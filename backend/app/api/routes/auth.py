from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.schemas.api import LoginRequest, SignupRequest, TermResponse, TokenResponse, UserResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/terms", response_model=list[TermResponse])
def signup_terms(session: Session = Depends(get_session)) -> list:
    return AuthService(session).signup_terms()


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, session: Session = Depends(get_session)) -> User:
    return AuthService(session).signup(payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)) -> TokenResponse:
    return TokenResponse(access_token=AuthService(session).login(payload))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(_: User = Depends(current_user)) -> None:
    # Stateless access token은 client가 폐기한다. 짧은 만료시간과 HTTPS 사용이 전제다.
    return None


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(current_user)) -> User:
    return user
