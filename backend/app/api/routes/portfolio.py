from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.schemas.api import PortfolioHistoryResponse, PortfolioResponse
from app.services.portfolio import PortfolioService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioResponse)
def portfolio(account_id: UUID = Query(), user: User = Depends(current_user), session: Session = Depends(get_session)) -> PortfolioResponse:
    return PortfolioService(session).evaluate(user.id, account_id)


@router.get("/history", response_model=PortfolioHistoryResponse)
def portfolio_history(
    account_id: UUID = Query(),
    period: Literal["1M", "3M", "1Y", "ALL"] = Query(default="1Y"),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> PortfolioHistoryResponse:
    return PortfolioService(session).history(user.id, account_id, period)
