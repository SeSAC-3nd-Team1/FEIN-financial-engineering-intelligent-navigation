from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.schemas.api import (
    EmailVerificationSendRequest,
    EmailVerificationSendResponse,
    EmailVerificationVerifyRequest,
    EmailVerificationVerifyResponse,
    LoginRequest,
    SignupRequest,
    TermResponse,
    TokenResponse,
    UserResponse,
)
from app.services.auth import AuthService
from app.services.email_verification import EmailVerificationService

router = APIRouter(prefix="/auth", tags=["auth"])


def email_verification_service() -> EmailVerificationService:
    return EmailVerificationService()


@router.get("/terms", response_model=list[TermResponse])
def signup_terms(session: Session = Depends(get_session)) -> list:
    return AuthService(session).signup_terms()


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def signup(
    payload: SignupRequest,
    session: Session = Depends(get_session),
    verification: EmailVerificationService = Depends(email_verification_service),
) -> User:
    return AuthService(session, verification).signup(payload)


@router.post(
    "/email-verifications/send",
    response_model=EmailVerificationSendResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def send_email_verification(
    payload: EmailVerificationSendRequest,
    request: Request,
    verification: EmailVerificationService = Depends(email_verification_service),
) -> EmailVerificationSendResponse:
    client_address = request.client.host if request.client is not None else None
    challenge = verification.send_code(str(payload.email), client_address)
    return EmailVerificationSendResponse(
        verification_id=challenge.verification_id,
        expires_in_seconds=challenge.expires_in_seconds,
        resend_after_seconds=challenge.resend_after_seconds,
    )


@router.post(
    "/email-verifications/verify",
    response_model=EmailVerificationVerifyResponse,
)
def verify_email(
    payload: EmailVerificationVerifyRequest,
    verification: EmailVerificationService = Depends(email_verification_service),
) -> EmailVerificationVerifyResponse:
    proof = verification.verify_code(payload.verification_id, payload.code)
    return EmailVerificationVerifyResponse(
        verification_token=proof.verification_token,
        expires_in_seconds=proof.expires_in_seconds,
    )


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
