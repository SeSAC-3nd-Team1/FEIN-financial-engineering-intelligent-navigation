from db.models import FinancialStatement, StockMaster, StockPriceDaily


def _constraint_names(model: type) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.name is not None
    }


def _index_columns(model: type) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in index.columns)
        for index in model.__table__.indexes
    }


def test_stock_master_uses_raw_schema_and_unique_code() -> None:
    assert StockMaster.__table__.schema == "raw"
    assert "uq_stock_master_stock_code" in _constraint_names(StockMaster)
    assert StockMaster.__table__.c.stock_code.type.length == 12


def test_daily_price_has_point_lookup_and_range_indexes() -> None:
    assert "uq_stock_price_daily_stock_date_type" in _constraint_names(
        StockPriceDaily
    )
    assert ("stock_id", "trade_date") in _index_columns(StockPriceDaily)
    assert ("trade_date", "stock_id") in _index_columns(StockPriceDaily)


def test_financial_statement_is_point_in_time_aware() -> None:
    column_names = set(FinancialStatement.__table__.columns.keys())
    assert {"fiscal_period", "report_date", "disclosure_date", "available_date"} <= (
        column_names
    )
    assert ("stock_id", "available_date") in _index_columns(FinancialStatement)
    assert "ck_financial_statement_available_date_after_report_date" in (
        _constraint_names(FinancialStatement)
    )
