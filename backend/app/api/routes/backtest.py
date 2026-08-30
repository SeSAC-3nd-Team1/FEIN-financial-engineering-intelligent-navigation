from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_session
from app.integrations.ai import AzureOpenAIBacktestExplanationClient
from app.repositories.backtest import BacktestRepository
from app.schemas.api import (
    BacktestAiExplanationResponse,
    BacktestAiInput,
    BacktestAvailableRangeResponse,
    BacktestRunRequest,
    BacktestRunResponse,
)
from app.services.backtest import BacktestService
from app.services.backtest_explanation import BacktestExplanationService


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


def get_backtest_explanation_service() -> BacktestExplanationService:
    client = AzureOpenAIBacktestExplanationClient(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        deployment=settings.azure_openai_backtest_explanation_deployment
        or settings.azure_openai_recommendation_deployment,
        api_version=settings.azure_openai_api_version,
        timeout_seconds=settings.ai_backtest_explanation_timeout_seconds,
    )
    return BacktestExplanationService(client)


@router.post("/explain", response_model=BacktestAiExplanationResponse)
async def explain_backtest(
    request: BacktestAiInput,
    service: BacktestExplanationService = Depends(get_backtest_explanation_service),
) -> BacktestAiExplanationResponse:
    return await service.explain(request)




