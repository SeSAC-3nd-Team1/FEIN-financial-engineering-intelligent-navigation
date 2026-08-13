"""Example period query with point-in-time financial data filtering."""

from datetime import date

from sqlalchemy import select

from db.connection import build_engine, session_scope
from db.models import FinancialStatement, StockMaster, StockPriceDaily


def main() -> None:
    engine = build_engine()
    backtest_date = date(2026, 8, 12)
    with session_scope(engine) as session:
        prices = session.execute(
            select(
                StockMaster.stock_code,
                StockPriceDaily.trade_date,
                StockPriceDaily.close_price,
            )
            .join(StockMaster, StockMaster.stock_id == StockPriceDaily.stock_id)
            .where(
                StockPriceDaily.trade_date.between(date(2026, 8, 1), backtest_date)
            )
            .order_by(StockPriceDaily.trade_date, StockMaster.stock_code)
        ).all()
        statements = session.execute(
            select(
                StockMaster.stock_code,
                FinancialStatement.fiscal_period,
                FinancialStatement.available_date,
                FinancialStatement.assets,
            )
            .join(StockMaster, StockMaster.stock_id == FinancialStatement.stock_id)
            .where(FinancialStatement.available_date <= backtest_date)
            .order_by(FinancialStatement.available_date.desc())
        ).all()
    print("prices:", prices)
    print("point-in-time financial statements:", statements)


if __name__ == "__main__":
    main()
