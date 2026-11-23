from fastapi import APIRouter, Depends
from fastapi.responses import Response

from src.config.project import SPEC
from src.constants.enums import Role, RunStatus
from src.controllers.views import review_view, run_view
from src.models.base import Session
from src.schemas.requests import CreateRun, ReviewInput
from src.services.auth import current_user, roles
from src.services.broker import wake_worker
from src.services.errors import BusinessError
from src.services.runs import create_run, submit_review, visible_runs
from src.utils.formatting import csv_text

router = APIRouter(prefix='/api/runs')


@router.get('')
def index(user=Depends(current_user)):
    with Session() as db:
        return [run_view(run, review) for run, review in visible_runs(db, user)]


@router.post('', status_code=201)
def create(request: CreateRun, user=Depends(roles(Role.ANALYST))):
    with Session.begin() as db:
        item = create_run(db, request, user['sub'])
        view = run_view(item)
    wake_worker()
    return view


@router.get('/{run_id}')
def detail(run_id: int, user=Depends(current_user)):
    with Session() as db:
        run, review = visible_runs(db, user, run_id)
        return run_view(run, review, include_result=True)


@router.post('/{run_id}/review', status_code=201)
def decision(run_id: int, request: ReviewInput, user=Depends(roles(Role.SUPERVISOR))):
    with Session.begin() as db:
        return review_view(submit_review(db, run_id, request, user['sub']))


@router.get('/{run_id}/export')
def export(run_id: int, user=Depends(current_user)):
    with Session() as db:
        run, _ = visible_runs(db, user, run_id)
        if run.status != RunStatus.SUCCEEDED:
            raise BusinessError('分析完成后才能下载明细', 409)
        result = run.result
        file = f'{SPEC["slug"]}-run-{run_id}.csv'
        return Response(csv_text(result['columns'], result['rows']), media_type='text/csv',
                        headers={'Content-Disposition': f'attachment; filename={file}'})
