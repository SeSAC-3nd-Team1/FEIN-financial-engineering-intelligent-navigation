"""포트폴리오 평가 계산을 검증한다."""

from decimal import Decimal

from app.services.portfolio import calculate_return


def test_return_rate() -> None:
    assert calculate_return(Decimal("25000"), Decimal("100000")) == Decimal("25.00")


def test_zero_purchase_return_is_zero() -> None:
    assert calculate_return(Decimal("100"), Decimal("0")) == Decimal("0")
