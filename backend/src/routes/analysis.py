from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select

from src.config.project import SPEC
from src.constants.enums import Decision, Role, RunStatus
from src.controllers.views import review_view, run_view
from src.models.base import Session
from src.models.workflow import AnalysisRun, Review
from src.schemas.requests import CreateRun, ReviewInput
from src.services.auth import current_user, roles
from src.services.broker import wake_worker
from src.services.errors import BusinessError
from src.services.runs import (
    create_run,
    needs_recompute,
    reproduce,
    retry_run,
    review_of,
    submit_review,
    visible_runs,
)
from src.utils.formatting import csv_text

router = APIRouter(prefix='/api/runs')


@router.get('')
def index(batch_id: int | None = None, user=Depends(current_user)):
    with Session() as db:
        return [run_view(run, review, stale=needs_recompute(db, run))
                for run, review in visible_runs(db, user) if batch_id is None or run.batch_id == batch_id]


@router.post('', status_code=201)
def create(request: CreateRun, batch_id: int, user=Depends(roles(Role.ANALYST))):
    with Session.begin() as db:
        item = create_run(db, batch_id, request, user['sub'])
        view = run_view(item)
    wake_worker()
    return view


@router.get('/{run_id}')
def detail(run_id: int, user=Depends(current_user)):
    with Session() as db:
        run, review = visible_runs(db, user, run_id)
        return run_view(run, review, include_result=True, stale=needs_recompute(db, run))


@router.post('/{run_id}/review', status_code=201)
def decision(run_id: int, request: ReviewInput, user=Depends(roles(Role.SUPERVISOR))):
    with Session.begin() as db:
        return review_view(submit_review(db, run_id, request, user['sub']))


@router.post('/{run_id}/retry', status_code=201)
def retry(run_id: int, user=Depends(roles(Role.ANALYST))):
    with Session.begin() as db:
        item = retry_run(db, run_id, user['sub'])
        view = run_view(item, review_of(db, item.id))
    wake_worker()
    return view


@router.post('/{run_id}/reproduce')
def reproduce_route(run_id: int, user=Depends(current_user)):
    with Session() as db:
        run = db.get(AnalysisRun, run_id)
        if run is None:
            raise BusinessError('分析不存在', 404)
        if user['role'] == Role.VIEWER and not db.scalar(
                select(Review.id).where(Review.run_id == run_id, Review.decision == Decision.APPROVED)):
            raise BusinessError('没有可查看的分析结果', 404)
        return reproduce(db, run)


@router.get('/{run_id}/export')
def export(run_id: int, user=Depends(current_user)):
    with Session() as db:
        run, _ = visible_runs(db, user, run_id)
        if run.status != RunStatus.SUCCEEDED or not run.result:
            raise BusinessError('分析完成后才能下载明细', 409)
        result = run.result
        file = f'{SPEC["slug"]}-run-{run_id}-v{run.version}.csv'
        return Response(csv_text(result['columns'], result['rows']), media_type='text/csv',
                        headers={'Content-Disposition': f'attachment; filename={file}'})
