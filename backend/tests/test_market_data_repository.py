"""시장 데이터 repository의 조회 계약을 검증한다."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Company, StockDividend
from app.repositories.market_data import MarketDataRepository


def test_latest_dividend_prioritizes_year_annual_report_and_common_stock() -> None:
    class FakeSession:
        def scalar(self, query):
            self.query = query
            return None

    session = FakeSession()

    MarketDataRepository(session).latest_dividend("005930")

    sql = str(session.query)
    assert "stock_dividends.stock_code" in sql
    assert "stock_dividends.business_year DESC" in sql
    assert "stock_dividends.report_code" in sql
    assert "stock_dividends.stock_kind" in sql
    assert "stock_dividends.report_code =" in sql
    assert "stock_dividends.stock_kind =" in sql


def test_latest_dividend_returns_previous_common_when_latest_is_preferred() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Company.__table__.create(engine)
    StockDividend.__table__.create(engine)
    collected_at = datetime(2026, 8, 26, tzinfo=UTC)

    with Session(engine) as session:
        session.add(
            Company(
                id=1, corp_code="00126380", stock_code="005930", corp_name="삼성전자"
            )
        )
        session.add_all(
            [
                StockDividend(
                    id=1,
                    stock_code="005930",
                    corp_code="00126380",
                    business_year="2025",
                    report_code="11011",
                    stock_kind="PREFERRED",
                    reported_dividend_yield=Decimal("1.9"),
                    source="OpenDART_ALOT_MATTER",
                    collected_at=collected_at,
                ),
                StockDividend(
                    id=2,
                    stock_code="005930",
                    corp_code="00126380",
                    business_year="2024",
                    report_code="11011",
                    stock_kind="COMMON",
                    reported_dividend_yield=Decimal("1.5"),
                    source="OpenDART_ALOT_MATTER",
                    collected_at=collected_at,
                ),
            ]
        )
        session.commit()

        result = MarketDataRepository(session).latest_dividend("005930")

        assert result is not None
        assert result.business_year == "2024"
        assert result.stock_kind == "COMMON"
        assert result.reported_dividend_yield == Decimal("1.5")


def test_kospi_since_filters_sorts_and_deduplicates_trade_dates() -> None:
    rows = [
        SimpleNamespace(
            id=3, trade_date=date(2026, 8, 22), close_value=Decimal("3040")
        ),
        SimpleNamespace(
            id=1, trade_date=date(2026, 8, 20), close_value=Decimal("3000")
        ),
        SimpleNamespace(
            id=2, trade_date=date(2026, 8, 20), close_value=Decimal("3010")
        ),
    ]

    class FakeSession:
        def scalars(self, query):
            self.query = query
            return rows

    session = FakeSession()

    result = MarketDataRepository(session).kospi_since(date(2026, 8, 20))

    assert [(row.trade_date, row.close_value) for row in result] == [
        (date(2026, 8, 20), Decimal("3010")),
        (date(2026, 8, 22), Decimal("3040")),
    ]
    assert "market_indices.trade_date >=" in str(session.query)
    assert "ORDER BY market_indices.trade_date, market_indices.id" in str(session.query)
