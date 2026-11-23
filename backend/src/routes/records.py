from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from src.config.project import SPEC
from src.constants.enums import Role
from src.controllers.views import batch_view
from src.models.base import Session
from src.models.workflow import Batch, Ticket
from src.schemas.requests import CreateBatch, TicketBatchInput
from src.services.auth import current_user, roles
from src.services.errors import BusinessError
from src.services.runs import latest_run, needs_recompute, recompute_after_tickets
from src.services.tickets import (
    add_tickets,
    batch_tickets,
    create_batch,
    get_batch,
    import_tickets,
    registry_csv,
    registry_view,
    resolve_batch,
)
from src.services.broker import wake_worker

router = APIRouter(prefix='/api')
editor = roles(Role.ANALYST, Role.SUPERVISOR)


def _stats(db, batch):
    items = batch_tickets(db, batch.id)
    try:
        resolution = resolve_batch(db, batch.id)[1]
    except BusinessError:
        resolution = {'segments': [], 'missing': []}
    run = latest_run(db, batch.id)
    return {
        'ticket_count': len(items),
        'segment_count': len(resolution['segments']),
        'paired_count': len(resolution.get('pairs', {})),
        'missing_count': len(resolution.get('missing', [])),
        'latest_run': {'id': run.id, 'version': run.version, 'status': run.status} if run else None,
        'needs_recompute': bool(run and needs_recompute(db, run)),
    }


@router.get('/spec')
def spec():
    return SPEC


@router.get('/batches')
def batches(user=Depends(current_user)):
    with Session() as db:
        items = list(db.scalars(select(Batch).order_by(Batch.id.desc()).limit(100)))
        return [batch_view(item, _stats(db, item)) for item in items]


@router.post('/batches', status_code=201)
def create_batch_route(request: CreateBatch, user=Depends(editor)):
    with Session.begin() as db:
        item = create_batch(db, request.name, request.note, user['sub'])
        return batch_view(item, _stats(db, item))


@router.get('/batches/{batch_id}')
def batch_detail(batch_id: int, user=Depends(current_user)):
    with Session() as db:
        batch = get_batch(db, batch_id)
        return batch_view(batch, _stats(db, batch))


def _registry(db, batch_id):
    batch = get_batch(db, batch_id)
    items, resolution = resolve_batch(db, batch_id)
    view = registry_view(items, resolution)
    view['batch'] = batch_view(batch, _stats(db, batch))
    return view


@router.get('/batches/{batch_id}/registry')
def registry(batch_id: int, user=Depends(current_user)):
    with Session() as db:
        return _registry(db, batch_id)


@router.post('/batches/{batch_id}/tickets', status_code=201)
def submit_tickets(batch_id: int, request: TicketBatchInput, user=Depends(editor)):
    with Session.begin() as db:
        items, skipped = add_tickets(db, batch_id, [row.model_dump() for row in request.tickets], user['sub'])
        if not items:
            raise BusinessError('这些工单编号都已在批次中，未新增记录', 409)
        recompute_after_tickets(db, batch_id, user['sub'])
        view = _registry(db, batch_id)
    wake_worker()
    view['added'] = len(items)
    view['skipped'] = skipped
    return view


def _import(batch_id, raw, procedure, actor):
    with Session.begin() as db:
        report = import_tickets(db, batch_id, raw, procedure, actor)
        if report['added']:
            recompute_after_tickets(db, batch_id, actor)
        return report


@router.post('/batches/{batch_id}/tickets/import')
async def import_ticket_csv(batch_id: int, request: Request, procedure: str = Query(...),
                            user=Depends(editor)):
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 512 * 1024:
            raise BusinessError('CSV 文件上限 512 KB', 413)
        raw.extend(chunk)
    report = await run_in_threadpool(_import, batch_id, bytes(raw), procedure, user['sub'])
    if report['added']:
        wake_worker()
    return report


@router.get('/batches/{batch_id}/tickets/template')
def ticket_template(batch_id: int, procedure: str = Query(...), user=Depends(current_user)):
    with Session() as db:
        get_batch(db, batch_id)
    if procedure not in ('old', 'new'):
        raise BusinessError('规程须为 old 或 new')
    fields = ['code', 'segment', 'kind', 'minutes', 'inspected_on', 'target_code', 'note']
    example = ','.join(['SJ-0111-O-01' if procedure == 'old' else 'SJ-0111-N-01',
                        'SJ-01', 'initial', '24.00', '2026-11-17', '', ''])
    payload = '﻿' + ','.join(fields) + '\r\n' + example + '\r\n'
    return Response(payload, media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={SPEC["slug"]}-{procedure}-tickets.csv'})


@router.get('/batches/{batch_id}/tickets/export')
def export_tickets(batch_id: int, procedure: str = Query(...), user=Depends(current_user)):
    if procedure not in ('old', 'new'):
        raise BusinessError('规程须为 old 或 new')
    with Session() as db:
        get_batch(db, batch_id)
        items, resolution = resolve_batch(db, batch_id)
        view = registry_view(items, resolution)
        rows = [row for row in view['tickets'] if row['procedure'] == procedure]
    file = f'{SPEC["slug"]}-{procedure}-tickets.csv'
    return Response(registry_csv(rows), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename={file}'})
