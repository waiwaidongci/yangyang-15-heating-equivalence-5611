import logging
from time import perf_counter
from uuid import uuid4

logger = logging.getLogger('uvicorn.error')


async def trace_request(request, call_next):
    request_id = uuid4().hex
    request.state.request_id = request_id
    started = perf_counter()
    response = await call_next(request)
    response.headers['X-Request-Id'] = request_id
    if response.status_code >= 400:
        logger.info('%s %s %s %.1fms request=%s', request.method, request.url.path, response.status_code, (perf_counter()-started)*1000, request_id)
    return response
