from datetime import UTC, datetime, timedelta
import json

import pytest

from agent_orchestration.guardrails import evaluate_guardrails
from agent_orchestration.universe import FileUniverseProvider, UniverseSnapshot


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
