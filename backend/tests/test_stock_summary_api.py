"""종목 요약 배당 nullable API 계약을 검증한다."""

from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import current_user
from app.api.routes import market
from app.schemas.api import StockSummaryResponse


class NoDividendSummaryService:
    def summary(self, stock_code: str) -> StockSummaryResponse:
        return StockSummaryResponse(
            stock_code=stock_code,
            stock_name="삼성전자",
            market="KOSPI",
            sector="전기전자",
            listing_date=date(1975, 6, 11),
            listed_shares=5_969_782_550,
            security_type="주권",
            description=None,
            price=None,
            previous_close=None,
            change_amount=None,
            change_rate=None,
            volume=None,
            market_cap=None,
            per=None,
            pbr=None,
            roe=None,
            dividend_yield=None,
            financial_year=None,
            as_of=None,
            sources={
                "price": None,
                "market": "KRX",
                "financial": None,
                "dividend": None,
                "dividend_price": None,
            },
        )


def test_summary_returns_200_and_null_when_dividend_data_is_missing() -> None:
    app = FastAPI()
    app.include_router(market.router, prefix="/api/v1")
    app.dependency_overrides[current_user] = lambda: object()
    app.dependency_overrides[market.get_stock_market_service] = NoDividendSummaryService

    response = TestClient(app).get("/api/v1/market/stocks/005930/summary")

    assert response.status_code == 200
    assert response.json()["dividend_yield"] is None
