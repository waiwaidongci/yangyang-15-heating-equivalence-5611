from fastapi import APIRouter, Depends, Request
from redis.exceptions import RedisError

from src.schemas.requests import Credentials
from src.services.auth import current_user, sign_in
from src.services.broker import redis
from src.services.errors import BusinessError

router = APIRouter(prefix='/api/auth')


@router.post('/login')
def login(body: Credentials, request: Request):
    address = request.client.host if request.client else 'local'
    try:
        with redis.pipeline() as transaction:
            key = f'desk:login:{address}'
            count, _ = transaction.incr(key).expire(key, 30, nx=True).execute()
        if count > 60:
            raise BusinessError('登录尝试过多，请稍后重试', 429)
    except RedisError as exc:
        raise BusinessError('登录服务暂时不可用，请重试', 503) from exc
    return sign_in(body.email, body.password)


@router.get('/me')
def me(user=Depends(current_user)):
    return {'email': user['sub'], 'role': user['role']}
