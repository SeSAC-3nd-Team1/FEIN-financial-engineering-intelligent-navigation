from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories.backtest import BacktestRepository
from app.schemas.api import BacktestRunRequest, BacktestRunResponse
from app.services.backtest import BacktestService

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.post("/run", response_model=BacktestRunResponse)
def run_backtest(request: BacktestRunRequest, session: Session = Depends(get_session)) -> BacktestRunResponse:
    return BacktestService(BacktestRepository(session)).run(request)
