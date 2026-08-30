"""Generate a short explanation without changing backtest source-of-truth metrics."""

from datetime import UTC, datetime
import logging

from app.core.errors import ServiceError
from app.integrations.ai.backtest_explanation_client import BacktestExplanationAIClient
from app.schemas.api import BacktestAiExplanationResponse, BacktestAiInput

logger = logging.getLogger(__name__)


class BacktestExplanationService:
    def __init__(self, client: BacktestExplanationAIClient | None) -> None:
        self.client = client

    @staticmethod
    def fallback(context: BacktestAiInput) -> BacktestAiExplanationResponse:
        difference = context.benchmark_difference
        if difference > 0:
            headline = f"{context.benchmark_name}보다 {abs(difference)}%p 높은 성과였어요"
        elif difference < 0:
            headline = f"{context.benchmark_name}보다 {abs(difference)}%p 낮은 성과였어요"
        else:
            headline = f"{context.benchmark_name}과 같은 누적 수익률이었어요"
        comparison = (
            f"{context.benchmark_name}보다 {abs(difference)}%p 높았어요."
            if difference >= 0
            else f"{context.benchmark_name}보다 {abs(difference)}%p 낮았어요."
        )
        sharpe = "" if context.sharpe is None else f" 샤프 지수는 {context.sharpe}였어요."
        return BacktestAiExplanationResponse(
            headline=headline,
            overview=f"{context.period_label} 동안 {context.strategy_name}은 누적 {context.cumulative_return}%를 기록했고, {comparison}",
            caution=f"이 기간 최대 낙폭은 {context.mdd}%, 연환산 변동성은 {context.volatility}%였어요.{sharpe}",
            generated_at=datetime.now(UTC),
        )

    async def explain(self, context: BacktestAiInput) -> BacktestAiExplanationResponse:
        if self.client is None:
            return self.fallback(context)
        try:
            return await self.client.explain(context)
        except ServiceError as exc:
            if not exc.code.startswith("AI_"):
                raise
            logger.warning("Backtest AI explanation unavailable code=%s", exc.code)
            return self.fallback(context)
        except Exception:
            logger.exception("Unexpected backtest AI explanation failure")
            return self.fallback(context)
