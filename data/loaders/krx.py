"""KRX canonical row를 서비스 PostgreSQL에 멱등 적재한다."""

from sqlalchemy.orm import Session

from db.models.market_data import MarketIndex, MarketStock, MarketStockPrice
from loaders.upsert import upsert_rows


class KrxRepository:
    """KRX 서비스 테이블의 충돌키를 한 곳에서 관리한다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_stocks(self, rows: list[dict]) -> int:
        return upsert_rows(self.session, MarketStock, rows, conflict_columns=["stock_code"])

    def upsert_prices(self, rows: list[dict]) -> int:
        return upsert_rows(
            self.session,
            MarketStockPrice,
            rows,
            conflict_columns=["stock_code", "trade_date"],
        )

    def upsert_indices(self, rows: list[dict]) -> int:
        return upsert_rows(
            self.session,
            MarketIndex,
            rows,
            conflict_columns=["index_code", "trade_date"],
        )

