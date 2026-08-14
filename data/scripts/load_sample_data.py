"""Load deterministic sample rows and demonstrate idempotent UPSERTs."""

from datetime import date

import pandas as pd

from db.connection import build_engine, session_scope
from db.models import FinancialStatement, MacroIndicator, MarketIndexDaily, StockIssuance
from loaders.stocks import attach_stock_ids, load_stock_master, load_stock_prices
from loaders.upsert import upsert_dataframe


def main() -> None:
    engine = build_engine()
    master = pd.DataFrame(
        [
            {
                "reference_date": date(2026, 8, 13),
                "stock_code": "005930",
                "isin": "KR7005930003",
                "market_type": "KOSPI",
                "stock_name": "삼성전자",
                "corporation_registration_number": "1301110006246",
                "corporation_name": "삼성전자주식회사",
            }
        ]
    )
    prices = pd.DataFrame(
        [
            {
                "stock_code": "005930",
                "trade_date": date(2026, 8, 12),
                "open_price": 80_000,
                "high_price": 81_000,
                "low_price": 79_500,
                "close_price": 80_700,
                "volume": 12_345_678,
                "trading_value": 995_000_000_000,
            }
        ]
    )

    with session_scope(engine) as session:
        affected = load_stock_master(session, master)
        affected += load_stock_prices(session, prices)

        issuance = attach_stock_ids(
            session,
            pd.DataFrame(
                [
                    {
                        "stock_code": "005930",
                        "reference_date": date(2026, 8, 13),
                        "issued_shares": 5_919_637_922,
                        "par_value": 100,
                        "listing_date": date(1975, 6, 11),
                    }
                ]
            ),
        )
        affected += upsert_dataframe(
            session,
            StockIssuance,
            issuance,
            conflict_columns=["stock_id", "reference_date"],
        )

        financial = attach_stock_ids(
            session,
            pd.DataFrame(
                [
                    {
                        "stock_code": "005930",
                        "corp_code": "00126380",
                        "receipt_number": "20260515000001",
                        "business_year": "2026",
                        "report_code": "11013",
                        "fiscal_period": "2026Q1",
                        "statement_scope": "CFS",
                        "report_date": date(2026, 3, 31),
                        "disclosure_date": date(2026, 5, 15),
                        "available_date": date(2026, 5, 15),
                        "assets": 500_000_000_000_000,
                        "liabilities": 120_000_000_000_000,
                        "equity": 380_000_000_000_000,
                        "revenue": 80_000_000_000_000,
                        "operating_income": 10_000_000_000_000,
                        "net_income": 8_000_000_000_000,
                    }
                ]
            ),
        )
        affected += upsert_dataframe(
            session,
            FinancialStatement,
            financial,
            conflict_columns=[
                "corp_code",
                "business_year",
                "report_code",
                "fiscal_period",
                "statement_scope",
            ],
        )

        affected += upsert_dataframe(
            session,
            MarketIndexDaily,
            pd.DataFrame(
                [
                    {
                        "index_code": "KOSPI",
                        "trade_date": date(2026, 8, 12),
                        "open_value": 3_150.12,
                        "high_value": 3_175.44,
                        "low_value": 3_140.20,
                        "close_value": 3_168.77,
                        "change_rate": 0.0052,
                    }
                ]
            ),
            conflict_columns=["index_code", "trade_date"],
        )
        affected += upsert_dataframe(
            session,
            MacroIndicator,
            pd.DataFrame(
                [
                    {
                        "indicator_code": "ECOS_BASE_RATE",
                        "indicator_name": "한국은행 기준금리",
                        "observation_date": date(2026, 8, 1),
                        "frequency": "M",
                        "value": 2.50,
                        "unit": "%",
                    }
                ]
            ),
            conflict_columns=["indicator_code", "observation_date", "frequency"],
        )
    print(f"sample UPSERT complete: {affected} rows affected")


if __name__ == "__main__":
    main()
