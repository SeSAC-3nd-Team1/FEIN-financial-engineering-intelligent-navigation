from __future__ import annotations

import pandas as pd
import pytest

from features.model_dataset import (
    assign_purged_time_split,
    compute_financial_features,
    compute_stock_features,
)
from processing.contracts import canonical_name, snake_case
from processing.normalize import build_operation_contract, normalize_payload
from processing.quality import validate_payload


def _field_profile(*, date: bool = False, integer: bool = False, numeric: bool = False):
    return {
        "nonempty": 1,
        "yyyymmdd_rate_nonempty": 1.0 if date else 0.0,
        "integer_rate_nonempty": 1.0 if integer else 0.0,
        "numeric_rate_nonempty": 1.0 if numeric else 0.0,
    }


def test_snake_case_and_core_aliases_use_path_operation_case():
    assert snake_case("lstgMrktTotAmt") == "lstg_mrkt_tot_amt"
    assert canonical_name("stock_price", "getstockpriceinfo", "clpr") == "close_price"
    assert canonical_name("stock_price", "getStockPriceInfo", "clpr") == "close_price"
    assert canonical_name("unknown", "x", "basDt") == "bas_dt"


def test_profile_payload_contract_and_normalization():
    profile = {
        "payload_fields": {
            "basDt": _field_profile(date=True, integer=True, numeric=True),
            "clpr": _field_profile(integer=True, numeric=True),
        }
    }
    contract = build_operation_contract(profile, "stock_price", "getstockpriceinfo")
    output, errors = normalize_payload(
        {"basDt": "20260814", "clpr": "72,100"},
        contract,
    )
    assert output["trade_date"].isoformat() == "2026-08-14"
    assert output["close_price"] == 72100
    assert errors == []


def test_numeric_looking_identifiers_remain_strings():
    profile = {
        "payload_fields": {
            "basDt": _field_profile(date=True, integer=True, numeric=True),
            "srtnCd": _field_profile(integer=True, numeric=True),
            "isinCd": _field_profile(),
        }
    }
    contract = build_operation_contract(profile, "stock_price", "getstockpriceinfo")
    output, errors = normalize_payload(
        {"basDt": "20260814", "srtnCd": "005930", "isinCd": "KR7005930003"},
        contract,
    )
    assert output["stock_code"] == "005930"
    assert output["isin_code"] == "KR7005930003"
    assert errors == []


def test_financial_corporation_number_remains_string():
    profile = {
        "payload_fields": {
            "basDt": _field_profile(date=True, integer=True, numeric=True),
            "crno": _field_profile(integer=True, numeric=True),
        }
    }
    contract = build_operation_contract(
        profile,
        "financial_statement",
        "getsummfinastat_v2",
    )
    output, _ = normalize_payload(
        {"basDt": "20251231", "crno": "001101110018138"},
        contract,
    )
    assert output["corporation_number"] == "001101110018138"


def test_quality_is_applied_to_nested_payload_semantics():
    assert validate_payload({"basDt": "20260814"}) is None
    assert validate_payload({"basDt": ""}) == "missing_basDt"
    assert validate_payload({"basDt": "20260230"}) == "invalid_basDt"


def _price_frame(days: int = 180) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=days, freq="B")
    return pd.DataFrame(
        {
            "stock_code": ["005930"] * days,
            "trade_date": dates,
            "close_price": [100 + i for i in range(days)],
            "volume": [1000 + i for i in range(days)],
            "trading_value": [100000 + i for i in range(days)],
            "market_cap": [1_000_000 + i for i in range(days)],
        }
    )


def test_stock_features_use_past_for_features_and_future_only_for_targets():
    result = compute_stock_features(_price_frame())
    row = result.iloc[60]
    assert row["momentum_20d"] == pytest.approx((160 / 140) - 1)
    assert row["target_return_5d"] == pytest.approx((165 / 160) - 1)
    assert pd.isna(result.iloc[-1]["target_return_5d"])


def test_temporal_split_purges_targets_crossing_boundaries():
    result, boundaries = assign_purged_time_split(compute_stock_features(_price_frame()))
    train = result[result["split"] == "train"]
    boundary_rows = train[
        train["target_date_20d"] > pd.Timestamp(boundaries["train_end"])
    ]
    assert not boundary_rows.empty
    assert not boundary_rows["eligible_target_20d"].any()
    eligible_train = result[
        result["eligible_target_20d"] & (result["split"] == "train")
    ]
    assert eligible_train["target_date_20d"].max() <= pd.Timestamp(
        boundaries["train_end"]
    )


def test_financial_features_are_not_marked_ready_for_point_in_time_join():
    frame = pd.DataFrame(
        {
            "base_date": ["2025-12-31"],
            "sales": [100],
            "operating_profit": [10],
            "net_income": [5],
            "total_assets": [200],
            "total_liabilities": [80],
            "total_equity": [120],
        }
    )
    result = compute_financial_features(frame)
    assert result.iloc[0]["debt_ratio"] == pytest.approx(80 / 120)
    assert not bool(result.iloc[0]["point_in_time_join_ready"])
