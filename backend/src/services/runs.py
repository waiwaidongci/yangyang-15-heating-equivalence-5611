"""Analysis runs: versioned per batch, recalculated when tickets change."""

import json
import logging

from sqlalchemy import func, select

from src.config.project import SPEC
from src.constants.enums import Decision, Role, RunStatus
from src.domain import tickets as ticket_rules
from src.domain.analysis import analyze
from src.models.base import utc_now
from src.models.workflow import AnalysisRun, AuditEvent, Batch, Review
from src.services import tickets as ticket_service
from src.services.errors import BusinessError
from src.services.validation import validated

logger = logging.getLogger(__name__)

RETRYABLE = (RunStatus.FAILED, RunStatus.BLOCKED)


def review_of(db, run_id):
    return db.scalar(select(Review).where(Review.run_id == run_id))


def latest_run(db, batch_id):
    return db.scalar(select(AnalysisRun).where(AnalysisRun.batch_id == batch_id)
                     .order_by(AnalysisRun.version.desc()).limit(1))


def snapshot_analysis(ticket_snapshot, parameters):
    """Resolve a frozen snapshot and run the paired test on it."""
    resolution = ticket_rules.resolve(ticket_snapshot)
    result = analyze(resolution['pairs'], parameters, resolution['missing'], resolution['issues'])
    result['tickets'] = [ticket_rules.ticket_view(row, resolution['ticket_status'].get(row['code'], 'valid'))
                         for row in ticket_snapshot]
    result['segments'] = resolution['segments']
    return resolution, result


def current_snapshot(db, batch_id):
    items = ticket_service.batch_tickets(db, batch_id)
    try:
        resolution = ticket_rules.resolve(ticket_service.ticket_rows(items))
    except ValueError as exc:
        raise BusinessError(str(exc), 409) from exc
    return items, resolution, ticket_service.snapshot(items)


def snapshot_drifted(db, item):
    """True when the batch's tickets changed since this run's frozen snapshot."""
    if item.status == RunStatus.QUEUED:
        return False
    try:
        _, _, snap = current_snapshot(db, item.batch_id)
    except BusinessError:
        return False
    return snap != item.ticket_snapshot


def needs_recompute(db, item):
    """True when an unsigned conclusion must be recalculated.

    Recalculation supersedes the pending conclusion (it can no longer be signed)
    while the earlier tickets stay queryable through ``reproduce``.  A signed
    conclusion is never stale: it stays reproducible from its frozen tickets.
    """
    if item.superseded_by is not None or item.status == RunStatus.SUPERSEDED:
        return True
    if item.status == RunStatus.QUEUED or review_of(db, item.id) is not None:
        return False
    return snapshot_drifted(db, item)


def _mark_superseded(db, previous, new, actor):
    """Retire an unsigned conclusion; a signed one keeps standing beside v(new)."""
    if review_of(db, previous.id) is not None:
        return
    previous.status = RunStatus.SUPERSEDED
    previous.superseded_by = new.id
    db.add(AuditEvent(actor=actor, action='run.superseded',
                      detail=f'分析 #{previous.id} v{previous.version} 作废，改算 v{new.version}'))


def _new_version(db, batch, parameters, title, owner, actor, previous=None, action='run.created'):
    version = (db.scalar(select(func.max(AnalysisRun.version)).where(AnalysisRun.batch_id == batch.id)) or 0) + 1
    items, resolution, snapshot = current_snapshot(db, batch.id)
    item = AnalysisRun(batch_id=batch.id, version=version, title=title, owner=owner, parameters=parameters,
                       ticket_snapshot=snapshot, sample_size=len(resolution['pairs']))
    db.add(item)
    db.flush()
    if previous is not None:
        _mark_superseded(db, previous, item, actor)
    db.add(AuditEvent(actor=actor, action=action,
                      detail=f'批次 #{batch.id} 分析 v{version}，{len(resolution["pairs"])} 个配对区段'))
    return item


def create_run(db, batch_id, request, actor):
    parameters = validated(SPEC['parameters'], request.parameters, defaults=True)
    batch = db.scalar(select(Batch).where(Batch.id == batch_id).with_for_update())
    if batch is None:
        raise BusinessError('批次不存在', 404)
    latest = latest_run(db, batch_id)
    if latest is not None and latest.status in RETRYABLE and latest.superseded_by is None:
        latest.parameters = parameters
        latest.title = request.title
        return requeue(db, latest, actor, 'run.retried')
    return _new_version(db, batch, parameters, request.title, actor, actor, previous=latest)


def recompute_after_tickets(db, batch_id, actor):
    """Keep the pending conclusion in step with freshly imported tickets.

    A queued run has not concluded yet, so its snapshot is refreshed in place.
    An unreviewed succeeded run is superseded by a new version.  A failed or
    blocked run is retried in place, so retries never add a version.  Once a
    conclusion is signed it stays reproducible from its own tickets; later work
    opens a new version beside it instead of invalidating the signature.
    """
    latest = latest_run(db, batch_id)
    if latest is None:
        return None
    if latest.status == RunStatus.QUEUED:
        _, resolution, snapshot = current_snapshot(db, batch_id)
        latest.ticket_snapshot = snapshot
        latest.sample_size = len(resolution['pairs'])
        db.add(AuditEvent(actor=actor, action='run.refreshed',
                          detail=f'分析 #{latest.id} v{latest.version} 更新待算工单，不新增版本'))
        return latest
    if latest.status in RETRYABLE:
        return requeue(db, latest, actor, 'run.retried')
    return _new_version(db, db.get(Batch, batch_id), latest.parameters, latest.title, latest.owner, actor,
                        previous=latest, action='run.superseded')


def requeue(db, item, actor, action):
    _, resolution, snapshot = current_snapshot(db, item.batch_id)
    item.ticket_snapshot = snapshot
    item.sample_size = len(resolution['pairs'])
    item.status = RunStatus.QUEUED
    item.result = None
    item.error = None
    item.finished_at = None
    db.add(AuditEvent(actor=actor, action=action, detail=f'分析 #{item.id} v{item.version} 重试，不新增版本'))
    return item


def retry_run(db, run_id, actor):
    item = db.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update())
    if item is None:
        raise BusinessError('分析不存在', 404)
    if item.status not in RETRYABLE:
        raise BusinessError('只有失败或受阻的分析需要重试', 409)
    if item.superseded_by is not None:
        raise BusinessError('这份分析已被新的版本取代，请查看最新版本', 409)
    return requeue(db, item, actor, 'run.retried')


def visible_runs(db, user, run_id=None):
    query = select(AnalysisRun, Review).outerjoin(Review, Review.run_id == AnalysisRun.id)
    if user['role'] == Role.VIEWER:
        query = query.where(Review.decision == Decision.APPROVED)
    if run_id is not None:
        pair = db.execute(query.where(AnalysisRun.id == run_id)).first()
        if pair is None:
            raise BusinessError('没有可查看的分析结果', 404)
        return pair
    return db.execute(query.order_by(AnalysisRun.id.desc()).limit(200)).all()


def submit_review(db, run_id, request, actor):
    item = db.scalar(select(AnalysisRun).where(AnalysisRun.id == run_id).with_for_update())
    if item is None:
        raise BusinessError('分析不存在', 404)
    db.scalar(select(Batch).where(Batch.id == item.batch_id).with_for_update())
    if item.superseded_by is not None or item.status == RunStatus.SUPERSEDED:
        raise BusinessError('这份结论已作废，不能继续签核，请复核最新版本', 409)
    latest = latest_run(db, item.batch_id)
    if latest is not None and latest.id != item.id:
        raise BusinessError('这份分析已被新的版本取代，请复核最新版本', 409)
    if item.status != RunStatus.SUCCEEDED:
        raise BusinessError('分析算完后才能复核', 409)
    if not item.result or not item.result.get('consistent'):
        raise BusinessError('配法裁决不一致，需先核对工单再签核', 409)
    if snapshot_drifted(db, item):
        recompute_after_tickets(db, item.batch_id, actor)
        raise BusinessError('批次已有新的计时工单，结论正在重算，旧结论不能继续待签，请待重算完成', 409)
    if review_of(db, run_id) is not None:
        raise BusinessError('这份分析已完成复核。请发起新分析并重新复核。', 409)
    if item.owner == actor:
        raise BusinessError('分析须由另一位负责人复核', 409)
    review = Review(run_id=run_id, decision=request.decision, note=request.note, reviewer=actor)
    db.add(review)
    db.add(AuditEvent(actor=actor, action=f'review.{request.decision}',
                      detail=f'分析 #{run_id} v{item.version} · 批次 #{item.batch_id}'))
    db.flush()
    return review


def reproduce(db, item):
    """Re-run the frozen snapshot and confirm the signed numbers still match."""
    if item.status not in (RunStatus.SUCCEEDED, RunStatus.SUPERSEDED) or not item.result:
        raise BusinessError('只有已完成计算的分析可以复现', 409)
    try:
        _, result = snapshot_analysis(item.ticket_snapshot, item.parameters)
    except ValueError as exc:
        raise BusinessError(f'按当时工单复现失败：{exc}', 409) from exc
    stored = item.result
    matches = all(stored.get(key) == result.get(key) for key in ('verdict', 'metrics', 'rows', 'chart'))
    return {
        'run_id': item.id,
        'version': item.version,
        'matches': matches,
        'verdict': result.get('verdict'),
        'verdict_label': result.get('verdict_label'),
        'metrics': result.get('metrics'),
        'chart': result.get('chart'),
        'configurations': result.get('configurations'),
        'canonical': result.get('canonical'),
        'tickets': result.get('tickets'),
        'snapshot_size': len(item.ticket_snapshot),
        'stored_verdict': stored.get('verdict'),
    }


def run_pending(db):
    item = db.scalar(select(AnalysisRun).where(AnalysisRun.status == RunStatus.QUEUED)
                     .order_by(AnalysisRun.id).limit(1).with_for_update(skip_locked=True))
    if item is None:
        return False
    try:
        resolution, result = snapshot_analysis(item.ticket_snapshot, item.parameters)
        if not {'headline', 'summary', 'metrics', 'columns', 'rows', 'verdict'} <= set(result):
            raise RuntimeError('invalid result schema')
        json.dumps(result, allow_nan=False, ensure_ascii=False)
        item.result = result
        item.status = RunStatus.SUCCEEDED
        item.error = None
    except ValueError as exc:
        item.error = str(exc)[:600] or '本次观测数据不足以完成计算'
        try:
            resolution = ticket_rules.resolve(item.ticket_snapshot)
        except ValueError:
            resolution = None
        if resolution is not None and not resolution['pairs'] and resolution['missing']:
            item.status = RunStatus.BLOCKED
            item.error = f'{item.error} 缺单区段：' + '、'.join(row['segment'] for row in resolution['missing'])
        else:
            item.status = RunStatus.FAILED
    except Exception:
        logger.exception('Analysis %s raised unexpectedly', item.id)
        item.error = '分析计算失败，请检查记录和参数后重试'
        item.status = RunStatus.FAILED
    item.finished_at = utc_now()
    return True
