"""KIS·KRX·OpenDART 조합 Stock summary/chart 규칙을 검증한다."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.integrations.kis.models import CurrentQuote, MinuteCandle
from app.services.market import StockMarketService, _dividend_yield, _positive_ratio


class FakeRepository:
    def __init__(self, *, financial=True, prices=True, dividend=True) -> None:
        today = date.today()
        self._stock = SimpleNamespace(
            stock_code="005930",
            stock_name="삼성전자",
            market="KOSPI",
            sector="전기전자",
            listing_date=date(1975, 6, 11),
            listed_shares=5_969_782_550,
            security_type="주권",
            source="KRX",
            as_of=today,
        )
        self._price = SimpleNamespace(
            trade_date=today,
            open_price=Decimal("73000"),
            high_price=Decimal("74200"),
            low_price=Decimal("72800"),
            close_price=Decimal("73800"),
            volume=12_345_678,
            market_cap=Decimal("438000000000000"),
            source="KRX",
            as_of=today,
        )
        self._company = SimpleNamespace(
            corp_name="삼성전자",
            established_date=date(1969, 1, 13),
            industry_code="264",
        )
        self._financial = (
            SimpleNamespace(
                business_year="2025",
                net_income=Decimal("30000000000000"),
                total_equity=Decimal("360000000000000"),
            )
            if financial
            else None
        )
        self._dividend = (
            SimpleNamespace(
                dividend_per_share=Decimal("1500"),
                reported_dividend_yield=Decimal("1.8"),
                source="OpenDART_ALOT_MATTER",
            )
            if dividend
            else None
        )
        self._prices = [self._price] if prices else []
        self.requested_start_date = None

    def stock(self, stock_code: str):
        return self._stock if stock_code == "005930" else None

    def latest_price(self, _stock_code: str):
        return self._price

    def company(self, _stock_code: str):
        return self._company

    def latest_annual_financial(self, _stock_code: str):
        return self._financial

    def latest_dividend(self, _stock_code: str):
        return self._dividend

    def prices_since(self, _stock_code: str, _start_date: date):
        self.requested_start_date = _start_date
        return self._prices


class FakeLiveMarket:
    def __init__(self, *, price: Decimal | None = Decimal("75000")) -> None:
        self.price = price

    def get_quote(self, stock_code: str):
        if self.price is None:
            raise RuntimeError("KIS unavailable")
        return CurrentQuote(
            stock_code=stock_code,
            price=self.price,
            previous_close=None,
            change_amount=None,
            change_rate=None,
            volume=None,
            as_of=datetime(2026, 8, 26, tzinfo=UTC),
            source="KIS_WS",
        )

    def get_minute_candles(self, stock_code: str, limit: int):
        assert limit == 390
        now = datetime(2026, 8, 24, tzinfo=UTC)
        return (
            [
                MinuteCandle(
                    stock_code=stock_code,
                    started_at=now,
                    open=Decimal("73000"),
                    high=Decimal("73500"),
                    low=Decimal("72900"),
                    close=Decimal("73400"),
                    volume=100,
                    is_closed=False,
                )
            ],
            now,
            "KIS",
        )


class UnavailableRepository:
    def stock(self, _stock_code: str):
        raise AssertionError("1D KIS chart must not query the KRX repository")


def test_summary_combines_real_sources_and_calculates_metrics() -> None:
    result = StockMarketService(FakeRepository(), FakeLiveMarket()).summary("005930")

    assert result.stock_name == "삼성전자"
    assert result.price == Decimal("75000")
    assert result.previous_close is None
    assert result.change_amount is None
    assert result.change_rate is None
    assert result.volume is None

    assert result.market_cap == Decimal("438000000000000")
    assert result.per == Decimal("14.6")
    assert result.pbr == pytest.approx(Decimal("1.216666666666666666666666667"))
    assert result.roe == pytest.approx(Decimal("8.333333333333333333333333333"))
    assert result.dividend_yield == Decimal("1.8")
    assert result.sources == {
                "price": "KIS_WS",

        "market": "KRX",
                "financial": "OpenDART",
        "per": "OpenDART",
        "pbr": "OpenDART",
        "roe": "OpenDART",
        "dividend": "OpenDART_ALOT_MATTER",

        "dividend_price": None,
    }


@pytest.mark.parametrize(
    ("numerator", "denominator"),
    [(Decimal("1"), Decimal("0")), (Decimal("1"), Decimal("-1")), (None, Decimal("1"))],
)
def test_financial_ratio_returns_null_for_missing_or_nonpositive_denominator(
    numerator, denominator
) -> None:
    assert _positive_ratio(numerator, denominator) is None


def test_dividend_yield_uses_krx_close_when_reported_yield_is_missing() -> None:
    repository = FakeRepository()
    repository._dividend.reported_dividend_yield = None

    result = StockMarketService(repository, FakeLiveMarket(price=None)).summary(
        "005930"
    )

    assert result.dividend_yield == Decimal("1500") / Decimal("73800") * Decimal("100")
    assert result.sources["dividend_price"] == "KRX"


def test_dividend_yield_uses_reported_value_without_dps() -> None:
    repository = FakeRepository()
    repository._dividend.dividend_per_share = None

    result = StockMarketService(repository, FakeLiveMarket()).summary("005930")

    assert result.dividend_yield == Decimal("1.8")


def test_dividend_yield_is_null_without_dividend_data() -> None:
    result = StockMarketService(
        FakeRepository(dividend=False), FakeLiveMarket()
    ).summary("005930")

    assert result.dividend_yield is None


def test_dividend_repository_failure_does_not_break_summary() -> None:
    repository = FakeRepository()
    repository.latest_dividend = lambda _stock_code: (_ for _ in ()).throw(
        RuntimeError("db")
    )

    result = StockMarketService(repository, FakeLiveMarket()).summary("005930")

    assert result.dividend_yield is None


def test_dividend_ratio_helper_uses_reported_value_when_calculation_is_unavailable() -> (
    None
):
    assert _dividend_yield(None, Decimal("75000"), Decimal("1.8")) == Decimal("1.8")


def test_summary_returns_null_financial_metrics_when_statement_is_missing() -> None:
    result = StockMarketService(
        FakeRepository(financial=False), FakeLiveMarket()
    ).summary("005930")

    assert result.per is None
    assert result.pbr is None
    assert result.roe is None
    assert result.sources["financial"] is None
    assert result.sources["per"] is None
    assert result.sources["pbr"] is None
    assert result.sources["roe"] is None



def test_historical_chart_uses_only_repository_prices() -> None:
    repository = FakeRepository()
    result = StockMarketService(repository, FakeLiveMarket()).chart("005930", "3M")

    assert result.source == "KRX"
    assert len(result.items) == 1
    assert result.items[0].close == Decimal("73800")
    assert repository.requested_start_date == date.today() - timedelta(days=93)


def test_one_day_chart_uses_kis_minute_candles() -> None:
    result = StockMarketService(FakeRepository(), FakeLiveMarket()).chart(
        "005930", "1D"
    )

    assert result.source == "KIS"
    assert result.items[0].date == "2026-08-24T00:00:00+00:00"
    assert result.items[0].close == Decimal("73400")


def test_one_day_chart_does_not_require_krx_database() -> None:
    result = StockMarketService(UnavailableRepository(), FakeLiveMarket()).chart(
        "005930", "1D"
    )

    assert result.source == "KIS"
    assert result.stock_code == "005930"
