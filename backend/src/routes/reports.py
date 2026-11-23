from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select

from src.config.runtime import WORKDIR
from src.constants.enums import Role
from src.controllers.views import delivery_view, schedule_view
from src.models.base import Session
from src.models.workflow import AuditEvent, Delivery, Schedule
from src.schemas.requests import ScheduleInput
from src.services.auth import current_user, roles
from src.services.broker import wake_worker
from src.services.delivery import create_schedule, stop_schedule
from src.services.errors import BusinessError
from src.utils.formatting import timestamp

router = APIRouter(prefix='/api/reports')
supervisor = roles(Role.SUPERVISOR)


@router.get('/schedules')
def schedules(user=Depends(supervisor)):
    with Session() as db:
        return [schedule_view(row) for row in db.scalars(select(Schedule).order_by(Schedule.id.desc()).limit(100))]


@router.post('/schedules', status_code=201)
def create(request: ScheduleInput, user=Depends(supervisor)):
    with Session.begin() as db:
        view = schedule_view(create_schedule(db, request, user['sub']))
    wake_worker()
    return view


@router.post('/schedules/{schedule_id}/stop')
def stop(schedule_id: int, user=Depends(supervisor)):
    with Session.begin() as db:
        return schedule_view(stop_schedule(db, schedule_id, user['sub']))


@router.get('/inbox')
def inbox(user=Depends(current_user)):
    with Session() as db:
        query = select(Delivery, Schedule).join(Schedule, Schedule.id == Delivery.schedule_id)
        return [delivery_view(*pair) for pair in db.execute(query.order_by(Delivery.id.desc()).limit(100))]


@router.get('/inbox/{delivery_id}/file')
def get_file(delivery_id: int, user=Depends(current_user)):
    with Session() as db:
        row = db.get(Delivery, delivery_id)
        if not row or not (WORKDIR / row.filename).is_file():
            raise BusinessError('分发文件不存在', 404)
        return FileResponse(WORKDIR / row.filename, filename=row.filename, media_type='text/csv')


@router.get('/audit')
def audit(user=Depends(supervisor)):
    with Session() as db:
        return [{'at': timestamp(row.at), 'actor': row.actor, 'action': row.action, 'detail': row.detail}
                for row in db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(100))]
