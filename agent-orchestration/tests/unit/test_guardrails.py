import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

import agent_orchestration.guardrails as guardrails_module
from agent_orchestration.guardrails import GuardrailResult, evaluate_guardrails
from agent_orchestration.universe import (
    AssetType,
    FileUniverseProvider,
    UniverseProviderError,
    UniverseSnapshot,
    UniverseTarget,
)


def test_stale_universe_blocks_trade_candidate():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC) - timedelta(days=40),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )
    result = evaluate_guardrails("005930", snapshot, analysis_mode="analysis_only")

    assert result.trade_blocked is True
    assert "STALE_UNIVERSE" in result.block_reasons


def test_analysis_only_always_disables_execution():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )
    result = evaluate_guardrails("005930", snapshot, analysis_mode="analysis_only")

    assert result.execution_allowed is False


def test_unknown_ticker_is_outside_universe():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    result = evaluate_guardrails("000660", snapshot, analysis_mode="paper_trading")

    assert result.trade_blocked is True
    assert result.execution_allowed is False
    assert "OUTSIDE_OR_UNKNOWN_UNIVERSE" in result.block_reasons


def test_paper_trading_still_disables_execution():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    result = evaluate_guardrails("005930", snapshot, analysis_mode="paper_trading")

    assert result.trade_blocked is True
    assert result.execution_allowed is False
    assert "PAPER_TRADING_NO_EXECUTION" in result.block_reasons


def test_freshness_uses_precise_elapsed_time():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC) - timedelta(days=7, seconds=1),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    assert snapshot.stale is True


def test_future_universe_timestamp_is_stale():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC) + timedelta(seconds=1),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    assert snapshot.stale is True


def test_universe_requires_aware_timestamp():
    with pytest.raises(ValidationError):
        UniverseSnapshot(
            as_of=datetime(2026, 8, 27),
            max_age_days=7,
            instruments={},
        )


@pytest.mark.parametrize("max_age_days", [0, 366])
def test_universe_age_setting_is_bounded(max_age_days):
    with pytest.raises(ValidationError):
        UniverseSnapshot(
            as_of=datetime.now(UTC),
            max_age_days=max_age_days,
            instruments={},
        )


def test_target_and_config_keys_use_one_canonical_form():
    target = UniverseTarget(ticker=" 005930.KS ", asset_type="KOSPI200_STOCK")
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={" 005930.KS ": "KOSPI200_STOCK"},
    )

    result = evaluate_guardrails(
        " 005930 ", snapshot, analysis_mode="paper_trading", asset_type=target.asset_type
    )

    assert target.ticker == "005930"
    assert "OUTSIDE_OR_UNKNOWN_UNIVERSE" not in result.block_reasons
    assert "INVALID_IDENTIFIER" not in result.block_reasons


def test_canonical_target_contract_is_accepted_by_evaluator():
    target = UniverseTarget(ticker="005930.KS", asset_type="KOSPI200_STOCK")
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    result = evaluate_guardrails(target, snapshot, analysis_mode="paper_trading")

    assert "OUTSIDE_OR_UNKNOWN_UNIVERSE" not in result.block_reasons
    assert "INVALID_IDENTIFIER" not in result.block_reasons


def test_unsupported_asset_type_blocks_known_target():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"BTC": "CRYPTO"},
    )

    result = evaluate_guardrails("BTC", snapshot, analysis_mode="paper_trading")

    assert result.trade_blocked is True
    assert "UNSUPPORTED_ASSET_TYPE" in result.block_reasons


def test_unknown_asset_type_blocks_known_target():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "MYSTERY_ASSET"},
    )

    result = evaluate_guardrails("005930", snapshot, analysis_mode="paper_trading")

    assert result.trade_blocked is True
    assert "UNKNOWN_ASSET_TYPE" in result.block_reasons


def test_malformed_identifier_blocks_candidate():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"not a ticker": "KOSPI200_STOCK"},
    )

    result = evaluate_guardrails("not a ticker", snapshot, analysis_mode="paper_trading")

    assert result.trade_blocked is True
    assert "INVALID_IDENTIFIER" in result.block_reasons


def test_asset_type_mismatch_blocks_candidate():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    result = evaluate_guardrails(
        "005930", snapshot, analysis_mode="paper_trading", asset_type="CRYPTO"
    )

    assert result.trade_blocked is True
    assert "ASSET_TYPE_MISMATCH" in result.block_reasons
    assert "UNSUPPORTED_ASSET_TYPE" in result.block_reasons


def test_unknown_analysis_mode_is_explicitly_blocked():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    result = evaluate_guardrails("005930", snapshot, analysis_mode="live_trading")

    assert result.trade_blocked is True
    assert result.execution_allowed is False
    assert "INVALID_ANALYSIS_MODE" in result.block_reasons


@pytest.mark.asyncio
async def test_universe_provider_failure_is_typed_and_blocks(tmp_path):
    with pytest.raises(UniverseProviderError) as error:
        await FileUniverseProvider(tmp_path / "missing.json").get_snapshot()

    result = evaluate_guardrails("005930", None, analysis_mode="paper_trading")

    assert error.value.block_reason == "UNIVERSE_UNAVAILABLE"
    assert result.trade_blocked is True
    assert "UNIVERSE_UNAVAILABLE" in result.block_reasons


def test_unsafe_guardrail_result_construction_is_rejected():
    with pytest.raises(ValidationError):
        GuardrailResult(trade_blocked=False, execution_allowed=True)

    with pytest.raises(ValidationError):
        GuardrailResult.model_validate(
            {"trade_blocked": False, "execution_allowed": True, "block_reasons": []}
        )


def test_guardrail_no_trading_fields_cannot_be_mutated():
    result = GuardrailResult()

    with pytest.raises((ValidationError, TypeError)):
        result.execution_allowed = True


def test_guardrail_model_copy_revalidates_no_trading_invariants():
    with pytest.raises(ValidationError):
        GuardrailResult().model_copy(
            update={"trade_blocked": False, "execution_allowed": True}
        )


def test_snapshot_model_copy_revalidates_age_bounds():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    with pytest.raises(ValidationError):
        snapshot.model_copy(update={"max_age_days": 1_000_000})


def test_target_model_copy_revalidates_asset_type():
    target = UniverseTarget(ticker="BTC", asset_type="CRYPTO")

    with pytest.raises(ValidationError):
        target.model_copy(update={"asset_type": None})


def test_snapshot_is_frozen_but_valid_copies_remain_available():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )

    with pytest.raises((ValidationError, TypeError)):
        snapshot.instruments = {"BTC": AssetType.CRYPTO}
    with pytest.raises((ValidationError, TypeError)):
        snapshot.as_of = datetime.now(UTC)

    copied = snapshot.model_copy(update={"max_age_days": 30})

    assert snapshot.max_age_days == 7
    assert copied.max_age_days == 30


@pytest.mark.parametrize(
    "field, value",
    [("as_of", "not-a-timestamp"), ("max_age_days", "not-an-age")],
)
def test_malformed_freshness_state_fails_closed(field, value):
    snapshot_values = {
        "as_of": datetime.now(UTC),
        "max_age_days": 7,
        "instruments": {"005930": "KOSPI200_STOCK"},
    }
    snapshot_values[field] = value
    snapshot = UniverseSnapshot.model_construct(**snapshot_values)

    result = evaluate_guardrails("005930", snapshot, analysis_mode="paper_trading")

    assert result.trade_blocked is True
    assert result.execution_allowed is False
    assert "UNIVERSE_UNAVAILABLE" in result.block_reasons


def test_policy_and_nested_boundary_state_are_immutable():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )
    result = GuardrailResult(block_reasons=["TEST_REASON"])

    with pytest.raises(TypeError):
        guardrails_module.ASSET_TYPE_POLICY[AssetType.CRYPTO] = True
    with pytest.raises(TypeError):
        snapshot.instruments["005930"] = AssetType.CASH
    with pytest.raises(AttributeError):
        result.block_reasons.append("ANOTHER_REASON")


def test_unexpected_instrument_state_fails_closed_without_key_error():
    snapshot = UniverseSnapshot.model_construct(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "MYSTERY_ASSET"},
    )

    result = evaluate_guardrails("005930", snapshot, analysis_mode="paper_trading")

    assert result.trade_blocked is True
    assert "UNKNOWN_ASSET_TYPE" in result.block_reasons


def test_unexpected_policy_state_fails_closed_without_key_error(monkeypatch):
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )
    monkeypatch.setattr(
        guardrails_module,
        "ASSET_TYPE_POLICY",
        {AssetType.KOSPI200_STOCK: "unexpected"},
    )

    result = evaluate_guardrails("005930", snapshot, analysis_mode="paper_trading")

    assert result.trade_blocked is True
    assert "UNKNOWN_ASSET_POLICY" in result.block_reasons


@pytest.mark.asyncio
async def test_file_universe_provider_loads_snapshot(tmp_path):
    path = tmp_path / "universe.json"
    path.write_text(
        json.dumps(
            {
                "as_of": "2026-08-27T00:00:00Z",
                "max_age_days": 7,
                "instruments": {"005930": "KOSPI200_STOCK"},
            }
        ),
        encoding="utf-8",
    )

    snapshot = await FileUniverseProvider(path).get_snapshot()

    assert snapshot.instruments == {"005930": "KOSPI200_STOCK"}
