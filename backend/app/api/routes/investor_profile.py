"""Investor-profile analysis API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.schemas.api import InvestorProfileAnalyzeRequest, InvestorProfileResponse
from app.services.investor_profile import InvestorProfileService

router = APIRouter(prefix="/investor-profile", tags=["investor-profile"])


def get_investor_profile_service(session: Session = Depends(get_session)) -> InvestorProfileService:
    return InvestorProfileService(session)


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
