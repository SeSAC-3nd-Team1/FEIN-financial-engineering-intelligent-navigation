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
from db.models.trading import AccountDeposit, CashLedger, Execution, InvestmentOnboarding, Order, PortfolioSnapshot, Position, RebalancingDecision, Strategy, StrategyTargetWeight, VirtualAccount
from db.models.opendart import Company, CompanyDisclosure, CompanyFinancial, CompanyFinancialAccount
from db.models.market_data import MarketIndex, MarketStock, MarketStockPrice
from db.models.recommendation import InvestorProfileAssessment, StrategyRecommendation, StrategyRecommendationItem

__all__ = [
    "RegistrationAgreement",
    "RegistrationSession",
    "Term",
    "User",
    "UserAgreement",
    "CashLedger",
    "AccountDeposit",
    "Execution",
    "InvestmentOnboarding",
    "Order",
    "PortfolioSnapshot",
    "RebalancingDecision",
    "Position",
    "Strategy",
    "StrategyTargetWeight",
    "VirtualAccount",
    "Company",
    "CompanyDisclosure",
    "CompanyFinancial",
    "CompanyFinancialAccount",
    "MarketIndex",
    "MarketStock",
    "MarketStockPrice",
    "InvestorProfileAssessment",
    "StrategyRecommendation",
    "StrategyRecommendationItem",
]
