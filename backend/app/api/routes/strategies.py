from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import Strategy
from app.repositories import TradingRepository
from app.schemas.api import StrategyResponse

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyResponse])
def list_strategies(session: Session = Depends(get_session)) -> list[Strategy]:
    return TradingRepository(session).strategies()
