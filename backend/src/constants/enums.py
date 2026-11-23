from enum import StrEnum


class Role(StrEnum):
    VIEWER = 'viewer'
    ANALYST = 'analyst'
    SUPERVISOR = 'supervisor'


class Procedure(StrEnum):
    OLD = 'old'
    NEW = 'new'


class TicketKind(StrEnum):
    INITIAL = 'initial'
    RETEST = 'retest'
    CORRECTION = 'correction'
    WITHDRAWAL = 'withdrawal'


MEASUREMENT_KINDS = frozenset({TicketKind.INITIAL, TicketKind.RETEST, TicketKind.CORRECTION})


class RunStatus(StrEnum):
    QUEUED = 'queued'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    BLOCKED = 'blocked'
    SUPERSEDED = 'superseded'


class Decision(StrEnum):
    APPROVED = 'approved'
    RETURNED = 'returned'


TICKET_STATE_LABELS = {
    'valid': '有效',
    'withdrawn': '已撤回',
    'replaced': '已被更正',
    'applied': '生效',
    'superseded': '已失效',
    'unresolved': '待核对引用',
}

PROCEDURE_LABELS = {Procedure.OLD: '旧规程', Procedure.NEW: '新规程'}
KIND_LABELS = {
    TicketKind.INITIAL: '首次计时',
    TicketKind.RETEST: '补测',
    TicketKind.CORRECTION: '更正',
    TicketKind.WITHDRAWAL: '撤回',
}
