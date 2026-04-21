from __future__ import annotations

import datetime as dt

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import config

security = HTTPBearer(auto_error=False)


def create_access_token(email: str) -> str:
    now = dt.datetime.utcnow()
    payload = {
        "sub": email,
        "role": "admin",
        "iat": now,
        "exp": now + dt.timedelta(hours=config.token_expire_hours),
    }
    return jwt.encode(payload, config.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, config.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录状态无效或已过期",
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少登录凭证",
        )
    payload = decode_token(credentials.credentials)
    subject = payload.get("sub")
    if subject != config.admin_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前账号无权访问",
        )
    return {"email": subject, "role": payload.get("role", "admin")}
