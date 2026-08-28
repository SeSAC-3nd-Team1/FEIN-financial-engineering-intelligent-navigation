"""전략 카탈로그 상태가 실제 계좌 선택 가능 여부를 결정하는지 검증한다."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import ServiceError
from app.services.accounts import AccountService


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class FakeRepository:
    def __init__(self, availability_status: str) -> None:
        self.account = SimpleNamespace(id=uuid4(), selected_strategy_id=None)
        self.catalog_strategy = SimpleNamespace(
            id="value",
            is_active=True,
            availability_status=availability_status,
        )

    def owned_account(self, *_args, **_kwargs):
        return self.account

    def strategy(self, _strategy_id):
        return self.catalog_strategy


def test_testing_strategy_cannot_be_selected() -> None:
    session = FakeSession()
    service = AccountService(session)  # type: ignore[arg-type]
    service.repo = FakeRepository("TESTING")  # type: ignore[assignment]

    with pytest.raises(ServiceError) as raised:
        service.select_strategy(7, service.repo.account.id, "value")  # type: ignore[attr-defined]

    assert raised.value.code == "STRATEGY_NOT_AVAILABLE"
    assert session.commits == 0
    assert session.rollbacks == 1


def test_available_strategy_is_selected() -> None:
    session = FakeSession()
    service = AccountService(session)  # type: ignore[arg-type]
    service.repo = FakeRepository("AVAILABLE")  # type: ignore[assignment]

    account = service.select_strategy(7, service.repo.account.id, "value")  # type: ignore[attr-defined]

    assert account.selected_strategy_id == "value"
    assert session.commits == 1
    assert session.rollbacks == 0
