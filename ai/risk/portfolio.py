"""Long-only portfolio construction with explicit P0 constraints."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PortfolioConstraints:
    max_positions: int = 10
    max_weight: float = 0.15
    cash_buffer: float = 0.05
    max_turnover: float = 0.30
    min_trade_weight: float = 0.005

    def __post_init__(self) -> None:
        if self.max_positions <= 0:
            raise ValueError("max_positions must be positive")
        if not 0 < self.max_weight <= 1:
            raise ValueError("max_weight must be in (0, 1]")
        if not 0 <= self.cash_buffer < 1:
            raise ValueError("cash_buffer must be in [0, 1)")
        if not 0 <= self.max_turnover <= 2:
            raise ValueError("max_turnover must be in [0, 2]")
        if not 0 <= self.min_trade_weight <= 1:
            raise ValueError("min_trade_weight must be in [0, 1]")
        if self.max_positions * self.max_weight < 1 - self.cash_buffer:
            raise ValueError("position limits cannot deploy the requested invested weight")


def _normalize_capped_equal_weight(codes: list[str], constraints: PortfolioConstraints) -> pd.Series:
    invested = 1.0 - constraints.cash_buffer
    if not codes:
        return pd.Series(dtype=float)
    weight = invested / len(codes)
    if weight > constraints.max_weight + 1e-12:
        raise ValueError("selected positions cannot satisfy max_weight")
    return pd.Series(weight, index=codes, dtype=float)


def construct_portfolio(
    candidates: pd.DataFrame,
    *,
    current_weights: pd.Series | None = None,
    constraints: PortfolioConstraints = PortfolioConstraints(),
) -> pd.DataFrame:
    """Convert ranked eligible stocks to weights and cap one-way turnover."""

    required = {"stock_code", "score"}
    missing = sorted(required - set(candidates.columns))
    if missing:
        raise ValueError(f"portfolio candidate columns missing: {missing}")
    data = candidates.copy()
    if "risk_eligible" in data:
        data = data.loc[data["risk_eligible"].fillna(False).astype(bool)]
    data["score"] = pd.to_numeric(data["score"], errors="coerce")
    selected = (
        data.loc[data["score"].notna()]
        .sort_values(["score", "stock_code"], ascending=[False, True])
        .drop_duplicates("stock_code")
        .head(constraints.max_positions)
    )
    target = _normalize_capped_equal_weight(selected["stock_code"].astype(str).tolist(), constraints)

    current = pd.Series(dtype=float) if current_weights is None else pd.Series(current_weights, dtype=float)
    if (current < 0).any() or current.sum() > 1 + 1e-9:
        raise ValueError("current weights must be long-only and sum to at most one")
    if (current > constraints.max_weight + 1e-9).any():
        raise ValueError("current weights cannot exceed max_weight")
    if int(current.gt(0).sum()) > constraints.max_positions:
        raise ValueError("current holdings cannot exceed max_positions")
    all_codes = current.index.union(target.index)
    current = current.reindex(all_codes, fill_value=0.0)
    target = target.reindex(all_codes, fill_value=0.0)
    delta = target - current
    delta = delta.where(delta.abs().ge(constraints.min_trade_weight), 0.0)

    # 최소 거래 필터로 작은 매도만 제거되면 남은 매수가 보유 현금을 초과할 수 있다.
    # 매수 총액을 현재 현금과 실행할 매도의 합으로 제한해 총 자산 비중을 보존한다.
    sells = float(-delta.clip(upper=0.0).sum())
    buys = float(delta.clip(lower=0.0).sum())
    available_to_buy = 1.0 - float(current.sum()) + sells
    if buys > available_to_buy and buys > 0:
        delta.loc[delta > 0] *= max(0.0, available_to_buy) / buys

    # 현금도 하나의 자산으로 포함해야 주식 순매수·순매도가 회전율에서 누락되지 않는다.
    cash_delta = -float(delta.sum())
    turnover = float((delta.abs().sum() + abs(cash_delta)) / 2.0)
    if turnover > constraints.max_turnover and turnover > 0:
        delta *= constraints.max_turnover / turnover

    final = current + delta
    open_positions = final.gt(1e-12)
    if int(open_positions.sum()) > constraints.max_positions:
        # 회전율 제한으로 기존 종목이 남아 있으면 신규 편입을 취소해야 종목 수 상한과
        # 회전율을 동시에 지킬 수 있다. 낮은 목표 비중의 신규 종목부터 제외한다.
        new_positions = final.index[current.eq(0.0) & open_positions]
        excess = int(open_positions.sum()) - constraints.max_positions
        positions_to_cancel = target.loc[new_positions].sort_values().index[:excess]
        delta.loc[positions_to_cancel] = 0.0
        final = current + delta

    invested = float(final.sum())
    if (final < -1e-9).any() or (final > constraints.max_weight + 1e-9).any():
        raise RuntimeError("portfolio construction violated position constraints")
    if invested > 1.0 + 1e-9:
        raise RuntimeError("portfolio construction exceeded available capital")
    if int(final.gt(1e-12).sum()) > constraints.max_positions:
        raise RuntimeError("portfolio construction exceeded max_positions")
    final = final.clip(lower=0.0, upper=constraints.max_weight)
    cash_weight = 1.0 - float(final.sum())
    result = pd.DataFrame({"stock_code": final.index.astype(str), "weight": final.values})
    result = result.loc[result["weight"].gt(0)].sort_values(
        ["weight", "stock_code"], ascending=[False, True]
    )
    result["cash_weight"] = cash_weight
    return result.reset_index(drop=True)
