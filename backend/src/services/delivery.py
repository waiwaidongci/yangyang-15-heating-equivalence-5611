from datetime import timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import select

from src.config.project import SPEC
from src.config.runtime import WORKDIR
from src.constants.enums import Decision, RunStatus
from src.models.base import utc_now
from src.models.workflow import AnalysisRun, AuditEvent, Delivery, Review, Schedule
from src.services.errors import BusinessError
from src.utils.formatting import csv_text


def create_schedule(db, request, actor):
    run = db.get(AnalysisRun, request.run_id)
    if run is None or not run.result or run.status != RunStatus.SUCCEEDED:
        raise BusinessError('只有已签核分析可以定时分发', 409)
    if not db.scalar(select(Review.id).where(Review.run_id == request.run_id, Review.decision == Decision.APPROVED)):
        raise BusinessError('只有已签核分析可以定时分发', 409)
    first_at = request.start_at.astimezone(timezone.utc).replace(tzinfo=None) if request.start_at else utc_now()
    if first_at < utc_now() - timedelta(minutes=1):
        raise BusinessError('首次分发时间已过去')
    schedule = Schedule(run_id=request.run_id, recipient=request.recipient,
                        interval_minutes=request.interval_minutes, next_at=first_at)
    db.add(schedule)
    db.flush()
    db.add(AuditEvent(actor=actor, action='schedule.created', detail=f'计划 #{schedule.id} · {schedule.recipient}'))
    return schedule


def stop_schedule(db, schedule_id, actor):
    schedule = db.get(Schedule, schedule_id, with_for_update=True)
    if schedule is None:
        raise BusinessError('计划不存在', 404)
    if schedule.active:
        schedule.active = False
        db.add(AuditEvent(actor=actor, action='schedule.stopped', detail=f'计划 #{schedule.id}'))
    return schedule


def dispatch_pending(db):
    now = utc_now()
    schedule = db.scalar(select(Schedule).where(Schedule.active.is_(True), Schedule.next_at <= now)
                         .order_by(Schedule.next_at, Schedule.id).limit(1).with_for_update(skip_locked=True))
    if schedule is None:
        return False
    due_at = schedule.next_at
    run = db.get(AnalysisRun, schedule.run_id)
    if run is None or not run.result:
        schedule.active = False
        db.add(AuditEvent(actor='worker', action='schedule.stopped',
                          detail=f'计划 #{schedule.id} 的来源分析已不可用'))
        return True
    filename = f'{SPEC["slug"]}-plan{schedule.id}-v{run.version}-{due_at:%Y%m%dT%H%M%S}.csv'
    result = run.result
    WORKDIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=WORKDIR, suffix='.tmp', delete=False) as temp:
        temp_name = Path(temp.name)
        temp.write(csv_text(result['columns'], result['rows']).encode('utf-8'))
    try:
        temp_name.replace(WORKDIR / filename)
    finally:
        temp_name.unlink(missing_ok=True)
    db.add(Delivery(schedule_id=schedule.id, scheduled_at=due_at, filename=filename))
    every = timedelta(minutes=schedule.interval_minutes)
    schedule.next_at = due_at + every * ((now - due_at) // every + 1)
    db.add(AuditEvent(actor='worker', action='report.delivered', detail=f'计划 #{schedule.id} · {schedule.recipient}'))
    return True
