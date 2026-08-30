"""Publish a validated momentum snapshot and deploy a new AUTO virtual account."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.models import MomentumRebalanceRun, Order, Position, StrategyTargetWeight
from app.repositories import TradingRepository
from app.schemas.api import ModelRecommendationApplyResponse, OrderCreateRequest
from app.services.model_recommendation import ModelRecommendationService
from app.services.trading import TradingService


class MomentumInvestmentService:
    @staticmethod
    def _is_quarter_end_snapshot(as_of: date) -> bool:
        # This is only a cheap quarter-membership guard.  The authoritative
        # decision date is the latest KOSPI trade date returned by the
        # repository below; never use a calendar-day tolerance here.
        return as_of.month in (3, 6, 9, 12)

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
        if (
            snapshot.source != "generated"
            or snapshot.is_stale
            or getattr(snapshot, "model_version", None) != "risk-adjusted-momentum-v2"
        ):
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
        # momentum 모델만 주식 95% + 현금 5% 정책을 허용한다. 다른 비중 누락은
        # 모델 산출 오류로 간주해 적용하지 않는다.
        if (
            not target_weights
            or len(target_weights) != len(snapshot.recommendations)
            or any(weight > Decimal("0.05") for weight in target_weights.values())
            or total_weight != Decimal("0.95")
        ):
            raise ServiceError(
                "INVALID_STRATEGY_TARGET_WEIGHTS",
                "모멘텀 목표 주식 비중 합계는 0.95여야 합니다(현금 0.05 포함).",
                503,
            )
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
        position_count = (
            self.session.scalar(
                select(func.count(Position.id)).where(Position.account_id == account.id)
            )
            or 0
        )
        # A newly created empty account may encounter a target row left by the
        # demo seed or an older model artifact for the same as_of date. The
        # generated snapshot is authoritative for the first application. Once
        # an account has positions or orders, keep the conflict guard so a
        # changed model cannot silently rewrite an active portfolio's target.
        self._publish_targets(
            snapshot.as_of,
            target_weights,
            replace_existing=position_count == 0 and not existing_order_keys,
        )

        if account.operation_mode != "AUTO":
            return self._response(
                account.id, snapshot.as_of, len(target_weights), 0, "PROPOSAL_ONLY"
            )

        # 기존 수동/과거 포트폴리오는 자동으로 덮어쓰지 않는다. 다만 현재 스냅샷 주문이
        # 일부 체결된 재시도라면 같은 멱등성 키를 기준으로 남은 주문만 이어서 처리한다.
        if position_count > 0 and not existing_order_keys:
            return self._response(
                account.id, snapshot.as_of, len(target_weights), 0, "PROPOSAL_ONLY"
            )

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
        return self._response(
            account.id, snapshot.as_of, len(target_weights), created, status
        )

    def rebalance(self, user_id: int, account_id) -> ModelRecommendationApplyResponse:
        """Apply a generated v2 quarter target to an existing AUTO account.

        This intentionally remains an internal service operation: scheduling is
        outside the request path, and no external brokerage order is involved.
        Each leg has a stable snapshot/account/symbol/side key, so a retry after
        a partial run only submits missing legs.
        """
        account = self.repo.owned_account(account_id, user_id)
        if account is None:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        if account.selected_strategy_id != "momentum":
            raise ServiceError("MOMENTUM_STRATEGY_REQUIRED", "모멘텀 계좌만 리밸런싱할 수 있습니다.", 409)
        snapshot = self.snapshot_service.latest()
        if (snapshot.source != "generated" or snapshot.is_stale or
                getattr(snapshot, "model_version", None) != "risk-adjusted-momentum-v2"):
            raise ServiceError("MODEL_RECOMMENDATION_NOT_APPLICABLE", "안전한 v2 스냅샷이 없어 리밸런싱하지 않습니다.", 409)
        if not self._is_quarter_end_snapshot(snapshot.as_of):
            raise ServiceError(
                "MOMENTUM_QUARTER_END_SNAPSHOT_REQUIRED",
                "분기 말 공식 모멘텀 스냅샷만 리밸런싱할 수 있습니다.",
                409,
            )
        quarter = (snapshot.as_of.month - 1) // 3 + 1
        expected_date = self.repo.quarter_end_trade_date(snapshot.as_of.year, quarter)
        if expected_date != snapshot.as_of:
            raise ServiceError(
                "MOMENTUM_QUARTER_END_SNAPSHOT_REQUIRED",
                "KRX 해당 분기의 마지막 거래일 snapshot만 리밸런싱할 수 있습니다.",
                409,
            )
        targets = {item.symbol: Decimal(str(item.target_weight)) for item in snapshot.recommendations if item.target_weight > 0}
        if (
            not targets
            or len(targets) != len(snapshot.recommendations)
            or any(weight > Decimal("0.05") for weight in targets.values())
            or sum(targets.values(), Decimal("0")) != Decimal("0.95")
        ):
            raise ServiceError("INVALID_STRATEGY_TARGET_WEIGHTS", "v2 목표 주식 비중 합계는 0.95여야 합니다.", 503)
        if account.operation_mode != "AUTO":
            self._publish_targets(snapshot.as_of, targets)
            return self._response(account.id, snapshot.as_of, len(targets), 0, "PROPOSAL_ONLY")
        # Publishing is deliberately outside the critical section. Re-acquire
        # the account lock immediately before creating/reading the run and
        # keep that transaction open through plan persistence.
        self._publish_targets(snapshot.as_of, targets)
        account = self.repo.owned_account(account_id, user_id, lock=True)
        if account is None:
            raise NotFoundError("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없습니다.")
        run = self.repo.momentum_rebalance_run(account.id, snapshot.as_of.year, quarter, lock=True)
        if run is not None and run.snapshot_date != snapshot.as_of:
            raise ServiceError(
                "MOMENTUM_QUARTER_ALREADY_EXECUTED",
                "해당 계좌는 이번 분기 모멘텀 리밸런싱을 이미 실행했습니다.",
                409,
            )
        if run is not None and run.status == "COMPLETED":
            return self._response(account.id, snapshot.as_of, len(targets), 0, "ALREADY_APPLIED")
        positions = self.repo.positions(account.id)
        if not positions:
            # Do not create an uncommitted run before apply(): TradingService
            # owns a rollback boundary and would otherwise erase that run.
            response = self.apply(user_id, account_id)
            run = MomentumRebalanceRun(
                account_id=account.id,
                execution_year=snapshot.as_of.year,
                execution_quarter=quarter,
                snapshot_date=snapshot.as_of,
                status="COMPLETED",
            )
            self.session.add(run)
            self.session.commit()
            return response
        if run is None:
            run = MomentumRebalanceRun(
                account_id=account.id,
                execution_year=snapshot.as_of.year,
                execution_quarter=quarter,
                snapshot_date=snapshot.as_of,
                status="RUNNING",
            )
            self.session.add(run)
            self.session.flush()
        if getattr(run, "plan", None) is None:
            prices: dict[str, Decimal] = {}
            current_values: dict[str, Decimal] = {}
            for position in positions:
                price, _, _ = self.trading_service.market.get_price(position.stock_code)
                prices[position.stock_code] = Decimal(price)
                current_values[position.stock_code] = Decimal(position.quantity) * Decimal(price)
            total_assets = Decimal(account.cash_balance) + sum(current_values.values(), Decimal("0"))
            if total_assets <= 0:
                raise ServiceError("INVALID_PORTFOLIO_VALUE", "리밸런싱할 포트폴리오 가치가 없습니다.", 409)
            symbols = sorted(set(current_values) | set(targets))
            plan: list[dict[str, str]] = []
            for side in ("SELL", "BUY"):
                for symbol in symbols:
                    current_value = current_values.get(symbol, Decimal("0"))
                    target_value = total_assets * targets.get(symbol, Decimal("0"))
                    delta = target_value - current_value
                    if (side == "SELL" and delta >= 0) or (side == "BUY" and delta <= 0):
                        continue
                    if symbol not in prices:
                        price, _, _ = self.trading_service.market.get_price(symbol)
                        prices[symbol] = Decimal(price)
                    quantity = (abs(delta) / prices[symbol]).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
                    if quantity > 0:
                        plan.append({"symbol": symbol, "side": side, "quantity": str(quantity)})
            run.plan = plan
        # The first commit fixes the plan while the account/run locks are held.
        self.session.commit()
        plan = run.plan or []
        created = 0
        for leg in plan:
            symbol = str(leg["symbol"])
            side = str(leg["side"])
            quantity = Decimal(str(leg["quantity"]))
            key = f"momentum-rebalance-{snapshot.as_of.isoformat()}-{account.id}-{symbol}-{side}"
            existing = self.repo.order_by_idempotency(account.id, key)
            if existing:
                if (
                    existing.stock_code != symbol
                    or existing.side != side
                    or Decimal(existing.quantity) != quantity
                ):
                    raise ServiceError(
                        "MOMENTUM_REBALANCE_PLAN_CONFLICT",
                        "저장된 리밸런싱 계획과 기존 주문이 일치하지 않습니다.",
                        409,
                    )
                continue
            self.trading_service.execute_market_order(user_id, OrderCreateRequest(
                account_id=account.id, stock_code=symbol, side=side,
                quantity=quantity, idempotency_key=key,
            ))
            created += 1
        run = self.repo.momentum_rebalance_run(account.id, snapshot.as_of.year, quarter)
        run.status = "COMPLETED"
        self.session.commit()
        return self._response(account.id, snapshot.as_of, len(targets), created, "APPLIED" if created else "ALREADY_APPLIED")

    def _publish_targets(
        self,
        effective_from,
        target_weights: dict[str, Decimal],
        *,
        replace_existing: bool = False,
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
                if replace_existing:
                    for row in existing:
                        self.session.delete(row)
                    self.session.flush()
                    self.session.add_all(
                        [
                            StrategyTargetWeight(
                                strategy_id="momentum",
                                stock_code=stock_code,
                                target_weight=weight,
                                effective_from=effective_from,
                            )
                            for stock_code, weight in target_weights.items()
                        ]
                    )
                    self.session.commit()
                    return
                raise ServiceError(
                    "MODEL_TARGET_VERSION_CONFLICT",
                    "같은 기준일의 모멘텀 목표 비중이 이미 다르게 저장되어 있습니다.",
                    409,
                )
            return
        self.session.add_all(
            [
                StrategyTargetWeight(
                    strategy_id="momentum",
                    stock_code=stock_code,
                    target_weight=weight,
                    effective_from=effective_from,
                )
                for stock_code, weight in target_weights.items()
            ]
        )
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
