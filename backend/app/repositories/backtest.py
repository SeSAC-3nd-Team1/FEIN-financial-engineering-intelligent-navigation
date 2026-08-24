"""백테스트에 필요한 시점 기준 KRX 종목·가격·지수 조회."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MarketIndex, MarketStockPrice, Strategy


@dataclass(frozen=True)
class StockPricePoint:
    stock_code: str
    trade_date: date
    close: Decimal


@dataclass(frozen=True)
class IndexPricePoint:
    trade_date: date
    close: Decimal


class BacktestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def strategy(self, strategy_id: str) -> Strategy | None:
        return self.session.scalar(
            select(Strategy).where(Strategy.id == strategy_id, Strategy.is_active.is_(True))
        )

    def universe_codes(self, as_of: date, *, limit: int = 100) -> list[str]:
        """시작일 전에 관측된 최신 시총으로 universe를 고정해 미래 universe 참조를 막는다."""

        latest_date = self.session.scalar(
            select(func.max(MarketStockPrice.trade_date)).where(MarketStockPrice.trade_date < as_of)
        )
        if latest_date is None:
            return []
        return list(self.session.scalars(
            select(MarketStockPrice.stock_code)
            .where(
                MarketStockPrice.trade_date == latest_date,
                MarketStockPrice.market_cap.is_not(None),
                MarketStockPrice.market_cap > 0,
            )
            .order_by(MarketStockPrice.market_cap.desc())
            .limit(limit)
        ))

    def stock_prices(self, stock_codes: list[str], start_date: date, end_date: date) -> list[StockPricePoint]:
        rows = self.session.execute(
            select(
                MarketStockPrice.stock_code,
                MarketStockPrice.trade_date,
                MarketStockPrice.close_price,
            ).where(
                MarketStockPrice.stock_code.in_(stock_codes),
                MarketStockPrice.trade_date >= start_date,
                MarketStockPrice.trade_date <= end_date,
            ).order_by(MarketStockPrice.trade_date, MarketStockPrice.stock_code)
        )
        return [StockPricePoint(code, trade_date, close) for code, trade_date, close in rows]

    def kospi_prices(self, start_date: date, end_date: date) -> list[IndexPricePoint]:
        rows = self.session.execute(
            select(MarketIndex.trade_date, MarketIndex.close_value)
            .where(
                MarketIndex.market == "KOSPI",
                MarketIndex.index_name.in_(("코스피", "KOSPI")),
                MarketIndex.trade_date >= start_date,
                MarketIndex.trade_date <= end_date,
            )
            .order_by(MarketIndex.trade_date)
        )
        # provider 표기 차이로 같은 날짜가 중복되면 최초 main-index 행만 사용한다.
        unique = {trade_date: IndexPricePoint(trade_date, close) for trade_date, close in rows}
        return [unique[key] for key in sorted(unique)]
