from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from scripts.seed_demo import seed_data
from src.config.project import SPEC
from src.config.runtime import SEED_DEMO
from src.middlewares.headers import response_headers
from src.middlewares.trace import trace_request
from src.models.base import Base, Session, engine
from src.routes import analysis, records, reports, session
from src.services.broker import redis
from src.services.errors import BusinessError

logger = logging.getLogger('uvicorn.error')


@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    if SEED_DEMO:
        try:
            logger.info('demo row counts %s', seed_data())
        except Exception:
            logger.exception('demo seed failed')
    yield


app = FastAPI(title=SPEC['title'], lifespan=lifespan)
app.middleware('http')(trace_request)
app.middleware('http')(response_headers)
for module in (session, records, analysis, reports):
    app.include_router(module.router)


@app.exception_handler(BusinessError)
async def business_error(_request: Request, exc: BusinessError):
    return JSONResponse({'detail': str(exc)}, status_code=exc.status)


@app.exception_handler(RequestValidationError)
async def request_error(_request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    label = str(first['loc'][-1])
    return JSONResponse({'detail': f'请求字段不符合要求（{label}）'}, status_code=422)


@app.get('/api/health')
def health():
    with Session() as database:
        database.execute(text('SELECT 1'))
    redis.ping()
    return {'status': 'ok', 'project': SPEC['slug']}
