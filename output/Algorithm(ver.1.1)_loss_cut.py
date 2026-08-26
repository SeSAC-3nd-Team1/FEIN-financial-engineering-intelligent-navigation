"""Algorithm(ver.1.1) 전용 손절 추천 모듈.

원본 알고리즘이 전달하는 BMA 예측분포, BOCPD/HMM 레짐, Expert 상태와
포지션 상태를 이용한다. 기본값은 추천과 로그만 생성하며, ``auto_apply=True``일
때만 원본의 다음 목표 비중에 더 보수적인 손절 권고가 반영된다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AlgorithmLossCutConfig:
    auto_apply: bool = False
    initial_atr_multiple: float = 2.5
    trailing_atr_multiple: float = 3.0
    minimum_stop_fraction: float = 0.02
    maximum_stop_fraction: float = 0.12
    trailing_activation_r: float = 1.0
    adverse_probability_reduce: float = 0.55
    adverse_probability_exit: float = 0.70
    opposite_regime_exit: float = 0.60
    current_regime_floor: float = 0.20
    change_probability_trigger: float = 0.35
    sideways_max_holding_bars: int = 20
    reduce_fraction: float = 0.50
    cooldown_bars: int = 3


class AlgorithmLossCutMonitor:
    """예측분포·레짐 반전·Expert 무효화·ATR stop을 계층적으로 평가한다."""

    def __init__(self, config: AlgorithmLossCutConfig | None = None) -> None:
        self.config = config or AlgorithmLossCutConfig()
        self.auto_apply = self.config.auto_apply

    def evaluate_algorithm(
        self,
        *,
        timestamp: pd.Timestamp,
        market_row: pd.Series,
        current_weight: float,
        approved_target_weight: float,
        regime_probabilities: Mapping[str, float],
        predictive: object,
        forecasts: Mapping[str, object],
        bma_weights: Mapping[str, float],
        p_change: float,
        portfolio: object,
        position_state: object,
    ) -> dict[str, object]:
        if abs(current_weight) <= 1e-12 or getattr(position_state, "side", "FLAT") == "FLAT":
            position_state.status = "INACTIVE"
            return self._record(
                "NOT_APPLICABLE", approved_target_weight, None,
                "NO_OPEN_POSITION", 1.0, position_state,
            )

        close = float(market_row["Close"])
        atr = float(market_row["atr_14"]) * close
        if not np.isfinite(close) or not np.isfinite(atr) or atr <= 0:
            position_state.status = "DATA_ERROR"
            return self._record(
                "HOLD", approved_target_weight, None, "DATA_ERROR", 0.0, position_state
            )

        dominant_regime = max(regime_probabilities, key=regime_probabilities.get)
        dominant_expert = max(bma_weights, key=bma_weights.get) if bma_weights else ""
        if not getattr(position_state, "entry_regime", ""):
            position_state.entry_regime = dominant_regime
        if not getattr(position_state, "entry_expert", ""):
            position_state.entry_expert = dominant_expert

        self._arm_or_raise_stop(position_state, atr, dominant_expert)
        action, reason, confidence = self._decision(
            close=close,
            current_weight=current_weight,
            regime_probabilities=regime_probabilities,
            predictive=predictive,
            forecasts=forecasts,
            p_change=p_change,
            portfolio=portfolio,
            position_state=position_state,
        )

        target = float(approved_target_weight)
        if action in {"EXIT", "EMERGENCY_EXIT"}:
            target = 0.0
            position_state.status = "TRIGGERED"
            position_state.last_stop_reason = reason
            position_state.cooldown_until = pd.Timestamp(timestamp) + pd.offsets.BDay(
                self.config.cooldown_bars
            )
        elif action == "REDUCE":
            target = current_weight * (1.0 - self.config.reduce_fraction)
            position_state.status = "REDUCE_RECOMMENDED"
            position_state.last_stop_reason = reason
        else:
            position_state.status = "ARMED"

        return self._record(
            action,
            target,
            position_state.active_stop,
            reason,
            confidence,
            position_state,
        )

    def _arm_or_raise_stop(self, state: object, atr: float, dominant_expert: str) -> None:
        c = self.config
        entry = float(state.entry_price)
        side = str(state.side)
        if state.initial_stop is None:
            fraction = float(
                np.clip(
                    c.initial_atr_multiple * atr / max(entry, 1e-12),
                    c.minimum_stop_fraction,
                    c.maximum_stop_fraction,
                )
            )
            state.initial_risk_r = entry * fraction
            state.initial_stop = entry - state.initial_risk_r if side == "LONG" else entry + state.initial_risk_r
            state.active_stop = state.initial_stop

        # Sideways/OU 진입에는 trend trailing을 적용하지 않고 모델 무효화와
        # 최대 보유기간을 사용한다.
        trend_position = (
            str(getattr(state, "entry_regime", "")) in {"bull", "bear"}
            or dominant_expert.startswith(("bull_", "bear_"))
        )
        if not trend_position:
            return

        risk_r = max(float(state.initial_risk_r or 0.0), 1e-12)
        if side == "LONG":
            favorable = state.highest_price_since_entry - entry
            if favorable >= c.trailing_activation_r * risk_r:
                trailing = state.highest_price_since_entry - c.trailing_atr_multiple * atr
                state.active_stop = max(float(state.active_stop), trailing)
        else:
            favorable = entry - state.lowest_price_since_entry
            if favorable >= c.trailing_activation_r * risk_r:
                trailing = state.lowest_price_since_entry + c.trailing_atr_multiple * atr
                state.active_stop = min(float(state.active_stop), trailing)

    def _decision(
        self,
        *,
        close: float,
        current_weight: float,
        regime_probabilities: Mapping[str, float],
        predictive: object,
        forecasts: Mapping[str, object],
        p_change: float,
        portfolio: object,
        position_state: object,
    ) -> tuple[str, str, float]:
        side = str(position_state.side)
        if bool(getattr(portfolio, "kill_switch", False)):
            return "EMERGENCY_EXIT", "PORTFOLIO_KILL_SWITCH", 1.0

        stop = position_state.active_stop
        if stop is not None:
            breached = (side == "LONG" and close <= stop) or (side == "SHORT" and close >= stop)
            if breached:
                return "EXIT", "PRICE_BELOW_ACTIVE_STOP" if side == "LONG" else "PRICE_ABOVE_ACTIVE_STOP", 0.95

        p_up = float(np.clip(getattr(predictive, "p_up", 0.5), 0.0, 1.0))
        adverse_probability = 1.0 - p_up if side == "LONG" else p_up
        if adverse_probability >= self.config.adverse_probability_exit:
            return "EXIT", "PREDICTIVE_ADVERSE_PROBABILITY", adverse_probability

        current_regime = "bull" if side == "LONG" else "bear"
        opposite_regime = "bear" if side == "LONG" else "bull"
        regime_flip = (
            p_change >= self.config.change_probability_trigger
            and regime_probabilities.get(current_regime, 0.0) <= self.config.current_regime_floor
            and regime_probabilities.get(opposite_regime, 0.0) >= self.config.opposite_regime_exit
        )
        if regime_flip:
            return "EXIT", "BOCPD_HMM_REGIME_FLIP", 0.90

        entry_regime = str(getattr(position_state, "entry_regime", ""))
        if entry_regime == "sideways":
            ou = forecasts.get("side_ou")
            ou_invalid = ou is not None and not bool(getattr(ou, "valid", False))
            sideways_lost = regime_probabilities.get("sideways", 0.0) <= self.config.current_regime_floor
            if ou_invalid and sideways_lost:
                return "EXIT", "SIDEWAYS_MODEL_INVALIDATION", 0.90
            pnl = (
                close / max(position_state.entry_price, 1e-12) - 1.0
                if side == "LONG"
                else position_state.entry_price / max(close, 1e-12) - 1.0
            )
            if position_state.holding_bars >= self.config.sideways_max_holding_bars and pnl <= 0:
                return "EXIT", "SIDEWAYS_TIME_STOP", 0.80

        if adverse_probability >= self.config.adverse_probability_reduce:
            return "REDUCE", "PREDICTIVE_RISK_RISING", adverse_probability
        return "HOLD", "NO_LOSS_CUT_TRIGGER", 0.60

    @staticmethod
    def _record(
        action: str,
        target_weight: float,
        stop_price: float | None,
        reason: str,
        confidence: float,
        state: object,
    ) -> dict[str, object]:
        return {
            "loss_cut_action": action,
            "loss_cut_status": str(state.status),
            "loss_cut_reason": reason,
            "loss_cut_target_weight": float(target_weight),
            "recommended_stop_price": np.nan if stop_price is None else float(stop_price),
            "loss_cut_confidence": float(confidence),
            "loss_cut_entry_regime": str(getattr(state, "entry_regime", "")),
            "loss_cut_entry_expert": str(getattr(state, "entry_expert", "")),
            "loss_cut_holding_bars": int(getattr(state, "holding_bars", 0)),
        }


__all__ = ["AlgorithmLossCutConfig", "AlgorithmLossCutMonitor"]
