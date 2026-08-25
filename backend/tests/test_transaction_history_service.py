"""거래내역 cursor와 체결 응답 변환을 검증한다."""

from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import NotFoundError, ServiceError
from app.repositories.trading import ExecutionHistoryRecord
from app.services.transactions import (
    TransactionHistoryService,
    decode_transaction_cursor,
    encode_transaction_cursor,
)


def record(execution_id: int, executed_at: datetime, *, stock_name: str | None = "삼성전자"):
    return ExecutionHistoryRecord(
        execution=SimpleNamespace(
            id=execution_id,
            order_id=uuid4(),
            stock_code="005930",
            side="BUY",
            quantity=Decimal("1.25"),
            execution_price=Decimal("70000"),
            executed_at=executed_at,
        ),
        stock_name=stock_name,
    )


def test_transaction_cursor_round_trip() -> None:
    executed_at = datetime(2026, 8, 25, 10, 30, tzinfo=UTC)

    cursor = encode_transaction_cursor(executed_at, 42)

    assert decode_transaction_cursor(cursor) == (executed_at, 42)


@pytest.mark.parametrize("cursor", ["not-json", "e30", "eyJleGVjdXRlZF9hdCI6IjIwMjYtMDgtMjUifQ"])
def test_invalid_transaction_cursor_is_rejected(cursor: str) -> None:
    with pytest.raises(ServiceError) as error:
        decode_transaction_cursor(cursor)

    assert error.value.code == "INVALID_TRANSACTION_CURSOR"
    assert error.value.status_code == 422


def test_transaction_cursor_rejects_coerced_id_type() -> None:
    cursor = urlsafe_b64encode(json.dumps({
        "executed_at": "2026-08-25T10:30:00+00:00",
        "id": "42",
    }).encode()).decode().rstrip("=")

    with pytest.raises(ServiceError) as error:
        decode_transaction_cursor(cursor)

    assert error.value.code == "INVALID_TRANSACTION_CURSOR"


def test_transaction_history_returns_amount_and_next_cursor() -> None:
    account_id = uuid4()
    latest = datetime(2026, 8, 25, 10, 30, tzinfo=UTC)
    records = [
        record(3, latest),
        record(2, latest - timedelta(minutes=1), stock_name=None),
        record(1, latest - timedelta(minutes=2)),
    ]

    class FakeRepo:
        def owned_account(self, *_args):
            return object()

        def execution_history(self, account_id_arg, **kwargs):
            self.call = (account_id_arg, kwargs)
            return records

    service = TransactionHistoryService.__new__(TransactionHistoryService)
    service.repo = FakeRepo()

    result = service.list(7, account_id, limit=2, cursor=None)

    assert service.repo.call == (
        account_id,
        {"limit": 3, "before_executed_at": None, "before_id": None},
    )
    assert result.has_more is True
    assert len(result.items) == 2
    assert result.items[0].transaction_amount == Decimal("87500.00")
    assert result.items[1].stock_name is None
    assert decode_transaction_cursor(result.next_cursor) == (
        records[1].execution.executed_at,
        2,
    )


def test_transaction_history_applies_cursor_to_repository() -> None:
    account_id = uuid4()
    executed_at = datetime(2026, 8, 25, 10, 30, tzinfo=UTC)
    cursor = encode_transaction_cursor(executed_at, 9)

    class FakeRepo:
        def owned_account(self, *_args):
            return object()

        def execution_history(self, account_id_arg, **kwargs):
            self.call = (account_id_arg, kwargs)
            return []

    service = TransactionHistoryService.__new__(TransactionHistoryService)
    service.repo = FakeRepo()

    result = service.list(7, account_id, limit=20, cursor=cursor)

    assert service.repo.call[1]["before_executed_at"] == executed_at
    assert service.repo.call[1]["before_id"] == 9
    assert result.has_more is False
    assert result.next_cursor is None


def test_transaction_history_rejects_unowned_account_before_query() -> None:
    class FakeRepo:
        def owned_account(self, *_args):
            return None

        def execution_history(self, *_args, **_kwargs):
            raise AssertionError("unowned account must not query executions")

    service = TransactionHistoryService.__new__(TransactionHistoryService)
    service.repo = FakeRepo()

    with pytest.raises(NotFoundError) as error:
        service.list(7, uuid4(), limit=20, cursor=None)

    assert error.value.code == "ACCOUNT_NOT_FOUND"
