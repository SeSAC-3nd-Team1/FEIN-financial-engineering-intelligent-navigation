from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import settings
from app.db.session import get_session
from app.integrations.ai import AzureOpenAIRebalancingClient
from app.models import User
from app.schemas.api import (
    PortfolioHomeResponse,
    PortfolioHistoryResponse,
    PortfolioResponse,
    PortfolioTransactionListResponse,
    RebalancingDecisionCreateRequest,
    RebalancingDecisionHistoryResponse,
    RebalancingDecisionResponse,
    StockEvaluationResponse,
)
from app.services.portfolio_analytics import PortfolioAnalyticsService
from app.services.portfolio import PortfolioService
from app.services.transactions import TransactionHistoryService

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def get_portfolio_analytics_service(session: Session = Depends(get_session)) -> PortfolioAnalyticsService:
    return PortfolioAnalyticsService(session)


def get_portfolio_service(session: Session = Depends(get_session)) -> PortfolioService:
    client = AzureOpenAIRebalancingClient(
        endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        deployment=settings.azure_openai_rebalancing_deployment,
        api_version=settings.azure_openai_api_version,
        timeout_seconds=settings.ai_rebalancing_timeout_seconds,
    )
    return PortfolioService(
        session,
        rebalancing_client=client,
        rebalancing_model_version=settings.ai_rebalancing_model_version,
    )


def get_transaction_history_service(
    session: Session = Depends(get_session),
) -> TransactionHistoryService:
    return TransactionHistoryService(session)


@router.get("/transactions", response_model=PortfolioTransactionListResponse)
def portfolio_transactions(
    account_id: UUID = Query(),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, min_length=1, max_length=500),
    user: User = Depends(current_user),
    service: TransactionHistoryService = Depends(get_transaction_history_service),
) -> PortfolioTransactionListResponse:
    return service.list(user.id, account_id, limit=limit, cursor=cursor)


@router.get("/home", response_model=PortfolioHomeResponse)
async def portfolio_home(
    account_id: UUID = Query(),
    period: Literal["1M", "3M", "1Y", "ALL"] = Query(default="3M"),
    sort_by: Literal["stock_name", "weight", "purchase_amount", "return_rate"] = Query(
        default="weight",
        alias="sort",
    ),
    order: Literal["asc", "desc"] = Query(default="desc"),
    user: User = Depends(current_user),
    service: PortfolioService = Depends(get_portfolio_service),
) -> PortfolioHomeResponse:
    return await service.home(user.id, account_id, period, sort_by, order)


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


@router.get("/stock-evaluation", response_model=StockEvaluationResponse)
def stock_evaluation(
    account_id: UUID = Query(),
    stock_code: str = Query(pattern=r"^[0-9A-Z]{6,12}$"),
    user: User = Depends(current_user),
    service: PortfolioAnalyticsService = Depends(get_portfolio_analytics_service),
) -> StockEvaluationResponse:
    return service.stock_evaluation(user.id, account_id, stock_code)


@router.get("/decisions", response_model=RebalancingDecisionHistoryResponse)
def rebalancing_decisions(
    account_id: UUID = Query(),
    user: User = Depends(current_user),
    service: PortfolioAnalyticsService = Depends(get_portfolio_analytics_service),
) -> RebalancingDecisionHistoryResponse:
    return service.decision_history(user.id, account_id)


@router.post("/decisions", response_model=RebalancingDecisionResponse, status_code=201)
def create_rebalancing_decision(
    request: RebalancingDecisionCreateRequest,
    user: User = Depends(current_user),
    service: PortfolioAnalyticsService = Depends(get_portfolio_analytics_service),
) -> RebalancingDecisionResponse:
    return service.record_decision(user.id, request)
