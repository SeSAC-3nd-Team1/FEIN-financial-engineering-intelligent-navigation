from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User, VirtualAccount
from app.schemas.api import (
    AccountCashDepositRequest,
    AccountCashDepositResponse,
    AccountCreateRequest,
    AccountResponse,
    FundOperationRequest,
    FundOperationResponse,
    FundSummaryResponse,
    OperationMode,
    OperationModeSwitchRequest,
    OperationModeSwitchResponse,
    StrategySelectRequest,
)
from app.services.accounts import AccountService
from app.services.funds import FundOperationService

router = APIRouter(prefix="/accounts", tags=["accounts"])


def get_account_service(session: Session = Depends(get_session)) -> AccountService:
    return AccountService(session)


def get_fund_operation_service(
    session: Session = Depends(get_session),
) -> FundOperationService:
    return FundOperationService(session)


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreateRequest,
    user: User = Depends(current_user),
    service: AccountService = Depends(get_account_service),
) -> VirtualAccount:
    return service.create(user.id, payload.account_name, payload.operation_mode)


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


@router.post(
    "/{account_id}/deposits",
    response_model=AccountCashDepositResponse,
    status_code=status.HTTP_201_CREATED,
)
def deposit_virtual_cash(
    account_id: UUID,
    payload: AccountCashDepositRequest,
    user: User = Depends(current_user),
    service: AccountService = Depends(get_account_service),
) -> AccountCashDepositResponse:
    return service.deposit_cash(user.id, account_id, payload)


@router.get("/{account_id}/funds", response_model=FundSummaryResponse)
def virtual_fund_summary(
    account_id: UUID,
    user: User = Depends(current_user),
    service: FundOperationService = Depends(get_fund_operation_service),
) -> FundSummaryResponse:
    return service.summary(user.id, account_id)


@router.post(
    "/{account_id}/additional-investments",
    response_model=FundOperationResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_virtual_investment(
    account_id: UUID,
    payload: FundOperationRequest,
    user: User = Depends(current_user),
    service: FundOperationService = Depends(get_fund_operation_service),
) -> FundOperationResponse:
    return service.add_investment(user.id, account_id, payload)


@router.post(
    "/{account_id}/withdrawals",
    response_model=FundOperationResponse,
    status_code=status.HTTP_201_CREATED,
)
def withdraw_virtual_funds(
    account_id: UUID,
    payload: FundOperationRequest,
    user: User = Depends(current_user),
    service: FundOperationService = Depends(get_fund_operation_service),
) -> FundOperationResponse:
    return service.withdraw(user.id, account_id, payload)
