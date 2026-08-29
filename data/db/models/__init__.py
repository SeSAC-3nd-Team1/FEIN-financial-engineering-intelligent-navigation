"""Alembic과 애플리케이션이 공통으로 import하는 ORM model registry다.

금융/API PostgreSQL schema는 별도 재설계 중이며, 현재 registry에는 회원가입/회원 데이터
관계만 등록한다. 가입 전 임시 상태도 PostgreSQL에 보관하므로 registration 모델까지
Alembic metadata에 포함한다.
"""

from db.models.membership import (
    RegistrationAgreement,
    RegistrationSession,
    Term,
    User,
    UserAgreement,
)
from db.models.trading import (
    AccountCashDeposit,
    AccountDeposit,
    CashLedger,
    Execution,
    FundOperation,
    FundOperationOrder,
    InvestmentOnboarding,
    MomentumRebalanceRun,
    Order,
    PortfolioSnapshot,
    Position,
    RebalancingDecision,
    Strategy,
    StrategyTargetWeight,
    UserCarGoal,
    VirtualAccount,
)
from db.models.opendart import (
    Company,
    CompanyDisclosure,
    CompanyFinancial,
    CompanyFinancialAccount,
    StockDividend,
)
from db.models.market_data import MarketIndex, MarketStock, MarketStockPrice
from db.models.recommendation import (
    InvestorProfileAssessment,
    StrategyRecommendation,
    StrategyRecommendationItem,
)

__all__ = [
    "RegistrationAgreement",
    "RegistrationSession",
    "Term",
    "User",
    "UserAgreement",
    "CashLedger",
    "AccountCashDeposit",
    "AccountDeposit",
    "Execution",
    "FundOperation",
    "FundOperationOrder",
    "InvestmentOnboarding",
    "MomentumRebalanceRun",
    "Order",
    "PortfolioSnapshot",
    "RebalancingDecision",
    "Position",
    "Strategy",
    "StrategyTargetWeight",
    "UserCarGoal",
    "VirtualAccount",
    "Company",
    "CompanyDisclosure",
    "CompanyFinancial",
    "CompanyFinancialAccount",
    "StockDividend",
    "MarketIndex",
    "MarketStock",
    "MarketStockPrice",
    "InvestorProfileAssessment",
    "StrategyRecommendation",
    "StrategyRecommendationItem",
]
