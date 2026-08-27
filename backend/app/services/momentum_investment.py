"""Publish a validated momentum snapshot and deploy a new AUTO virtual account."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.models import Order, Position, StrategyTargetWeight
from app.repositories import TradingRepository
from app.schemas.api import ModelRecommendationApplyResponse, OrderCreateRequest
from app.services.model_recommendation import ModelRecommendationService
from app.services.trading import TradingService


class MomentumInvestmentService:
    def __init__(
        self,
        session: Session,
        *,
        snapshot_service: ModelRecommendationService | None = None,
        trading_service: TradingService | None = None,
    ) -> None:
        self.session = session
        self.repo = TradingRepository(session)
        self.snapshot_service = snapshot_service or ModelRecommendationService()
        self.trading_service = trading_service or TradingService(session)

    def apply(self, user_id: int, account_id) -> ModelRecommendationApplyResponse:
        account = self.repo.owned_account(account_id, user_id)
        if account is None:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        if account.selected_strategy_id != "momentum":
            raise ServiceError(
                "MOMENTUM_STRATEGY_REQUIRED",
                "모멘텀 전략이 선택된 계좌에서만 모델 추천을 적용할 수 있습니다.",
                409,
            )

        snapshot = self.snapshot_service.latest()
        if snapshot.source != "generated" or snapshot.is_stale:
            raise ServiceError(
                "MODEL_RECOMMENDATION_NOT_APPLICABLE",
                "최신 실제 모델 추천이 없어 포트폴리오에 적용할 수 없습니다.",
                409,
            )
        target_weights = {
            item.symbol: Decimal(str(item.target_weight))
            for item in snapshot.recommendations
            if item.target_weight > 0
        }
        total_weight = sum(target_weights.values(), Decimal("0"))
        if not target_weights or total_weight <= 0 or total_weight > 1:
            raise ServiceError(
                "INVALID_STRATEGY_TARGET_WEIGHTS",
                "모델 목표 비중 합계가 올바르지 않습니다.",
                503,
            )
        self._publish_targets(snapshot.as_of, target_weights)

        if account.operation_mode != "AUTO":
            return self._response(account.id, snapshot.as_of, len(target_weights), 0, "PROPOSAL_ONLY")

        order_keys = {
            stock_code: f"momentum-{snapshot.as_of.isoformat()}-{stock_code}"
            for stock_code in target_weights
        }
        existing_order_keys = set(
            self.session.scalars(
                select(Order.idempotency_key).where(
                    Order.account_id == account.id,
                    Order.idempotency_key.in_(order_keys.values()),
                )
            )
        )
        position_count = self.session.scalar(
            select(func.count(Position.id)).where(Position.account_id == account.id)
        ) or 0
        # 기존 수동/과거 포트폴리오는 자동으로 덮어쓰지 않는다. 다만 현재 스냅샷 주문이
        # 일부 체결된 재시도라면 같은 멱등성 키를 기준으로 남은 주문만 이어서 처리한다.
        if position_count > 0 and not existing_order_keys:
            return self._response(account.id, snapshot.as_of, len(target_weights), 0, "PROPOSAL_ONLY")

        created = 0
        starting_assets = Decimal(account.initial_cash)
        if starting_assets <= 0:
            starting_assets = Decimal(account.cash_balance)
        for stock_code, target_weight in target_weights.items():
            key = order_keys[stock_code]
            if key in existing_order_keys:
                continue
            price, _, _ = self.trading_service.market.get_price(stock_code)
            quantity = ((starting_assets * target_weight) / price).quantize(
                Decimal("0.00000001"),
                rounding=ROUND_DOWN,
            )
            if quantity <= 0:
                continue
            self.trading_service.execute_market_order(
                user_id,
                OrderCreateRequest(
                    account_id=account.id,
                    stock_code=stock_code,
                    side="BUY",
                    quantity=quantity,
                    idempotency_key=key,
                ),
            )
            created += 1

        status = "APPLIED" if created else "ALREADY_APPLIED"
        return self._response(account.id, snapshot.as_of, len(target_weights), created, status)

    def _publish_targets(
        self,
        effective_from,
        target_weights: dict[str, Decimal],
    ) -> None:
        existing = list(
            self.session.scalars(
                select(StrategyTargetWeight).where(
                    StrategyTargetWeight.strategy_id == "momentum",
                    StrategyTargetWeight.effective_from == effective_from,
                )
            )
        )
        if existing:
            current = {row.stock_code: Decimal(row.target_weight) for row in existing}
            if current != target_weights:
                raise ServiceError(
                    "MODEL_TARGET_VERSION_CONFLICT",
                    "같은 기준일의 모멘텀 목표 비중이 이미 다르게 저장되어 있습니다.",
                    409,
                )
            return
        self.session.add_all([
            StrategyTargetWeight(
                strategy_id="momentum",
                stock_code=stock_code,
                target_weight=weight,
                effective_from=effective_from,
            )
            for stock_code, weight in target_weights.items()
        ])
        self.session.commit()

    @staticmethod
    def _response(account_id, as_of, target_count, orders_created, status):
        return ModelRecommendationApplyResponse(
            account_id=account_id,
            strategy_id="momentum",
            as_of=as_of,
            target_count=target_count,
            orders_created=orders_created,
            status=status,
        )
