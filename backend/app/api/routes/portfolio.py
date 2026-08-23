from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.schemas.api import PortfolioResponse
from app.services.portfolio import PortfolioService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioResponse)
def portfolio(account_id: UUID = Query(), user: User = Depends(current_user), session: Session = Depends(get_session)) -> PortfolioResponse:
    return PortfolioService(session).evaluate(user.id, account_id)
