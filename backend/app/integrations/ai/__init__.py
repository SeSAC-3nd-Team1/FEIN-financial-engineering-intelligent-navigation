"""AI provider integrations."""

from app.integrations.ai.backtest_explanation_client import AzureOpenAIBacktestExplanationClient
from app.integrations.ai.investor_profile_client import AzureOpenAIInvestorProfileClient
from app.integrations.ai.portfolio_comparison_client import AzureOpenAIPortfolioComparisonClient
from app.integrations.ai.rebalancing_client import AzureOpenAIRebalancingClient
from app.integrations.ai.strategy_recommendation_client import AzureOpenAIStrategyRecommendationClient

__all__ = [
    "AzureOpenAIBacktestExplanationClient",
    "AzureOpenAIInvestorProfileClient",
    "AzureOpenAIPortfolioComparisonClient",
    "AzureOpenAIRebalancingClient",
    "AzureOpenAIStrategyRecommendationClient",
]
