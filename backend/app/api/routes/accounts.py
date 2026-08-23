from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User, VirtualAccount
from app.schemas.api import AccountCreateRequest, AccountResponse, StrategySelectRequest
from app.services.accounts import AccountService

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(payload: AccountCreateRequest, user: User = Depends(current_user), session: Session = Depends(get_session)) -> VirtualAccount:
    return AccountService(session).create(user.id, payload.account_name)


@router.get("/me", response_model=AccountResponse)
def my_account(user: User = Depends(current_user), session: Session = Depends(get_session)) -> VirtualAccount:
    return AccountService(session).get_mine(user.id)


@router.put("/{account_id}/strategy", response_model=AccountResponse)
def select_strategy(account_id: UUID, payload: StrategySelectRequest, user: User = Depends(current_user), session: Session = Depends(get_session)) -> VirtualAccount:
    return AccountService(session).select_strategy(user.id, account_id, payload.strategy_id)
