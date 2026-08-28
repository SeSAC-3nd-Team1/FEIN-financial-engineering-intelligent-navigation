from datetime import UTC, datetime, timedelta
from decimal import Decimal
import importlib.util
import sys
from pathlib import Path

from app.trading_engine.contracts_fix import MBGWeightResponseFix
from app.trading_engine.weight_gate_fix import AlgorithmWeightGateFix


def response(proposals, confidence="0.9"):
    return MBGWeightResponseFix(request_id="r1", confidence=confidence, summary="조정", proposals=proposals)


def test_agent_adjustment_is_capped_and_cash_buffer_is_preserved():
    baseline = {"005930": Decimal("0.50"), "000660": Decimal("0.40")}
    result = AlgorithmWeightGateFix().evaluate(
        baseline_weights=baseline, signal_generated_at=datetime.now(UTC),
        agent=response([
            {"stock_code": "005930", "baseline_weight": "0.50", "proposed_weight": "0.80", "reason": "강세"},
            {"stock_code": "000660", "baseline_weight": "0.40", "proposed_weight": "0.30", "reason": "축소"},
        ]),
    )
    assert result.agent_applied is True
    assert result.approved_weights["005930"] <= Decimal("0.60")
    assert sum(result.approved_weights.values()) <= Decimal("0.95")


def test_universe_mismatch_falls_back_to_baseline():
    baseline = {"005930": Decimal("0.50")}
    result = AlgorithmWeightGateFix().evaluate(
        baseline_weights=baseline, signal_generated_at=datetime.now(UTC),
        agent=response([{"stock_code": "000660", "baseline_weight": "0.50", "proposed_weight": "0.40", "reason": "교체"}]),
    )
    assert result.agent_applied is False
    assert result.approved_weights == baseline


def test_stale_signal_is_rejected():
    result = AlgorithmWeightGateFix().evaluate(
        baseline_weights={"005930": Decimal("0.50")},
        signal_generated_at=datetime.now(UTC) - timedelta(hours=2), agent=None,
    )
    assert "STALE_OR_FUTURE_ALGORITHM_SIGNAL" in result.reasons


def test_fixed_output_model_enforces_cash_buffer_across_portfolio():
    path = Path(__file__).resolve().parents[2] / "output" / "fincon_ver23_model_fix.py"
    spec = importlib.util.spec_from_file_location("fincon_ver23_model_fix_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    plan = module.FinConVer23Model().plan(
        account_id="a", generated_at="t", cash_balance=Decimal("1000"), positions=[],
        prices={"005930": Decimal("100"), "000660": Decimal("100")},
        target_weights={"005930": Decimal("0.60"), "000660": Decimal("0.40")},
        stop_prices={}, coordinator_blocked_symbols=set(), coordinator_risk_flags=[],
        max_turnover=Decimal("1"), min_order_amount=Decimal("1"), cash_buffer=Decimal("0.05"),
    )
    assert sum(order.target_weight for order in plan.orders) <= Decimal("0.95")
