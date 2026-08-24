"""Investor-profile analysis API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import settings
from app.db.session import get_session
from app.integrations.ai import AzureOpenAIInvestorProfileClient
from app.models import User
from app.schemas.api import InvestorProfileAnalyzeRequest, InvestorProfileResponse
from app.services.investor_profile import InvestorProfileService

router = APIRouter(prefix="/investor-profile", tags=["investor-profile"])


def get_investor_profile_service(session: Session = Depends(get_session)) -> InvestorProfileService:
    client = AzureOpenAIInvestorProfileClient(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        timeout_seconds=settings.ai_profile_timeout_seconds,
    )
    return InvestorProfileService(
        session,
        client,
        model_version=settings.ai_profile_model_version,
        prompt_version=settings.ai_profile_prompt_version,
    )


@router.post("/analyze", response_model=InvestorProfileResponse)
async def analyze_investor_profile(
    payload: InvestorProfileAnalyzeRequest,
    user: User = Depends(current_user),
    service: InvestorProfileService = Depends(get_investor_profile_service),
) -> InvestorProfileResponse:
    return await service.analyze(user.id, payload)


@router.get("/me/latest", response_model=InvestorProfileResponse)
def latest_investor_profile(
    user: User = Depends(current_user),
    service: InvestorProfileService = Depends(get_investor_profile_service),
) -> InvestorProfileResponse:
    return service.latest(user.id)
