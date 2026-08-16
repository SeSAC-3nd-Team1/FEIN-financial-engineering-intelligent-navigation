from datetime import date

import pytest

from scripts import prepare_financial_sql_rebuild as core
from scripts import rebuild_financial_sql as fast


def test_membership_tables_are_never_reset():
    assert set(core.MEMBERSHIP_TABLES).isdisjoint(core.FINANCIAL_RESET_TABLES)
    assert "public.users" in core.PRESERVED_TABLES
    assert "public.terms" in core.PRESERVED_TABLES
    assert "public.user_agreements" in core.PRESERVED_TABLES
    assert "public.alembic_version" in core.PRESERVED_TABLES


def test_api_source_mappings_are_unique_and_canonical():
    keys = {(item.table_name, item.source) for item in core.API_SOURCES}
    assert len(keys) == len(core.API_SOURCES)
    assert {
        (item.dataset, item.operation) for item in core.API_SOURCES
    } == {
        ("stock_master", "getItemInfo"),
        ("stock_price", "getStockPriceInfo"),
        ("market_index", "getStockMarketIndex"),
    }


def test_sql_only_payload_month_requires_valid_basdt():
    assert core._parse_basdt_month({"basDt": "20260813"}) == date(2026, 8, 1)
    with pytest.raises(RuntimeError):
        core._parse_basdt_month({"basDt": "2026-08-13"})
    with pytest.raises(RuntimeError):
        core._parse_basdt_month({})


def test_fast_front_door_uses_optimized_scanner():
    original = core.scan_blob_and_remove_preserved
    try:
        fast.main.__module__ == "scripts.rebuild_financial_sql"
        core.scan_blob_and_remove_preserved = fast.scan_blob_and_remove_preserved
        assert core.scan_blob_and_remove_preserved is fast.scan_blob_and_remove_preserved
    finally:
        core.scan_blob_and_remove_preserved = original
