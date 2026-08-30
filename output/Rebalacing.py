"""JDY와 Algorithm 전략에 공통 적용하는 constant-mix 리밸런싱 모듈.

Claude Shannon의 이른바 "Shannon's Demon"에서 착안한 고정비중(constant-mix)
방식으로 다음 네 자산군을 목표 비중에 되돌린다.

1. 주식(EQUITY)
2. 현금(CASH)
3. 단기국공채 및 RP(SHORT_GOV_RP)
4. 물가연동채권(INFLATION_LINKED_BOND)

이 모듈은 종목이나 금융상품을 임의로 선택하지 않는다. JDY/Algorithm이 주식
슬리브 내부 목표를 만들고, 외부 계좌 어댑터가 각 자산군의 실제 상품과 체결을
담당한다. 기본값에서 AI agent 요청은 승인 대기이며 자동 주문되지 않는다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from enum import Enum
import math
from typing import Callable, Mapping, Sequence
from uuid import uuid4

import pandas as pd


EPS = 1e-10


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    CASH = "CASH"
    SHORT_GOV_RP = "SHORT_GOV_RP"
    INFLATION_LINKED_BOND = "INFLATION_LINKED_BOND"


class RequestSource(str, Enum):
    USER = "USER"
    AI_AGENT = "AI_AGENT"
    SCHEDULE = "SCHEDULE"


class RebalanceFrequency(str, Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    CUSTOM_DAYS = "CUSTOM_DAYS"
    MANUAL_ONLY = "MANUAL_ONLY"


class ProposalStatus(str, Enum):
    NOT_DUE = "NOT_DUE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AllocationWeights:
    equity: float
    cash: float
    short_gov_rp: float
    inflation_linked_bond: float

    def __post_init__(self) -> None:
        values = self.as_dict()
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("모든 목표 비중은 유한한 숫자여야 합니다.")
        if any(value < 0 or value > 1 for value in values.values()):
            raise ValueError("각 목표 비중은 0 이상 1 이하여야 합니다.")
        if not math.isclose(sum(values.values()), 1.0, abs_tol=1e-8):
            raise ValueError(f"목표 비중 합은 1이어야 합니다: {sum(values.values()):.12f}")

    def as_dict(self) -> dict[AssetClass, float]:
        return {
            AssetClass.EQUITY: float(self.equity),
            AssetClass.CASH: float(self.cash),
            AssetClass.SHORT_GOV_RP: float(self.short_gov_rp),
            AssetClass.INFLATION_LINKED_BOND: float(self.inflation_linked_bond),
        }

    @classmethod
    def shannon_classic(cls) -> "AllocationWeights":
        """고전적인 위험자산 50% / 현금 50% 예시."""
        return cls(0.50, 0.50, 0.0, 0.0)

    @classmethod
    def from_mapping(cls, values: Mapping[str | AssetClass, float]) -> "AllocationWeights":
        normalized = {_asset_class(key): float(value) for key, value in values.items()}
        missing = [asset.value for asset in AssetClass if asset not in normalized]
        if missing:
            raise ValueError(f"목표 비중이 누락된 자산군: {missing}")
        return cls(
            equity=normalized[AssetClass.EQUITY],
            cash=normalized[AssetClass.CASH],
            short_gov_rp=normalized[AssetClass.SHORT_GOV_RP],
            inflation_linked_bond=normalized[AssetClass.INFLATION_LINKED_BOND],
        )


@dataclass(frozen=True)
class RebalanceSchedule:
    frequency: RebalanceFrequency = RebalanceFrequency.MONTHLY
    custom_days: int | None = None
    drift_band: float = 0.05
    rebalance_on_band_breach: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.drift_band <= 1:
            raise ValueError("drift_band는 0 이상 1 이하여야 합니다.")
        if self.frequency == RebalanceFrequency.CUSTOM_DAYS:
            if self.custom_days is None or self.custom_days <= 0:
                raise ValueError("CUSTOM_DAYS에는 양의 custom_days가 필요합니다.")

    def interval(self) -> timedelta | None:
        days = {
            RebalanceFrequency.DAILY: 1,
            RebalanceFrequency.WEEKLY: 7,
            RebalanceFrequency.MONTHLY: 30,
            RebalanceFrequency.QUARTERLY: 90,
            RebalanceFrequency.CUSTOM_DAYS: self.custom_days,
            RebalanceFrequency.MANUAL_ONLY: None,
        }[self.frequency]
        return timedelta(days=days) if days is not None else None


@dataclass(frozen=True)
class RebalanceRequest:
    target_weights: AllocationWeights
    schedule: RebalanceSchedule
    source: RequestSource
    requested_by: str
    requested_at: pd.Timestamp
    manual_execute: bool = False
    user_approved: bool = False
    request_id: str = field(default_factory=lambda: str(uuid4()))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "RebalanceRequest":
        if "target_weights" not in payload:
            raise ValueError("target_weights가 필요합니다.")
        frequency = RebalanceFrequency(str(payload.get("frequency", "MONTHLY")).upper())
        schedule = RebalanceSchedule(
            frequency=frequency,
            custom_days=_optional_int(payload.get("custom_days")),
            drift_band=float(payload.get("drift_band", 0.05)),
            rebalance_on_band_breach=bool(payload.get("rebalance_on_band_breach", True)),
        )
        requested_at = pd.Timestamp(payload.get("requested_at", pd.Timestamp.now()))
        if requested_at.tzinfo is not None:
            requested_at = requested_at.tz_localize(None)
        return cls(
            target_weights=AllocationWeights.from_mapping(payload["target_weights"]),  # type: ignore[arg-type]
            schedule=schedule,
            source=RequestSource(str(payload.get("source", "USER")).upper()),
            requested_by=str(payload.get("requested_by", "unknown")),
            requested_at=requested_at,
            manual_execute=bool(payload.get("manual_execute", False)),
            user_approved=bool(payload.get("user_approved", False)),
            request_id=str(payload.get("request_id", uuid4())),
        )


@dataclass(frozen=True)
class SleeveSnapshot:
    values: Mapping[AssetClass, float]
    observed_at: pd.Timestamp

    def __post_init__(self) -> None:
        normalized = {_asset_class(key): float(value) for key, value in self.values.items()}
        missing = [asset.value for asset in AssetClass if asset not in normalized]
        if missing:
            raise ValueError(f"현재 평가액이 누락된 자산군: {missing}")
        if any(not math.isfinite(value) or value < 0 for value in normalized.values()):
            raise ValueError("자산군 평가액은 유한한 0 이상의 값이어야 합니다.")
        object.__setattr__(self, "values", normalized)
        timestamp = pd.Timestamp(self.observed_at)
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_localize(None)
        object.__setattr__(self, "observed_at", timestamp)

    @property
    def total_value(self) -> float:
        return float(sum(self.values.values()))

    def weights(self) -> dict[AssetClass, float]:
        if self.total_value <= EPS:
            raise ValueError("총 평가액이 0이므로 현재 비중을 계산할 수 없습니다.")
        return {asset: value / self.total_value for asset, value in self.values.items()}


@dataclass(frozen=True)
class TradeInstruction:
    asset_class: AssetClass
    current_value: float
    target_value: float
    delta_value: float
    direction: str
    current_weight: float
    target_weight: float


@dataclass
class RebalanceProposal:
    request_id: str
    status: ProposalStatus
    reason: str
    source: RequestSource
    requested_by: str
    created_at: pd.Timestamp
    total_value: float
    current_weights: Mapping[AssetClass, float]
    target_weights: Mapping[AssetClass, float]
    maximum_drift: float
    instructions: list[TradeInstruction]
    requires_human_approval: bool
    execution_result: Mapping[str, object] | None = None

    @property
    def has_trades(self) -> bool:
        return bool(self.instructions)


@dataclass
class RebalanceState:
    last_executed_at: pd.Timestamp | None = None
    last_request_id: str | None = None
    last_status: ProposalStatus = ProposalStatus.NOT_DUE
    execution_count: int = 0


class ShannonRebalancer:
    """주기 또는 비중 이탈에 따라 네 자산군의 constant-mix를 복원한다."""

    def __init__(
        self,
        *,
        minimum_trade_value: float = 10_000.0,
        ai_requests_require_human_approval: bool = True,
    ) -> None:
        if minimum_trade_value < 0:
            raise ValueError("minimum_trade_value는 음수가 될 수 없습니다.")
        self.minimum_trade_value = float(minimum_trade_value)
        self.ai_requests_require_human_approval = ai_requests_require_human_approval
        self.state = RebalanceState()

    def propose(
        self,
        snapshot: SleeveSnapshot,
        request: RebalanceRequest,
    ) -> RebalanceProposal:
        current = snapshot.weights()
        target = request.target_weights.as_dict()
        drift = {asset: current[asset] - target[asset] for asset in AssetClass}
        maximum_drift = max(abs(value) for value in drift.values())
        due, reason = self._is_due(snapshot.observed_at, request, maximum_drift)

        requires_approval = (
            request.source == RequestSource.AI_AGENT
            and self.ai_requests_require_human_approval
            and not request.user_approved
        )
        if not due:
            status = ProposalStatus.NOT_DUE
            instructions: list[TradeInstruction] = []
        else:
            instructions = self._instructions(snapshot, target)
            if not instructions:
                status = ProposalStatus.NOT_DUE
                reason = "MINIMUM_TRADE_VALUE_NOT_REACHED"
            elif requires_approval:
                status = ProposalStatus.AWAITING_APPROVAL
            else:
                status = ProposalStatus.APPROVED

        self.state.last_request_id = request.request_id
        self.state.last_status = status
        return RebalanceProposal(
            request_id=request.request_id,
            status=status,
            reason=reason,
            source=request.source,
            requested_by=request.requested_by,
            created_at=snapshot.observed_at,
            total_value=snapshot.total_value,
            current_weights=current,
            target_weights=target,
            maximum_drift=maximum_drift,
            instructions=instructions,
            requires_human_approval=requires_approval,
        )

    def approve(self, proposal: RebalanceProposal, approved_by: str) -> RebalanceProposal:
        if proposal.status != ProposalStatus.AWAITING_APPROVAL:
            raise ValueError("승인 대기 중인 제안만 승인할 수 있습니다.")
        if not approved_by.strip():
            raise ValueError("approved_by가 필요합니다.")
        proposal.status = ProposalStatus.APPROVED
        proposal.requires_human_approval = False
        proposal.reason = f"APPROVED_BY:{approved_by}"
        self.state.last_status = proposal.status
        return proposal

    def reject(self, proposal: RebalanceProposal, rejected_by: str) -> RebalanceProposal:
        if proposal.status not in {ProposalStatus.AWAITING_APPROVAL, ProposalStatus.APPROVED}:
            raise ValueError("승인 대기 또는 승인된 제안만 거절할 수 있습니다.")
        proposal.status = ProposalStatus.REJECTED
        proposal.reason = f"REJECTED_BY:{rejected_by}"
        self.state.last_status = proposal.status
        return proposal

    def execute(
        self,
        proposal: RebalanceProposal,
        executor: Callable[[Sequence[TradeInstruction]], Mapping[str, object]],
    ) -> RebalanceProposal:
        """승인된 제안을 외부 계좌 어댑터에 전달한다.

        ``executor``가 실제 상품선택, 주문, 부분체결, 수수료와 원장 대사를
        책임진다. 이 모듈은 자산군 단위 금액 지시만 전달한다.
        """
        if proposal.status != ProposalStatus.APPROVED:
            raise PermissionError("APPROVED 상태의 제안만 실행할 수 있습니다.")
        try:
            result = executor(tuple(proposal.instructions))
        except Exception as exc:
            proposal.status = ProposalStatus.FAILED
            proposal.reason = f"EXECUTION_FAILED:{type(exc).__name__}"
            proposal.execution_result = {"error": str(exc)}
            self.state.last_status = proposal.status
            raise
        proposal.status = ProposalStatus.EXECUTED
        proposal.reason = "EXECUTED_BY_EXTERNAL_ADAPTER"
        proposal.execution_result = dict(result)
        self.state.last_executed_at = proposal.created_at
        self.state.last_request_id = proposal.request_id
        self.state.last_status = proposal.status
        self.state.execution_count += 1
        return proposal

    def _is_due(
        self,
        observed_at: pd.Timestamp,
        request: RebalanceRequest,
        maximum_drift: float,
    ) -> tuple[bool, str]:
        if request.manual_execute:
            return True, "MANUAL_EXECUTION_REQUEST"
        if request.schedule.rebalance_on_band_breach and maximum_drift >= request.schedule.drift_band:
            return True, "DRIFT_BAND_BREACH"
        interval = request.schedule.interval()
        if interval is None:
            return False, "MANUAL_ONLY_NO_REQUEST"
        if self.state.last_executed_at is None:
            return True, "FIRST_SCHEDULED_REBALANCE"
        if observed_at - self.state.last_executed_at >= interval:
            return True, f"SCHEDULE_DUE:{request.schedule.frequency.value}"
        return False, "NOT_DUE"

    def _instructions(
        self,
        snapshot: SleeveSnapshot,
        target: Mapping[AssetClass, float],
    ) -> list[TradeInstruction]:
        current_weight = snapshot.weights()
        instructions: list[TradeInstruction] = []
        selected_deltas: dict[AssetClass, float] = {}
        for asset in AssetClass:
            if asset == AssetClass.CASH:
                continue
            current_value = float(snapshot.values[asset])
            target_value = snapshot.total_value * target[asset]
            delta = target_value - current_value
            if abs(delta) < self.minimum_trade_value:
                continue
            selected_deltas[asset] = delta
            instructions.append(
                TradeInstruction(
                    asset_class=asset,
                    current_value=current_value,
                    target_value=target_value,
                    delta_value=delta,
                    direction="BUY" if delta > 0 else "SELL",
                    current_weight=current_weight[asset],
                    target_weight=target[asset],
                )
            )

        # 최소거래금액 필터 뒤에도 실행 지시가 self-financing이 되도록 현금을
        # 정확한 자금조달 항목으로 다시 계산한다.
        cash_delta = -sum(selected_deltas.values())
        if abs(cash_delta) > 0.01:
            current_cash = float(snapshot.values[AssetClass.CASH])
            target_cash = current_cash + cash_delta
            if target_cash < -0.01:
                raise ValueError("현금이 부족해 제안된 매수를 자체 조달할 수 없습니다.")
            instructions.append(
                TradeInstruction(
                    asset_class=AssetClass.CASH,
                    current_value=current_cash,
                    target_value=target_cash,
                    delta_value=cash_delta,
                    direction="RAISE_CASH" if cash_delta > 0 else "DEPLOY_CASH",
                    current_weight=current_weight[AssetClass.CASH],
                    target_weight=target_cash / snapshot.total_value,
                )
            )

        # 전체 목표 자체의 자금 보존식도 별도로 검증한다.
        full_delta = sum(snapshot.total_value * target[a] - snapshot.values[a] for a in AssetClass)
        if not math.isclose(full_delta, 0.0, abs_tol=max(0.01, snapshot.total_value * 1e-10)):
            raise ArithmeticError(f"리밸런싱 자금 보존식이 맞지 않습니다: {full_delta}")
        instruction_delta = sum(item.delta_value for item in instructions)
        if not math.isclose(instruction_delta, 0.0, abs_tol=0.01):
            raise ArithmeticError(f"실행 지시의 자금 보존식이 맞지 않습니다: {instruction_delta}")
        return instructions


def scale_jdy_equity_targets(
    recommendations: pd.DataFrame,
    allocation: AllocationWeights,
    *,
    normalize_selected: bool = True,
) -> pd.DataFrame:
    """JDY 종목 목표비중을 전체 포트폴리오의 주식 슬리브에 맞춘다."""
    required = {"symbol", "target_weight"}
    missing = sorted(required - set(recommendations.columns))
    if missing:
        raise ValueError(f"JDY 추천 결과에 필요한 컬럼이 없습니다: {missing}")
    result = recommendations.copy()
    raw = pd.to_numeric(result["target_weight"], errors="raise").clip(lower=0.0)
    total = float(raw.sum())
    if normalize_selected and total > EPS:
        sleeve_weight = raw / total
    else:
        sleeve_weight = raw
    result["strategy_target_weight"] = raw
    result["portfolio_target_weight"] = sleeve_weight * allocation.equity
    result["asset_class"] = AssetClass.EQUITY.value
    return result


def apply_algorithm_equity_budget(
    strategy_target_weight: float,
    allocation: AllocationWeights,
) -> dict[str, float]:
    """Algorithm의 signed 노출을 주식 슬리브 예산 안으로 제한한다.

    Algorithm 목표 1.0은 주식 슬리브 100% 사용, 0.5는 절반만 사용한다.
    미사용 주식 예산은 현금 reserve로 이동한다. Short는 gross exposure로
    계산하며 실제 증거금·대차·매도대금 처리는 외부 계좌 어댑터 책임이다.
    """
    exposure = float(strategy_target_weight)
    if not math.isfinite(exposure) or abs(exposure) > 1 + EPS:
        raise ValueError("Algorithm strategy_target_weight는 -1 이상 1 이하여야 합니다.")
    deployed = allocation.equity * exposure
    reserve = allocation.equity * (1.0 - abs(exposure))
    return {
        "strategy_target_weight": exposure,
        "portfolio_equity_exposure": deployed,
        "equity_sleeve_cash_reserve": reserve,
        "portfolio_cash_and_reserve": allocation.cash + reserve,
        "short_gov_rp_weight": allocation.short_gov_rp,
        "inflation_linked_bond_weight": allocation.inflation_linked_bond,
    }


def proposal_to_frame(proposal: RebalanceProposal) -> pd.DataFrame:
    """UI 또는 AI agent가 표시하기 쉬운 거래 제안 표를 반환한다."""
    rows = []
    for instruction in proposal.instructions:
        row = asdict(instruction)
        row["asset_class"] = instruction.asset_class.value
        row["proposal_status"] = proposal.status.value
        row["proposal_reason"] = proposal.reason
        row["request_id"] = proposal.request_id
        rows.append(row)
    return pd.DataFrame(rows)


def state_to_mapping(state: RebalanceState) -> dict[str, object]:
    return {
        "last_executed_at": state.last_executed_at,
        "last_request_id": state.last_request_id,
        "last_status": state.last_status.value,
        "execution_count": state.execution_count,
    }


def _asset_class(value: str | AssetClass) -> AssetClass:
    if isinstance(value, AssetClass):
        return value
    normalized = str(value).strip().upper()
    aliases = {
        "STOCK": AssetClass.EQUITY,
        "주식": AssetClass.EQUITY,
        "현금": AssetClass.CASH,
        "SHORT_BOND_RP": AssetClass.SHORT_GOV_RP,
        "단기국공채_RP": AssetClass.SHORT_GOV_RP,
        "단기국공채 및 RP": AssetClass.SHORT_GOV_RP,
        "TIPS": AssetClass.INFLATION_LINKED_BOND,
        "물가연동채권": AssetClass.INFLATION_LINKED_BOND,
    }
    if normalized in aliases:
        return aliases[normalized]
    return AssetClass(normalized)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


__all__ = [
    "AllocationWeights",
    "AssetClass",
    "ProposalStatus",
    "RebalanceFrequency",
    "RebalanceProposal",
    "RebalanceRequest",
    "RebalanceSchedule",
    "RebalanceState",
    "RequestSource",
    "ShannonRebalancer",
    "SleeveSnapshot",
    "TradeInstruction",
    "apply_algorithm_equity_budget",
    "proposal_to_frame",
    "scale_jdy_equity_targets",
    "state_to_mapping",
]
