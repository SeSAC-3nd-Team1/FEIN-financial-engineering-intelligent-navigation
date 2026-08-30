"""MOCK.py 결과에 적용 가능한 새넌형 정률 리밸런싱 제안·시뮬레이션 모듈.

기본 비중은 주식 50%, 현금 20%, 단기국공채/RP 20%, 물가연동채 10%다.
실제 주문은 생성하지 않으며, MOCK의 시장 대비 10% 가정은 혼합 포트폴리오에
그대로 보장되지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

import numpy as np
import pandas as pd

ASSETS = ("equity", "cash", "short_gov_rp", "inflation_linked_bond")


@dataclass(frozen=True)
class AllocationWeights:
    equity: float = 0.50
    cash: float = 0.20
    short_gov_rp: float = 0.20
    inflation_linked_bond: float = 0.10

    def as_dict(self) -> Dict[str, float]:
        values = {name: float(getattr(self, name)) for name in ASSETS}
        if any(v < 0 for v in values.values()) or not np.isclose(sum(values.values()), 1.0):
            raise ValueError("비중은 음수가 아니며 합계가 1이어야 합니다.")
        return values


@dataclass(frozen=True)
class RebalanceConfig:
    frequency: str = "monthly"  # daily, weekly, monthly, quarterly
    drift_threshold: float = 0.05
    transaction_cost_bps: float = 5.0
    initial_cash: float = 100_000.0


@dataclass
class RebalanceProposal:
    should_rebalance: bool
    reason: str
    current_weights: Dict[str, float]
    target_weights: Dict[str, float]
    trades_value: Dict[str, float]


@dataclass
class RebalancingResult:
    equity: pd.Series
    returns: pd.Series
    decisions: pd.DataFrame
    metrics: Dict[str, float]


class MockRebalancer:
    def __init__(self, target: AllocationWeights = AllocationWeights(),
                 config: RebalanceConfig = RebalanceConfig()) -> None:
        self.target = target.as_dict()
        self.config = config

    def propose(self, current_values: Mapping[str, float], manual: bool = False,
                target: Optional[AllocationWeights] = None) -> RebalanceProposal:
        target_weights = (target or AllocationWeights(**self.target)).as_dict()
        values = {name: float(current_values.get(name, 0.0)) for name in ASSETS}
        total = sum(values.values())
        if total <= 0:
            raise ValueError("현재 자산가치 합계는 0보다 커야 합니다.")
        current = {name: values[name] / total for name in ASSETS}
        drift = max(abs(current[name] - target_weights[name]) for name in ASSETS)
        should = bool(manual or drift >= self.config.drift_threshold)
        reason = "manual_request" if manual else ("drift_threshold" if should else "within_band")
        trades = {name: total * target_weights[name] - values[name] if should else 0.0 for name in ASSETS}
        return RebalanceProposal(should, reason, current, target_weights, trades)

    def simulate(self, equity_returns: pd.Series,
                 cash_returns: Optional[pd.Series] = None,
                 short_gov_rp_returns: Optional[pd.Series] = None,
                 inflation_linked_bond_returns: Optional[pd.Series] = None) -> RebalancingResult:
        eq = pd.Series(equity_returns, dtype=float).dropna()
        sleeves = pd.DataFrame(index=eq.index)
        sleeves["equity"] = eq
        sleeves["cash"] = 0.0 if cash_returns is None else cash_returns.reindex(eq.index).fillna(0.0)
        sleeves["short_gov_rp"] = 0.0 if short_gov_rp_returns is None else short_gov_rp_returns.reindex(eq.index).fillna(0.0)
        sleeves["inflation_linked_bond"] = 0.0 if inflation_linked_bond_returns is None else inflation_linked_bond_returns.reindex(eq.index).fillna(0.0)
        freq = {"daily": None, "weekly": "W", "monthly": "M", "quarterly": "Q"}
        if self.config.frequency not in freq:
            raise ValueError(f"지원하지 않는 주기: {self.config.frequency}")
        scheduled = pd.Series(False, index=eq.index)
        if self.config.frequency == "daily":
            scheduled[:] = True
        else:
            periods = eq.index.to_period(freq[self.config.frequency])
            scheduled.iloc[0] = True
            scheduled.iloc[1:] = np.asarray(periods[1:] != periods[:-1])
        target = pd.Series(self.target)
        values = target * self.config.initial_cash
        portfolio_returns, costs, rows = [], [], []
        for date, row in sleeves.iterrows():
            before = float(values.sum())
            weights = values / before
            rebalance = bool(scheduled.at[date] or (weights - target).abs().max() >= self.config.drift_threshold)
            turnover = float((weights - target).abs().sum()) if rebalance else 0.0
            cost = before * turnover * self.config.transaction_cost_bps / 10_000.0
            if rebalance:
                values = target * (before - cost)
            start_value = float(values.sum())
            values = values * (1.0 + row)
            end_value = float(values.sum())
            portfolio_returns.append(end_value / start_value - 1.0 if start_value else 0.0)
            costs.append(cost)
            rows.append({"equity": end_value, "rebalanced": rebalance, "turnover": turnover,
                         "cost": cost, **{f"weight_{k}": float(values[k] / end_value) for k in ASSETS}})
        decisions = pd.DataFrame(rows, index=eq.index)
        returns = pd.Series(portfolio_returns, index=eq.index, name="return")
        equity = decisions["equity"].rename("equity")
        drawdown = equity / equity.cummax() - 1.0
        metrics = {"final_equity": float(equity.iloc[-1]),
                   "total_return": float(equity.iloc[-1] / self.config.initial_cash - 1.0),
                   "max_drawdown": float(drawdown.min()), "total_trading_cost": float(sum(costs)),
                   "rebalance_count": float(decisions["rebalanced"].sum()), "bars": float(len(eq))}
        return RebalancingResult(equity, returns, decisions, metrics)


def apply_to_mock_result(mock_result, target: AllocationWeights = AllocationWeights(),
                         config: Optional[RebalanceConfig] = None) -> RebalancingResult:
    cfg = config or RebalanceConfig(initial_cash=float(mock_result.equity.iloc[0] / (1 + mock_result.returns.iloc[0])))
    return MockRebalancer(target, cfg).simulate(mock_result.returns)
