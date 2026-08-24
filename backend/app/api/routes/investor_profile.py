"""Investor-profile analysis API."""

from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.core.config import settings
from app.integrations.ai import AzureOpenAIInvestorProfileClient
from app.models import User
from app.schemas.api import InvestorProfileAnalyzeRequest, InvestorProfileResponse
from app.services.investor_profile import InvestorProfileService

router = APIRouter(prefix="/investor-profile", tags=["investor-profile"])


def get_investor_profile_service() -> InvestorProfileService:
    client = AzureOpenAIInvestorProfileClient(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        timeout_seconds=settings.ai_profile_timeout_seconds,
    )
    return InvestorProfileService(client)


@router.post("/analyze", response_model=InvestorProfileResponse)
async def analyze_investor_profile(
    payload: InvestorProfileAnalyzeRequest,
    _: User = Depends(current_user),
    service: InvestorProfileService = Depends(get_investor_profile_service),
) -> InvestorProfileResponse:
    return await service.analyze(payload)
