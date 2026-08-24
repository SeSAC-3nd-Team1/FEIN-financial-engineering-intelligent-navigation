"""KIS·KRX·OpenDART 조합 Stock summary/chart 규칙을 검증한다."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.integrations.kis.models import CurrentQuote, MinuteCandle
from app.services.market import StockMarketService, _positive_ratio


class FakeRepository:
    def __init__(self, *, financial=True, prices=True) -> None:
        today = date.today()
        self._stock = SimpleNamespace(
            stock_code="005930", stock_name="삼성전자", market="KOSPI",
            sector="전기전자", listing_date=date(1975, 6, 11), listed_shares=5_969_782_550,
            security_type="주권", source="KRX", as_of=today,
        )
        self._price = SimpleNamespace(
            trade_date=today, open_price=Decimal("73000"), high_price=Decimal("74200"),
            low_price=Decimal("72800"), close_price=Decimal("73800"), volume=12_345_678,
            market_cap=Decimal("438000000000000"), source="KRX", as_of=today,
        )
        self._company = SimpleNamespace(
            corp_name="삼성전자", established_date=date(1969, 1, 13), industry_code="264",
        )
        self._financial = SimpleNamespace(
            business_year="2025", net_income=Decimal("30000000000000"),
            total_equity=Decimal("360000000000000"),
        ) if financial else None
        self._prices = [self._price] if prices else []

    def stock(self, stock_code: str):
        return self._stock if stock_code == "005930" else None

    def latest_price(self, _stock_code: str):
        return self._price

    def company(self, _stock_code: str):
        return self._company

    def latest_annual_financial(self, _stock_code: str):
        return self._financial

    def prices_since(self, _stock_code: str, _start_date: date):
        return self._prices


class FakeLiveMarket:
    def get_quote(self, stock_code: str) -> CurrentQuote:
        return CurrentQuote(
            stock_code=stock_code, price=Decimal("73400"), previous_close=Decimal("72200"),
            change_amount=Decimal("1200"), change_rate=Decimal("1.66"), volume=12345678,
            as_of=datetime(2026, 8, 24, tzinfo=UTC), source="KIS_REST",
        )

    def get_minute_candles(self, stock_code: str, limit: int):
        assert limit == 390
        now = datetime(2026, 8, 24, tzinfo=UTC)
        return [MinuteCandle(
            stock_code=stock_code, started_at=now, open=Decimal("73000"),
            high=Decimal("73500"), low=Decimal("72900"), close=Decimal("73400"),
            volume=100, is_closed=False,
        )], now, "KIS"


def test_summary_combines_real_sources_and_calculates_metrics() -> None:
    result = StockMarketService(FakeRepository(), FakeLiveMarket()).summary("005930")

    assert result.stock_name == "삼성전자"
    assert result.price == Decimal("73400")
    assert result.market_cap == Decimal("438000000000000")
    assert result.per == Decimal("14.6")
    assert result.pbr == pytest.approx(Decimal("1.216666666666666666666666667"))
    assert result.roe == pytest.approx(Decimal("8.333333333333333333333333333"))
    assert result.dividend_yield is None
    assert result.sources == {"price": "KIS_REST", "market": "KRX", "financial": "OpenDART"}


@pytest.mark.parametrize(
    ("numerator", "denominator"),
    [(Decimal("1"), Decimal("0")), (Decimal("1"), Decimal("-1")), (None, Decimal("1"))],
)
def test_financial_ratio_returns_null_for_missing_or_nonpositive_denominator(numerator, denominator) -> None:
    assert _positive_ratio(numerator, denominator) is None


def test_summary_returns_null_financial_metrics_when_statement_is_missing() -> None:
    result = StockMarketService(FakeRepository(financial=False), FakeLiveMarket()).summary("005930")

    assert result.per is None
    assert result.pbr is None
    assert result.roe is None
    assert result.sources["financial"] is None


def test_historical_chart_uses_only_repository_prices() -> None:
    result = StockMarketService(FakeRepository(), FakeLiveMarket()).chart("005930", "3M")

    assert result.source == "KRX"
    assert len(result.items) == 1
    assert result.items[0].close == Decimal("73800")


def test_one_day_chart_uses_kis_minute_candles() -> None:
    result = StockMarketService(FakeRepository(), FakeLiveMarket()).chart("005930", "1D")

    assert result.source == "KIS"
    assert result.items[0].date == "2026-08-24T00:00:00+00:00"
    assert result.items[0].close == Decimal("73400")
