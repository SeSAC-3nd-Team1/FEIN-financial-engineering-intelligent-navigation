"""개발용 Mock 포트폴리오 seed의 비중·수량·멱등 키를 검증한다."""

from decimal import Decimal

import pytest

from scripts.seed_demo_portfolio import (
    DEMO_ALLOCATIONS,
    allocation_quantity,
    ensure_demo_environment,
    idempotency_key,
)


def test_demo_allocations_preserve_original_mock_weights_and_cash() -> None:
    assert len(DEMO_ALLOCATIONS) == 20
    assert sum((weight for _, _, weight in DEMO_ALLOCATIONS), Decimal("0")) == Decimal("0.970")
    assert len({stock_code for stock_code, _, _ in DEMO_ALLOCATIONS}) == len(DEMO_ALLOCATIONS)


def test_allocation_quantity_uses_fractional_shares_without_exceeding_target() -> None:
    quantity = allocation_quantity(Decimal("10000000"), Decimal("0.18"), Decimal("78400"))

    assert quantity == Decimal("22.95918367")
    assert quantity * Decimal("78400") <= Decimal("1800000")


def test_demo_seed_requires_explicit_opt_in_and_fails_closed_for_unknown_environments() -> None:
    with pytest.raises(RuntimeError, match="DEMO_SEED_ENABLED"):
        ensure_demo_environment("", "development")
    for environment in ("", "production", "unknown"):
        with pytest.raises(RuntimeError, match="명시적인 개발 환경"):
            ensure_demo_environment("true", environment)
    ensure_demo_environment("true", "development")



def test_idempotency_key_is_stable_per_portfolio_version_and_stock() -> None:
    assert idempotency_key("005930") == "demo-mock-holdings-v1-005930"
    assert idempotency_key("005930") == idempotency_key("005930")
