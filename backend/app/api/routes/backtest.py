from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories.backtest import BacktestRepository
from app.schemas.api import BacktestAvailableRangeResponse, BacktestRunRequest, BacktestRunResponse
from app.services.backtest import BacktestService

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/available-range", response_model=BacktestAvailableRangeResponse)
def get_available_range(
    strategy_id: str | None = Query(default=None, alias="strategyId"),
    session: Session = Depends(get_session),
) -> BacktestAvailableRangeResponse:
    return BacktestService(BacktestRepository(session)).available_range(strategy_id)


@router.post("/run", response_model=BacktestRunResponse)
def run_backtest(request: BacktestRunRequest, session: Session = Depends(get_session)) -> BacktestRunResponse:
    return BacktestService(BacktestRepository(session)).run(request)
