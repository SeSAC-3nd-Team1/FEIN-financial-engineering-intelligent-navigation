"""JDY 전략 전용 손절 모니터.

원본 ``personal_strategy_JDY.py``는 종목 선정과 목표 비중을 담당하고, 이 모듈은
포지션 상태를 관측해 손절 조건과 권고 목표 비중을 추가한다. 주문은 전송하지
않으며 기존 JDY 전략과 동일하게 사람의 승인을 요구한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd

try:
    from .personal_strategy_JDY import (
        JDYPositionRiskState,
        JDYStrategyConfig,
        run_personal_strategy_jdy,
    )
except ImportError:  # 직접 파일 실행 또는 ai/inference를 PYTHONPATH로 사용
    from personal_strategy_JDY import (  # type: ignore
        JDYPositionRiskState,
        JDYStrategyConfig,
        run_personal_strategy_jdy,
    )


@dataclass(frozen=True)
class JDYLossCutConfig:
    atr_window: int = 20
    initial_atr_multiple: float = 2.5
    trailing_atr_multiple: float = 3.0
    minimum_stop_fraction: float = 0.06
    maximum_stop_fraction: float = 0.15
    trailing_activation_r: float = 1.0
    time_stop_days: int = 30
    time_stop_reduce_fraction: float = 0.50
    cooldown_business_days: int = 5


class JDYLossCutMonitor:
    """가설 훼손, ATR 손절, Chandelier trailing, time stop을 평가한다."""

    def __init__(self, config: JDYLossCutConfig | None = None) -> None:
        self.config = config or JDYLossCutConfig()

    def evaluate_jdy(
        self,
        as_of: str | pd.Timestamp,
        recommendations: pd.DataFrame,
        prices: pd.DataFrame,
        states: dict[str, JDYPositionRiskState],
    ) -> pd.DataFrame:
        cutoff = pd.Timestamp(as_of).tz_localize(None) if pd.Timestamp(as_of).tzinfo else pd.Timestamp(as_of)
        result = recommendations.copy()
        atr_by_symbol = self._latest_atr(prices)
        outputs: list[dict[str, object]] = []

        for row in result.itertuples(index=False):
            symbol = str(row.symbol)
            current_weight = float(row.current_weight)
            close = float(row.close) if np.isfinite(row.close) else np.nan
            held = current_weight > 0
            state = states.get(symbol)

            if not held:
                if state is not None and state.status not in {"TRIGGERED", "COOLDOWN"}:
                    state.status = "INACTIVE"
                outputs.append(self._empty_recommendation(state))
                continue

            if state is None:
                state = JDYPositionRiskState(symbol=symbol)
                states[symbol] = state
            if state.entry_price <= 0:
                state.open(close, cutoff)
                state.status = "MONITORING_BOOTSTRAPPED"
            else:
                state.observe(close, cutoff)

            atr = float(atr_by_symbol.get(symbol, np.nan))
            if not np.isfinite(close) or not np.isfinite(atr) or atr <= 0:
                state.status = "DATA_ERROR"
                outputs.append(
                    self._record("HOLD", current_weight, None, "DATA_ERROR", 0.0, state)
                )
                continue

            self._arm_or_raise_stop(state, atr)
            action, reason, confidence = self._decision(row, state, close)
            recommended_weight = current_weight
            if action == "EXIT":
                recommended_weight = 0.0
                state.status = "TRIGGERED"
                state.last_stop_reason = reason
                state.cooldown_until = cutoff + pd.offsets.BDay(self.config.cooldown_business_days)
            elif action == "REDUCE":
                base_target = float(row.target_weight)
                recommended_weight = min(
                    base_target,
                    current_weight * (1.0 - self.config.time_stop_reduce_fraction),
                )
                state.status = "REDUCE_RECOMMENDED"
                state.last_stop_reason = reason
            else:
                state.status = "ARMED" if state.active_stop is not None else "MONITORING"

            outputs.append(
                self._record(
                    action,
                    recommended_weight,
                    state.active_stop,
                    reason,
                    confidence,
                    state,
                )
            )

        monitor = pd.DataFrame(outputs, index=result.index)
        return pd.concat([result, monitor], axis=1)

    def _arm_or_raise_stop(self, state: JDYPositionRiskState, atr: float) -> None:
        c = self.config
        if state.initial_stop is None:
            fraction = float(
                np.clip(
                    c.initial_atr_multiple * atr / max(state.entry_price, 1e-12),
                    c.minimum_stop_fraction,
                    c.maximum_stop_fraction,
                )
            )
            state.initial_risk_r = state.entry_price * fraction
            state.initial_stop = state.entry_price - state.initial_risk_r
            state.active_stop = state.initial_stop

        initial_risk = max(float(state.initial_risk_r or 0.0), 1e-12)
        open_profit = state.highest_price_since_entry - state.entry_price
        if open_profit >= c.trailing_activation_r * initial_risk:
            trailing = state.highest_price_since_entry - c.trailing_atr_multiple * atr
            state.active_stop = max(float(state.active_stop or -np.inf), trailing)

    def _decision(self, row: object, state: JDYPositionRiskState, close: float) -> tuple[str, str, float]:
        base_action = str(getattr(row, "action"))
        reason = str(getattr(row, "reason"))
        if base_action == "SELL":
            return "EXIT", f"THESIS_INVALIDATION:{reason}", 0.95
        if state.active_stop is not None and close <= state.active_stop:
            return "EXIT", "PRICE_BELOW_ACTIVE_STOP", 0.90
        pnl = close / max(state.entry_price, 1e-12) - 1.0
        if state.holding_days >= self.config.time_stop_days and pnl <= 0:
            return "REDUCE", "TIME_STOP_NO_PROGRESS", 0.75
        if base_action == "REDUCE":
            return "REDUCE", f"STRATEGY_REDUCE:{reason}", 0.80
        return "HOLD", "NO_LOSS_CUT_TRIGGER", 0.60

    def _latest_atr(self, prices: pd.DataFrame) -> pd.Series:
        required = {"symbol", "date", "high", "low", "close"}
        missing = sorted(required - set(prices.columns))
        if missing:
            raise ValueError(f"ATR 계산에 필요한 prices 컬럼이 없습니다: {missing}")
        records: dict[str, float] = {}
        for symbol, group in prices.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
            previous = group["close"].shift(1)
            true_range = pd.concat(
                [
                    group["high"] - group["low"],
                    (group["high"] - previous).abs(),
                    (group["low"] - previous).abs(),
                ],
                axis=1,
            ).max(axis=1)
            records[str(symbol)] = float(
                true_range.rolling(self.config.atr_window, min_periods=self.config.atr_window).mean().iloc[-1]
            )
        return pd.Series(records, dtype=float)

    @staticmethod
    def _record(
        action: str,
        target_weight: float,
        stop_price: float | None,
        reason: str,
        confidence: float,
        state: JDYPositionRiskState,
    ) -> dict[str, object]:
        return {
            "loss_cut_action": action,
            "loss_cut_status": state.status,
            "loss_cut_reason": reason,
            "recommended_stop_price": stop_price,
            "loss_cut_target_weight": float(target_weight),
            "loss_cut_confidence": float(confidence),
            "holding_days": state.holding_days,
            "requires_loss_cut_approval": action in {"REDUCE", "EXIT"},
        }

    @staticmethod
    def _empty_recommendation(state: JDYPositionRiskState | None) -> dict[str, object]:
        return {
            "loss_cut_action": "NOT_APPLICABLE",
            "loss_cut_status": state.status if state is not None else "INACTIVE",
            "loss_cut_reason": "NO_OPEN_POSITION",
            "recommended_stop_price": np.nan,
            "loss_cut_target_weight": 0.0,
            "loss_cut_confidence": 1.0,
            "holding_days": state.holding_days if state is not None else 0,
            "requires_loss_cut_approval": False,
        }


def run_personal_strategy_jdy_with_loss_cut(
    as_of: str | pd.Timestamp,
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
    flows: pd.DataFrame,
    metadata: pd.DataFrame | None = None,
    current_positions: pd.DataFrame | None = None,
    strategy_config: JDYStrategyConfig | None = None,
    loss_cut_config: JDYLossCutConfig | None = None,
    states: dict[str, JDYPositionRiskState] | None = None,
) -> tuple[pd.DataFrame, dict[str, JDYPositionRiskState]]:
    """JDY 자동추천과 손절 모니터를 한 번에 실행하는 공개 진입점."""
    shared_states = states if states is not None else {}
    monitor = JDYLossCutMonitor(loss_cut_config)
    recommendations = run_personal_strategy_jdy(
        as_of=as_of,
        prices=prices,
        fundamentals=fundamentals,
        flows=flows,
        metadata=metadata,
        current_positions=current_positions,
        config=strategy_config,
        loss_cut_monitor=monitor,
        loss_cut_states=shared_states,
    )
    return recommendations, shared_states


def states_to_frame(states: Mapping[str, JDYPositionRiskState]) -> pd.DataFrame:
    """외부 저장소에 적재하기 쉬운 상태 스냅샷을 반환한다."""
    return pd.DataFrame([vars(state).copy() for state in states.values()])


__all__ = [
    "JDYLossCutConfig",
    "JDYLossCutMonitor",
    "run_personal_strategy_jdy_with_loss_cut",
    "states_to_frame",
]
