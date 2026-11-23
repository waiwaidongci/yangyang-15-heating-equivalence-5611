from datetime import timedelta
from secrets import compare_digest

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config.runtime import JWT_SECRET
from src.constants.enums import Role
from src.models.base import utc_now
from src.services.errors import BusinessError


ACCOUNTS = {
    'viewer@demo.local': (Role.VIEWER, 'Viewer-2026!'),
    'analyst@demo.local': (Role.ANALYST, 'Analyst-2026!'),
    'supervisor@demo.local': (Role.SUPERVISOR, 'Supervisor-2026!'),
}
BEARER = HTTPBearer(auto_error=False)


def sign_in(email, password):
    email = email.strip().lower()
    user = ACCOUNTS.get(email)
    valid = compare_digest(password.encode(), (user[1] if user else 'unknown-demo-user').encode())
    if not user or not valid:
        raise BusinessError('邮箱或密码不正确', 401)
    role = user[0]
    token = jwt.encode({'sub': email, 'role': role, 'exp': utc_now() + timedelta(hours=8)}, JWT_SECRET, algorithm='HS256')
    return {'token': token, 'email': email, 'role': role}


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(BEARER)):
    try:
        if not credentials:
            raise jwt.InvalidTokenError
        claims = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=['HS256'], options={'require': ['sub', 'exp', 'role']})
        if claims['sub'] not in ACCOUNTS or ACCOUNTS[claims['sub']][0] != claims['role']:
            raise jwt.InvalidTokenError
        return claims
    except jwt.InvalidTokenError as exc:
        raise BusinessError('请重新登录', 401) from exc


def roles(*allowed):
    def check(user=Depends(current_user)):
        if user['role'] not in allowed:
            raise BusinessError('当前角色没有该操作权限', 403)
        return user
    return check
