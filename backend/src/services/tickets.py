"""Batch intake: separate old/new timing tickets, retests, corrections and withdrawals."""

import csv
import io
from collections import Counter
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from src.constants.enums import KIND_LABELS, TicketKind
from src.domain import tickets as rules
from src.models.workflow import AuditEvent, Batch, Ticket
from src.services.errors import BusinessError


MAX_TICKETS = 4000
MAX_ROWS = 500
MAX_UPLOAD = 512 * 1024
TICKET_COLUMNS = ('code', 'segment', 'kind', 'minutes', 'inspected_on', 'target_code', 'note')
REQUIRED_COLUMNS = ('code', 'segment', 'minutes', 'inspected_on')


def clean_ticket(payload, procedure=None):
    try:
        return rules.normalize(payload, procedure)
    except ValueError as exc:
        raise BusinessError(str(exc)) from exc


def create_batch(db, name, note, actor):
    name = (name or '').strip()
    if not name:
        raise BusinessError('请填写批次名称')
    if len(name) > 120:
        raise BusinessError('批次名称不能超过 120 个字符')
    if db.scalar(select(Batch.id).where(Batch.name == name)):
        raise BusinessError('已有同名批次，请换一个名称', 409)
    item = Batch(name=name, note=(note or '').strip()[:300], created_by=actor)
    db.add(item)
    db.flush()
    db.add(AuditEvent(actor=actor, action='batch.created', detail=f'批次 #{item.id} · {item.name}'))
    return item


def get_batch(db, batch_id):
    item = db.get(Batch, batch_id)
    if item is None:
        raise BusinessError('批次不存在', 404)
    return item


def batch_tickets(db, batch_id):
    return list(db.scalars(select(Ticket).where(Ticket.batch_id == batch_id).order_by(Ticket.id)))


def ticket_rows(items):
    return [{
        'id': item.id,
        'code': item.code,
        'segment': item.segment,
        'procedure': item.procedure,
        'kind': item.kind,
        'minutes': item.minutes,
        'target_code': item.target_code,
        'inspected_on': item.inspected_on.isoformat(),
        'note': item.note,
    } for item in items]


def resolve_batch(db, batch_id):
    items = batch_tickets(db, batch_id)
    try:
        resolution = rules.resolve(ticket_rows(items))
    except ValueError as exc:
        raise BusinessError(str(exc), 409) from exc
    return items, resolution


def snapshot(items):
    """Freeze the ticket document a run is calculated from."""
    return [{'code': row['code'], 'segment': row['segment'], 'procedure': row['procedure'],
             'kind': row['kind'], 'minutes': row['minutes'], 'target_code': row['target_code'],
             'inspected_on': row['inspected_on']} for row in ticket_rows(items)]


def _insert_tickets(db, batch_id, rows, actor):
    existing = set(db.scalars(select(Ticket.code).where(Ticket.batch_id == batch_id)))
    fresh = []
    seen = Counter()
    for row in rows:
        seen[row['code']] += 1
        if seen[row['code']] > 1 or row['code'] in existing:
            continue
        fresh.append(row)
    if db.scalar(select(func.count(Ticket.id)).where(Ticket.batch_id == batch_id)) + len(fresh) > MAX_TICKETS:
        raise BusinessError(f'单个批次最多保留 {MAX_TICKETS} 张工单', 409)
    items = [Ticket(batch_id=batch_id, code=row['code'], segment=row['segment'],
                    procedure=row['procedure'], kind=row['kind'], minutes=row['minutes'],
                    target_code=row['target_code'], inspected_on=date.fromisoformat(row['inspected_on']),
                    note=row['note'], submitted_by=actor) for row in fresh]
    db.add_all(items)
    if items:
        db.add(AuditEvent(actor=actor, action='tickets.added',
                          detail=f'批次 #{batch_id} 新增 {len(items)} 张计时工单'))
    try:
        db.flush()
    except IntegrityError as exc:
        raise BusinessError('有同一工单编号刚刚写入，请刷新后重试', 409) from exc
    return items, len(rows) - len(fresh)


def add_tickets(db, batch_id, payloads, actor):
    get_batch(db, batch_id)
    rows = [clean_ticket(payload) for payload in payloads]
    return _insert_tickets(db, batch_id, rows, actor)


def parse_csv(raw, procedure):
    if len(raw) > MAX_UPLOAD:
        raise BusinessError('CSV 文件上限 512 KB', 413)
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
        header = reader.fieldnames or []
        if len(set(header)) != len(header) or not set(REQUIRED_COLUMNS).issubset(header) \
                or not set(header).issubset(TICKET_COLUMNS):
            raise BusinessError('CSV 表头应为 code、segment、minutes、inspected_on，可选 kind、target_code、note')
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise BusinessError('列数与表头不匹配')
            payload = {key: value for key, value in row.items() if str(value).strip() != ''}
            payload.setdefault('kind', str(TicketKind.INITIAL))
            try:
                rows.append(clean_ticket(payload, procedure))
            except BusinessError as exc:
                raise BusinessError(f'CSV 第 {reader.line_num} 行，{exc}') from exc
            if len(rows) > MAX_ROWS:
                raise BusinessError('单次导入上限 500 条')
        if not rows:
            raise BusinessError('CSV 里没有计时工单')
        return rows
    except (UnicodeDecodeError, csv.Error) as exc:
        raise BusinessError('请上传 UTF-8 编码的有效 CSV') from exc


def import_tickets(db, batch_id, raw, procedure, actor):
    get_batch(db, batch_id)
    rows = parse_csv(raw, procedure)
    items, skipped = _insert_tickets(db, batch_id, rows, actor)
    return {'added': len(items), 'skipped': skipped}


def registry_view(items, resolution):
    status = resolution['ticket_status']
    return {
        'tickets': [rules.ticket_view(row, status.get(row['code'], 'valid')) for row in ticket_rows(items)],
        'segments': resolution['segments'],
        'missing': resolution['missing'],
        'ambiguous': resolution['ambiguous'],
        'issues': resolution['issues'],
        'pairs': {segment: {proc: [row['code'] for row in values]
                            for proc, values in sides.items()}
                  for segment, sides in resolution['live'].items()},
    }


def registry_csv(rows):
    columns = [('code', '工单编号'), ('segment', '巡检区段编号'), ('procedure', '规程'),
               ('kind', '计时类别'), ('minutes', '计时（分钟）'), ('inspected_on', '计时日期'),
               ('target_code', '被更正或撤回的工单编号'), ('note', '备注')]
    labels = {'old': '旧规程', 'new': '新规程'}
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([
            labels.get(row[key], row[key]) if key == 'procedure'
            else KIND_LABELS[TicketKind(row[key])] if key == 'kind'
            else row[key] for key, _ in columns
        ])
    return '﻿' + buffer.getvalue()
