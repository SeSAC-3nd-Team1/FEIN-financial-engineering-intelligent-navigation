"""MOCK.py용 손절 조건 계산·제안 모듈. 주문을 전송하지 않는다."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LossCutConfig:
    atr_window: int = 14
    atr_multiple: float = 2.5
    hard_loss_pct: float = 0.08
    trailing_loss_pct: float = 0.10
    warning_distance_pct: float = 0.02


@dataclass
class PositionState:
    entry_price: float
    highest_price: float
    side: int = 1
    active: bool = True


@dataclass
class LossCutRecommendation:
    action: str
    status: str
    stop_price: float
    reason: str
    confidence: float
    suggested_target_weight: float


class MockLossCutMonitor:
    """ATR·고정손실·트레일링 기준 중 가장 보수적인 손절선을 제안한다."""

    def __init__(self, config: LossCutConfig = LossCutConfig()) -> None:
        self.config = config

    def recommend(
        self, close: float, low: float, atr: float, state: PositionState,
        current_weight: float = 1.0,
    ) -> LossCutRecommendation:
        state.highest_price = max(state.highest_price, close)
        hard = state.entry_price * (1.0 - self.config.hard_loss_pct)
        trailing = state.highest_price * (1.0 - self.config.trailing_loss_pct)
        atr_stop = close - self.config.atr_multiple * max(atr, 0.0)
        stop = max(hard, trailing, atr_stop)
        distance = (close - stop) / max(close, 1e-12)
        if low <= stop:
            return LossCutRecommendation("EXIT", "TRIGGERED", stop, "price_breached_stop", 1.0, 0.0)
        if distance <= self.config.warning_distance_pct:
            return LossCutRecommendation("REDUCE", "WARNING", stop, "price_near_stop", 0.7, current_weight * 0.5)
        return LossCutRecommendation("HOLD", "MONITORING", stop, "stop_not_reached", 0.5, current_weight)

    def annotate_decisions(self, decisions: pd.DataFrame, ohlcv: pd.DataFrame) -> pd.DataFrame:
        out = decisions.copy()
        px = ohlcv.reindex(out.index)
        previous_close = px["Close"].shift(1)
        true_range = pd.concat([
            px["High"] - px["Low"],
            (px["High"] - previous_close).abs(),
            (px["Low"] - previous_close).abs(),
        ], axis=1).max(axis=1)
        atr = true_range.rolling(self.config.atr_window, min_periods=1).mean()
        state = PositionState(float(px["Close"].iloc[0]), float(px["Close"].iloc[0]))
        records = []
        for date in out.index:
            rec = self.recommend(float(px.at[date, "Close"]), float(px.at[date, "Low"]), float(atr.at[date]), state, float(out.at[date, "target_weight"]))
            records.append(rec)
        out["loss_cut_action"] = [r.action for r in records]
        out["loss_cut_status"] = [r.status for r in records]
        out["loss_cut_reason"] = [r.reason for r in records]
        out["recommended_stop_price"] = [r.stop_price for r in records]
        out["loss_cut_confidence"] = [r.confidence for r in records]
        out["loss_cut_target_weight"] = [r.suggested_target_weight for r in records]
        return out

    def evaluate_algorithm(self, *, close: float, low: float, atr: float,
                           entry_price: float, highest_price: Optional[float] = None,
                           current_weight: float = 1.0, **_: object) -> Dict[str, object]:
        state = PositionState(entry_price, highest_price or max(entry_price, close))
        rec = self.recommend(close, low, atr, state, current_weight)
        return {
            "loss_cut_action": rec.action,
            "loss_cut_status": rec.status,
            "loss_cut_reason": rec.reason,
            "loss_cut_target_weight": rec.suggested_target_weight,
            "recommended_stop_price": rec.stop_price,
            "loss_cut_confidence": rec.confidence,
        }
