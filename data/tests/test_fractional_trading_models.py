"""가상거래 수량 컬럼이 소수점 8자리 계약을 공유하는지 검증한다."""

from sqlalchemy import Numeric

from db.models import Execution, Order, Position


def test_trading_quantities_support_eight_decimal_places() -> None:
    for model in (Position, Order, Execution):
        quantity_type = model.__table__.columns.quantity.type
        assert isinstance(quantity_type, Numeric)
        assert quantity_type.precision == 20
        assert quantity_type.scale == 8
