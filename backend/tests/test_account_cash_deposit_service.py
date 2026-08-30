"""전략과 무관한 계좌 현금 입금의 잔액 처리와 멱등성을 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.models import AccountCashDeposit, CashLedger, VirtualAccount
from app.schemas.api import AccountCashDepositRequest
from app.services.accounts import AccountService


NOW = datetime(2026, 8, 28, tzinfo=UTC)


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []

    def add(self, value) -> None:
        self.added.append(value)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, value) -> None:
        self.refreshed.append(value)


class FakeRepository:
    def __init__(self, account, existing=None) -> None:
        self.account = account
        self.existing = existing
        self.calls = []

    def owned_account(self, account_id, user_id, *, lock=False):
        self.calls.append(("account", account_id, user_id, lock))
        return self.account

    def account_cash_deposit_by_idempotency(self, account_id, key):
        self.calls.append(("deposit", account_id, key))
        return self.existing


def cash_account() -> VirtualAccount:
    return VirtualAccount(
        id=uuid4(),
        user_id=7,
        account_name="전략 없는 계좌",
        operation_mode="SEMI_AUTO",
        initial_cash=Decimal("0"),
        cash_balance=Decimal("0"),
        invested_principal=Decimal("0"),
        status="ACTIVE",
        selected_strategy_id=None,
        created_at=NOW,
        updated_at=NOW,
    )


def request(amount: int = 500_000) -> AccountCashDepositRequest:
    return AccountCashDepositRequest(
        amount=amount,
        idempotency_key="cash-deposit-once",
    )


def test_deposit_cash_updates_cash_account_without_selecting_strategy() -> None:
    account = cash_account()
    session = FakeSession()
    service = AccountService(session)  # type: ignore[arg-type]
    service.repo = FakeRepository(account)

    result = service.deposit_cash(7, account.id, request())

    assert result.account.selected_strategy_id is None
    assert result.amount == Decimal("500000.00")
    assert result.balance_after == Decimal("500000.00")
    assert account.initial_cash == Decimal("500000.00")
    assert account.cash_balance == Decimal("500000.00")
    assert account.invested_principal == Decimal("500000.00")
    assert isinstance(session.added[0], AccountCashDeposit)
    assert isinstance(session.added[1], CashLedger)
    assert session.added[1].reference_type == "ACCOUNT_CASH_DEPOSIT"
    assert session.commits == 1
    assert session.rollbacks == 0
    assert ("account", account.id, 7, True) in service.repo.calls


def test_deposit_cash_replays_same_request_without_duplicate_records() -> None:
    account = cash_account()
    account.cash_balance = Decimal("500000")
    account.initial_cash = Decimal("500000")
    account.invested_principal = Decimal("500000")
    existing = SimpleNamespace(
        id=uuid4(),
        amount=Decimal("500000"),
        balance_after=Decimal("500000"),
    )
    session = FakeSession()
    service = AccountService(session)  # type: ignore[arg-type]
    service.repo = FakeRepository(account, existing)

    result = service.deposit_cash(7, account.id, request())

    assert result.deposit_id == existing.id
    assert result.balance_after == Decimal("500000")
    assert session.added == []
    assert session.commits == 1
    assert session.rollbacks == 0


def test_deposit_cash_rejects_reused_key_with_different_amount() -> None:
    account = cash_account()
    existing = SimpleNamespace(
        id=uuid4(),
        amount=Decimal("500000"),
        balance_after=Decimal("500000"),
    )
    session = FakeSession()
    service = AccountService(session)  # type: ignore[arg-type]
    service.repo = FakeRepository(account, existing)

    with pytest.raises(ServiceError) as error:
        service.deposit_cash(7, account.id, request(700_000))

    assert error.value.code == "DEPOSIT_IDEMPOTENCY_CONFLICT"
    assert error.value.status_code == 409
    assert session.added == []
    assert session.commits == 0
    assert session.rollbacks == 1
