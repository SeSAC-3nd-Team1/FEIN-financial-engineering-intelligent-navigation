"""가상투자 시작 약관, 계좌 준비, 최종 확정 API."""

from ipaddress import ip_address
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.schemas.api import (
    InvestmentAccountPrepareRequest,
    InvestmentAccountPrepareResponse,
    InvestmentAgreementSubmitRequest,
    InvestmentOnboardingCreateRequest,
    InvestmentOnboardingResponse,
    InvestmentTermResponse,
)
from app.services.investment_onboarding import InvestmentOnboardingService

router = APIRouter(prefix="/investment", tags=["investment"])


def _client_ip(request: Request) -> str | None:
    """PostgreSQL INET에 저장할 수 있는 실제 IP 형식만 감사 정보로 전달한다."""

    if request.client is None:
        return None
    try:
        return str(ip_address(request.client.host))
    except ValueError:
        # TestClient 같은 비네트워크 client 이름은 감사 IP로 저장하지 않는다.
        return None


def get_investment_onboarding_service(
    session: Session = Depends(get_session),
) -> InvestmentOnboardingService:
    return InvestmentOnboardingService(session)


@router.get("/terms", response_model=list[InvestmentTermResponse])
def investment_terms(
    strategy_id: str,
    _: User = Depends(current_user),
    service: InvestmentOnboardingService = Depends(get_investment_onboarding_service),
) -> list:
    return service.terms(strategy_id)


@router.post("/onboardings", response_model=InvestmentOnboardingResponse)
def create_or_update_onboarding(
    payload: InvestmentOnboardingCreateRequest,
    user: User = Depends(current_user),
    service: InvestmentOnboardingService = Depends(get_investment_onboarding_service),
) -> InvestmentOnboardingResponse:
    return service.create_or_update(user, payload)


@router.get("/onboardings/me/current", response_model=InvestmentOnboardingResponse)
def current_onboarding(
    user: User = Depends(current_user),
    service: InvestmentOnboardingService = Depends(get_investment_onboarding_service),
) -> InvestmentOnboardingResponse:
    return service.current(user.id)


@router.post("/onboardings/{onboarding_id}/agreements", response_model=InvestmentOnboardingResponse)
def agree_to_investment_terms(
    onboarding_id: UUID,
    payload: InvestmentAgreementSubmitRequest,
    request: Request,
    user: User = Depends(current_user),
    service: InvestmentOnboardingService = Depends(get_investment_onboarding_service),
) -> InvestmentOnboardingResponse:
    return service.agree(
        user.id,
        onboarding_id,
        payload,
        agreed_ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/onboardings/{onboarding_id}/account", response_model=InvestmentAccountPrepareResponse)
def prepare_virtual_account(
    onboarding_id: UUID,
    payload: InvestmentAccountPrepareRequest,
    user: User = Depends(current_user),
    service: InvestmentOnboardingService = Depends(get_investment_onboarding_service),
) -> InvestmentAccountPrepareResponse:
    return service.prepare_account(user, onboarding_id, payload.account_name)


@router.post("/onboardings/{onboarding_id}/complete", response_model=InvestmentOnboardingResponse)
def complete_onboarding(
    onboarding_id: UUID,
    user: User = Depends(current_user),
    service: InvestmentOnboardingService = Depends(get_investment_onboarding_service),
) -> InvestmentOnboardingResponse:
    return service.complete(user.id, onboarding_id)
