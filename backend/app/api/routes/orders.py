from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.errors import NotFoundError
from app.db.session import get_session
from app.models import Execution, Order, User
from app.repositories import TradingRepository
from app.schemas.api import ExecutionResponse, OrderCreateRequest, OrderResponse
from app.services.trading import TradingService

router = APIRouter(tags=["orders"])


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreateRequest, user: User = Depends(current_user), session: Session = Depends(get_session)) -> Order:
    return TradingService(session).execute_market_order(user.id, payload)


@router.get("/orders", response_model=list[OrderResponse])
def list_orders(account_id: UUID = Query(), user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[Order]:
    if not TradingRepository(session).owned_account(account_id, user.id):
        raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
    return list(session.scalars(select(Order).where(Order.account_id == account_id).order_by(Order.requested_at.desc())))


@router.get("/executions", response_model=list[ExecutionResponse])
def list_executions(account_id: UUID = Query(), user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[Execution]:
    if not TradingRepository(session).owned_account(account_id, user.id):
        raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
    return list(session.scalars(select(Execution).where(Execution.account_id == account_id).order_by(Execution.executed_at.desc())))
