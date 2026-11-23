from src.constants.enums import (
    KIND_LABELS,
    PROCEDURE_LABELS,
    TICKET_STATE_LABELS,
    Procedure,
    RunStatus,
    TicketKind,
)
from src.utils.formatting import timestamp


RUN_STATUS_LABELS = {
    RunStatus.QUEUED: '等待重算',
    RunStatus.SUCCEEDED: '待复核',
    RunStatus.FAILED: '计算失败',
    RunStatus.BLOCKED: '缺单受阻',
    RunStatus.SUPERSEDED: '已作废',
}


def review_view(item):
    return {'decision': item.decision, 'note': item.note, 'reviewer': item.reviewer,
            'at': timestamp(item.created_at)} if item else None


def run_view(item, review=None, *, include_result=False, stale=False):
    view = {
        'id': item.id,
        'batch_id': item.batch_id,
        'version': item.version,
        'title': item.title,
        'owner': item.owner,
        'status': item.status,
        'status_label': RUN_STATUS_LABELS.get(item.status, item.status),
        'parameters': item.parameters,
        'sample_size': item.sample_size,
        'created_at': timestamp(item.created_at),
        'finished_at': timestamp(item.finished_at),
        'review': review_view(review),
        'error': item.error,
        'superseded_by': item.superseded_by,
        'stale': stale,
    }
    if include_result:
        view['result'] = item.result
    return view


def ticket_view(item):
    return {
        'id': item.id,
        'code': item.code,
        'segment': item.segment,
        'procedure': item.procedure,
        'procedure_label': PROCEDURE_LABELS.get(Procedure(item.procedure), item.procedure),
        'kind': item.kind,
        'kind_label': KIND_LABELS.get(TicketKind(item.kind), item.kind),
        'minutes': item.minutes,
        'target_code': item.target_code,
        'inspected_on': item.inspected_on.isoformat(),
        'note': item.note,
        'submitted_by': item.submitted_by,
        'created_at': timestamp(item.created_at),
        'state': 'valid',
        'state_label': TICKET_STATE_LABELS['valid'],
    }


def batch_view(item, stats):
    return {
        'id': item.id,
        'name': item.name,
        'note': item.note,
        'created_by': item.created_by,
        'created_at': timestamp(item.created_at),
        'ticket_count': stats.get('ticket_count', 0),
        'segment_count': stats.get('segment_count', 0),
        'paired_count': stats.get('paired_count', 0),
        'missing_count': stats.get('missing_count', 0),
        'latest_run': stats.get('latest_run'),
        'needs_recompute': stats.get('needs_recompute', False),
    }


def schedule_view(item):
    return {'id': item.id, 'run_id': item.run_id, 'recipient': item.recipient,
            'interval_minutes': item.interval_minutes, 'next_at': timestamp(item.next_at), 'active': item.active}


def delivery_view(delivery, schedule):
    return {'id': delivery.id, 'schedule_id': schedule.id, 'recipient': schedule.recipient,
            'run_id': schedule.run_id, 'at': timestamp(delivery.delivered_at),
            'scheduled_at': timestamp(delivery.scheduled_at)}
