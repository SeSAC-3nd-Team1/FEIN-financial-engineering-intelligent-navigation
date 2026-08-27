from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User, VirtualAccount
from app.schemas.api import (
    AccountCreateRequest,
    AccountResponse,
    OperationMode,
    OperationModeSwitchRequest,
    OperationModeSwitchResponse,
    StrategySelectRequest,
)
from app.services.accounts import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


def get_account_service(session: Session = Depends(get_session)) -> AccountService:
    return AccountService(session)


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreateRequest,
    user: User = Depends(current_user),
    service: AccountService = Depends(get_account_service),
) -> VirtualAccount:
    return service.create(user.id, payload.account_name, payload.operation_mode, payload.initial_deposit)


@router.get("/me/all", response_model=list[AccountResponse])
def all_my_accounts(
    user: User = Depends(current_user),
    service: AccountService = Depends(get_account_service),
) -> list[VirtualAccount]:
    return service.get_all_mine(user.id)


@router.get("/me", response_model=AccountResponse)
def my_account(
    operation_mode: OperationMode = Query(default="SEMI_AUTO"),
    user: User = Depends(current_user),
    service: AccountService = Depends(get_account_service),
) -> VirtualAccount:
    return service.get_mine(user.id, operation_mode)


@router.put("/me/active-operation-mode", response_model=OperationModeSwitchResponse)
def switch_active_operation_mode(
    payload: OperationModeSwitchRequest,
    user: User = Depends(current_user),
    service: AccountService = Depends(get_account_service),
) -> OperationModeSwitchResponse:
    return service.switch_active_operation_mode(user.id, payload.operation_mode)


@router.put("/{account_id}/strategy", response_model=AccountResponse)
def select_strategy(
    account_id: UUID,
    payload: StrategySelectRequest,
    user: User = Depends(current_user),
    service: AccountService = Depends(get_account_service),
) -> VirtualAccount:
    return service.select_strategy(user.id, account_id, payload.strategy_id)
