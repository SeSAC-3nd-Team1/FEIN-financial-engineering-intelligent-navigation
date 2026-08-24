"""FastAPI 인증/DB dependencies."""

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User

bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(get_session),
) -> User:
    if not credentials:
        raise ServiceError("AUTHENTICATION_REQUIRED", "로그인이 필요합니다.", 401)
    try:
        user_id = decode_access_token(credentials.credentials)
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise ServiceError("INVALID_TOKEN", "유효하지 않은 인증 토큰입니다.", 401) from exc
    user = session.get(User, user_id)
    if not user or user.account_status != "ACTIVE":
        raise ServiceError("INVALID_TOKEN", "유효하지 않은 인증 토큰입니다.", 401)
    return user
