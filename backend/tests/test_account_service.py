"""활성 운용방식 전환의 계좌 보존과 멱등 동작을 검증한다."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.models import VirtualAccount
from app.services.accounts import AccountService


NOW = datetime(2026, 8, 25, tzinfo=UTC)
DEFAULT_ONBOARDING = object()


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.refreshed = []

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def refresh(self, value) -> None:
        self.refreshed.append(value)


class FakeRepository:
    def __init__(self, user, account, onboarding=DEFAULT_ONBOARDING) -> None:
        self._user = user
        self._account = account
        if onboarding is DEFAULT_ONBOARDING:
            self._onboarding = (
                SimpleNamespace(account_id=account.id) if account is not None else None
            )
        else:
            self._onboarding = onboarding
        self.calls = []

    def user(self, user_id, *, lock=False):
        self.calls.append(("user", user_id, lock))
        return self._user

    def account_for_user(self, user_id, operation_mode, *, lock=False):
        self.calls.append(("account", user_id, operation_mode, lock))
        return self._account

    def completed_onboarding_for_user_mode(self, user_id, operation_mode):
        self.calls.append(("onboarding", user_id, operation_mode))
        return self._onboarding


def account(operation_mode: str = "AUTO", status: str = "ACTIVE") -> VirtualAccount:
    return VirtualAccount(
        id=uuid4(),
        user_id=7,
        account_name=f"{operation_mode} 계좌",
        operation_mode=operation_mode,
        initial_cash=Decimal("1000000"),
        cash_balance=Decimal("750000"),
        status=status,
        selected_strategy_id="low",
        created_at=NOW,
        updated_at=NOW,
    )


def test_switch_active_operation_mode_preserves_target_account() -> None:
    user = SimpleNamespace(
        id=7,
        active_operation_mode="SEMI_AUTO",
        operation_mode_changed_at=NOW,
    )
    target_account = account()
    session = FakeSession()
    service = AccountService(session)
    service.repo = FakeRepository(user, target_account)

    result = service.switch_active_operation_mode(7, "AUTO")

    assert result.previous_operation_mode == "SEMI_AUTO"
    assert result.operation_mode == "AUTO"
    assert result.changed is True
    assert result.account.id == target_account.id
    assert result.notice.code == "OPERATION_MODE_CHANGED"
    assert "자산과 거래내역은 이동하지 않고 그대로 유지" in result.notice.message
    assert user.active_operation_mode == "AUTO"
    assert target_account.operation_mode == "AUTO"
    assert target_account.cash_balance == Decimal("750000")
    assert ("user", 7, True) in service.repo.calls
    assert ("account", 7, "AUTO", False) in service.repo.calls
    assert session.commits == 1
    assert session.rollbacks == 0


def test_switch_active_operation_mode_is_idempotent() -> None:
    user = SimpleNamespace(
        id=7,
        active_operation_mode="AUTO",
        operation_mode_changed_at=NOW,
    )
    session = FakeSession()
    service = AccountService(session)
    service.repo = FakeRepository(user, account())

    result = service.switch_active_operation_mode(7, "AUTO")

    assert result.changed is False
    assert result.changed_at == NOW
    assert result.notice.code == "OPERATION_MODE_UNCHANGED"
    assert session.commits == 0
    assert session.rollbacks == 0


def test_switch_rejects_mode_without_separate_account() -> None:
    user = SimpleNamespace(
        id=7,
        active_operation_mode="SEMI_AUTO",
        operation_mode_changed_at=NOW,
    )
    session = FakeSession()
    service = AccountService(session)
    service.repo = FakeRepository(user, None)

    with pytest.raises(ServiceError) as error:
        service.switch_active_operation_mode(7, "AUTO")

    assert error.value.code == "OPERATION_MODE_ACCOUNT_NOT_READY"
    assert error.value.status_code == 409
    assert user.active_operation_mode == "SEMI_AUTO"
    assert session.commits == 0
    assert session.rollbacks == 1


def test_switch_rejects_inactive_target_account() -> None:
    user = SimpleNamespace(
        id=7,
        active_operation_mode="SEMI_AUTO",
        operation_mode_changed_at=NOW,
    )
    session = FakeSession()
    service = AccountService(session)
    service.repo = FakeRepository(user, account(status="SUSPENDED"))

    with pytest.raises(ServiceError) as error:
        service.switch_active_operation_mode(7, "AUTO")

    assert error.value.code == "OPERATION_MODE_ACCOUNT_NOT_ACTIVE"
    assert error.value.status_code == 409
    assert session.commits == 0
    assert session.rollbacks == 1


def test_switch_rejects_incomplete_target_onboarding() -> None:
    user = SimpleNamespace(
        id=7,
        active_operation_mode="SEMI_AUTO",
        operation_mode_changed_at=NOW,
    )
    session = FakeSession()
    service = AccountService(session)
    service.repo = FakeRepository(user, account(), onboarding=None)

    with pytest.raises(ServiceError) as error:
        service.switch_active_operation_mode(7, "AUTO")

    assert error.value.code == "OPERATION_MODE_ACCOUNT_NOT_READY"
    assert error.value.status_code == 409
    assert session.commits == 0
    assert session.rollbacks == 1
