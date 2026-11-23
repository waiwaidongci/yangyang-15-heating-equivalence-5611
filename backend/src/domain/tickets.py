"""Ticket intake and resolution for paired old/new inspection timings.

Work orders for the two procedures are submitted separately.  A batch may also
receive retests, corrections and withdrawals out of order; every correction or
withdrawal names the ticket it changes by code, so arrival order never decides
which timing is effective.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from itertools import product

from src.constants.enums import (
    KIND_LABELS,
    MEASUREMENT_KINDS,
    PROCEDURE_LABELS,
    TICKET_STATE_LABELS,
    Procedure,
    TicketKind,
)


PROCEDURE_ALIASES = {
    Procedure.OLD: Procedure.OLD, 'old': Procedure.OLD, '旧': Procedure.OLD, '旧规程': Procedure.OLD,
    Procedure.NEW: Procedure.NEW, 'new': Procedure.NEW, '新': Procedure.NEW, '新规程': Procedure.NEW,
}
KIND_ALIASES = {
    TicketKind.INITIAL: TicketKind.INITIAL, 'initial': TicketKind.INITIAL, '首次': TicketKind.INITIAL,
    '首次计时': TicketKind.INITIAL,
    TicketKind.RETEST: TicketKind.RETEST, 'retest': TicketKind.RETEST, '补测': TicketKind.RETEST,
    TicketKind.CORRECTION: TicketKind.CORRECTION, 'correction': TicketKind.CORRECTION, '更正': TicketKind.CORRECTION,
    TicketKind.WITHDRAWAL: TicketKind.WITHDRAWAL, 'withdrawal': TicketKind.WITHDRAWAL, '撤回': TicketKind.WITHDRAWAL,
}
MISSING_REASON_LABELS = {
    'no_ticket': '缺少该规程计时',
    'withdrawn': '该侧计时已全部撤回',
    'no_valid_measurement': '该侧没有有效计时',
    'unresolved': '引用的工单尚未到齐或无法核对',
    'conflict': '该侧更正与撤回互相冲突',
}
ISSUE_REASON_LABELS = {
    'unresolved_target': '引用的工单尚未到齐',
    'target_side_mismatch': '引用的工单不属于同一区段或同一规程',
    'target_not_measurement': '引用目标不是计时工单',
    'target_withdrawn': '引用的计时工单已经撤回',
    'conflicting_events': '同一工单收到互相冲突的更正或撤回',
}


def _text(value, label, limit=60, required=True):
    if value is None or str(value).strip() == '':
        if required:
            raise ValueError(f'{label}不能为空。')
        return None
    text = str(value).strip()
    if len(text) > limit:
        raise ValueError(f'{label}不能超过 {limit} 个字符。')
    return text


def _minutes(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label}必须是有效数字。') from None
    if not number.is_finite() or not Decimal('0.01') <= number <= Decimal('480'):
        raise ValueError(f'{label}必须在 0.01 到 480 分钟之间。')
    return float(number)


def _choice(value, aliases, label):
    if value is None:
        raise ValueError(f'请选择{label}。')
    text = str(value).strip()
    choice = aliases.get(text) or aliases.get(text.lower())
    if choice is None:
        raise ValueError(f'{label}无法识别。')
    return choice


def normalize(payload: dict, procedure=None) -> dict:
    """Validate one submitted ticket payload and return a canonical dict."""
    code = _text(payload.get('code'), '工单编号')
    segment = _text(payload.get('segment'), '巡检区段编号')
    raw_procedure = procedure if procedure is not None else payload.get('procedure')
    proc = _choice(raw_procedure, PROCEDURE_ALIASES, '规程')
    if procedure is not None and payload.get('procedure') not in (None, '') \
            and _choice(payload.get('procedure'), PROCEDURE_ALIASES, '规程') != proc:
        raise ValueError('提交的规程与工单内容不一致。')
    kind = _choice(payload.get('kind'), KIND_ALIASES, '计时类别')
    try:
        day = date.fromisoformat(str(payload.get('inspected_on')))
    except (TypeError, ValueError):
        raise ValueError(f'区段 {segment} 的计时日期必须采用 YYYY-MM-DD 格式。') from None
    target = _text(payload.get('target_code'), '关联工单编号', required=False)
    if kind == TicketKind.INITIAL:
        if target is not None:
            raise ValueError('首次计时工单不能填写关联工单编号。')
        minutes = _minutes(payload.get('minutes'), f'区段 {segment} 的计时（分钟）')
    elif kind == TicketKind.RETEST:
        if target is not None:
            raise ValueError('补测工单作为该区段的另一份有效计时，不填写关联工单编号。')
        minutes = _minutes(payload.get('minutes'), f'区段 {segment} 的计时（分钟）')
    elif kind == TicketKind.WITHDRAWAL:
        if target is None:
            raise ValueError('撤回工单必须填写被撤回的工单编号。')
        if payload.get('minutes') not in (None, ''):
            raise ValueError('撤回工单不填写计时分钟。')
        minutes = None
    else:
        if target is None:
            raise ValueError('更正工单必须填写被更正的工单编号。')
        if target == code:
            raise ValueError('工单不能引用自身。')
        minutes = _minutes(payload.get('minutes'), f'区段 {segment} 的计时（分钟）')
    note = _text(payload.get('note'), '备注', limit=300, required=False)
    return {
        'code': code,
        'segment': segment,
        'procedure': str(proc),
        'kind': str(kind),
        'minutes': minutes,
        'target_code': target,
        'inspected_on': day.isoformat(),
        'note': note,
    }


def _candidate_order(item):
    return item['inspected_on'], item['code']


def _dedupe_candidates(items):
    """One representative per measured value; later tickets win exact ties."""
    by_value = {}
    for item in sorted(items, key=_candidate_order):
        by_value[round(float(item['minutes']), 6)] = item
    return sorted(by_value.values(), key=_candidate_order)


def _side_text(procedures):
    return '、'.join(PROCEDURE_LABELS[Procedure(proc)] for proc in procedures)


def resolve(tickets: list[dict]) -> dict:
    """Group a batch's tickets by segment and determine usable measured values.

    The function is order independent: corrections and withdrawals attach to
    their target by code, so they may arrive before or after the ticket they
    change.  A withdrawal of a correction cancels that correction, which in turn
    restores the ticket it had replaced.
    """
    by_code = {}
    for item in tickets:
        if item['code'] in by_code:
            raise ValueError(f'工单编号 {item["code"]} 在本批次重复。')
        by_code[item['code']] = item

    broken = []
    valid_events = []
    for item in tickets:
        if item['kind'] not in (TicketKind.CORRECTION, TicketKind.WITHDRAWAL):
            continue
        target = by_code.get(item['target_code'])
        issue = {'code': item['code'], 'segment': item['segment'], 'procedure': item['procedure'],
                 'target_code': item['target_code'], 'kind': item['kind']}
        if target is None:
            broken.append({**issue, 'reason': 'unresolved_target'})
        elif target['segment'] != item['segment'] or target['procedure'] != item['procedure']:
            broken.append({**issue, 'reason': 'target_side_mismatch'})
        elif target['kind'] not in MEASUREMENT_KINDS:
            broken.append({**issue, 'reason': 'target_not_measurement'})
        else:
            valid_events.append(item)

    withdrawn_targets = {item['target_code'] for item in valid_events if item['kind'] == TicketKind.WITHDRAWAL}
    effective_corrections = [item for item in valid_events
                             if item['kind'] == TicketKind.CORRECTION and item['code'] not in withdrawn_targets]
    withdrawals_by_target = defaultdict(list)
    for item in valid_events:
        if item['kind'] == TicketKind.WITHDRAWAL:
            withdrawals_by_target[item['target_code']].append(item)
    corrections_by_target = defaultdict(list)
    for item in effective_corrections:
        corrections_by_target[item['target_code']].append(item)

    conflicted = set()
    conflict_sides = set()
    conflict_codes = set()
    for target_code in set(withdrawals_by_target) | set(corrections_by_target):
        withdrawals = withdrawals_by_target[target_code]
        corrections = corrections_by_target[target_code]
        if len(withdrawals) > 1 or len(corrections) > 1 or (withdrawals and corrections):
            target = by_code[target_code]
            conflicted.add(target_code)
            conflict_sides.add((target['segment'], target['procedure']))
            conflict_codes.add(target_code)
            conflict_codes.update(event['code'] for event in withdrawals + corrections)
            broken.append({'code': target_code, 'segment': target['segment'], 'procedure': target['procedure'],
                           'target_code': target_code, 'kind': None, 'reason': 'conflicting_events',
                           'events': [event['code'] for event in withdrawals + corrections]})
    broken_codes = {issue['code'] for issue in broken}

    replaced_by = defaultdict(list)
    for item in effective_corrections:
        if item['code'] in conflict_codes:
            continue
        if item['target_code'] in withdrawn_targets:
            broken.append({'code': item['code'], 'segment': item['segment'], 'procedure': item['procedure'],
                           'target_code': item['target_code'], 'kind': item['kind'], 'reason': 'target_withdrawn'})
            broken_codes.add(item['code'])
            continue
        replaced_by[item['target_code']].append(item)

    statuses = {}
    for item in tickets:
        code = item['code']
        if code in conflict_codes:
            statuses[code] = 'conflict'
        elif code in withdrawn_targets:
            statuses[code] = 'withdrawn'
        elif code in broken_codes:
            statuses[code] = 'unresolved'
        elif code in replaced_by:
            statuses[code] = 'replaced'
        elif item['kind'] in (TicketKind.CORRECTION, TicketKind.WITHDRAWAL):
            statuses[code] = 'applied'
        else:
            statuses[code] = 'valid'

    unresolved_sides = defaultdict(list)
    for issue in broken:
        if issue['reason'] == 'conflicting_events':
            continue
        if issue['reason'] == 'unresolved_target':
            unresolved_sides[(issue['segment'], issue['procedure'])].append(issue)

    live = defaultdict(lambda: defaultdict(list))
    present = defaultdict(lambda: defaultdict(bool))
    for item in tickets:
        present[item['segment']][item['procedure']] = True
        if item['kind'] not in MEASUREMENT_KINDS:
            continue
        if statuses[item['code']] in ('withdrawn', 'replaced', 'conflict', 'unresolved'):
            continue
        live[item['segment']][item['procedure']].append(item)

    segments = sorted({item['segment'] for item in tickets})
    pairs = {}
    missing = []
    ambiguous = []
    for segment in segments:
        reasons = {}
        candidates = {}
        for procedure in (Procedure.OLD, Procedure.NEW):
            proc = str(procedure)
            if (segment, proc) in conflict_sides:
                reasons[proc] = 'conflict'
                continue
            if unresolved_sides.get((segment, proc)):
                reasons[proc] = 'unresolved'
                continue
            values = live[segment].get(proc, [])
            if not values:
                if any(statuses[item['code']] == 'withdrawn' and item['segment'] == segment
                       and item['procedure'] == proc for item in tickets):
                    reasons[proc] = 'withdrawn'
                elif not present[segment].get(proc):
                    reasons[proc] = 'no_ticket'
                else:
                    reasons[proc] = 'no_valid_measurement'
                continue
            candidates[proc] = _dedupe_candidates(values)
        if reasons:
            missing.append({
                'segment': segment,
                'sides': [{'procedure': proc, 'label': PROCEDURE_LABELS[Procedure(proc)],
                           'reason': reason, 'text': MISSING_REASON_LABELS[reason]}
                          for proc, reason in reasons.items()],
                'text': '缺' + _side_text(reasons) + '计时',
            })
            continue
        pairs[segment] = candidates
        if len(candidates[str(Procedure.OLD)]) * len(candidates[str(Procedure.NEW)]) > 1:
            ambiguous.append({
                'segment': segment,
                'old': [{'code': item['code'], 'minutes': item['minutes']} for item in candidates[str(Procedure.OLD)]],
                'new': [{'code': item['code'], 'minutes': item['minutes']} for item in candidates[str(Procedure.NEW)]],
            })

    return {
        'segments': segments,
        'pairs': pairs,
        'missing': missing,
        'ambiguous': ambiguous,
        'issues': [{**issue, 'text': ISSUE_REASON_LABELS[issue['reason']]} for issue in broken],
        'ticket_status': statuses,
        'live': {segment: {proc: values for proc, values in sides.items()} for segment, sides in live.items()},
    }


def ticket_view(ticket, status):
    return {
        'id': ticket.get('id'),
        'code': ticket['code'],
        'segment': ticket['segment'],
        'procedure': ticket['procedure'],
        'procedure_label': PROCEDURE_LABELS[Procedure(ticket['procedure'])],
        'kind': ticket['kind'],
        'kind_label': KIND_LABELS[TicketKind(ticket['kind'])],
        'minutes': ticket['minutes'],
        'target_code': ticket['target_code'],
        'inspected_on': ticket['inspected_on'],
        'note': ticket.get('note'),
        'state': status,
        'state_label': TICKET_STATE_LABELS.get(status, status),
    }


def configuration_count(pairs):
    total = 1
    for sides in pairs.values():
        total *= len(sides[str(Procedure.OLD)]) * len(sides[str(Procedure.NEW)])
    return total


def configurations(pairs):
    """Yield every complete choice of one old and one new ticket per segment."""
    segments = list(pairs)
    choices = []
    for segment in segments:
        sides = pairs[segment]
        choices.append([(segment, sides[str(Procedure.OLD)][i], sides[str(Procedure.NEW)][j])
                        for i in range(len(sides[str(Procedure.OLD)]))
                        for j in range(len(sides[str(Procedure.NEW)]))])
    for combination in product(*choices):
        yield {segment: {'old': old, 'new': new} for segment, old, new in combination}


def canonical_configuration(pairs):
    """Latest measured ticket on each side; used to render a consistent verdict."""
    return {
        segment: {'old': sides[str(Procedure.OLD)][-1], 'new': sides[str(Procedure.NEW)][-1]}
        for segment, sides in pairs.items()
    }


def configuration_summary(configuration):
    return {segment: {'old': side['old']['code'], 'new': side['new']['code']}
            for segment, side in configuration.items()}
