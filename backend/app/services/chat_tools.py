"""물방개가 사용할 수 있는 읽기 전용 도구 계층."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ServiceError
from app.repositories.market_data import MarketDataRepository
from app.repositories.recommendation import RecommendationRepository
from app.repositories.trading import TradingRepository
from app.schemas.api import StockSummaryResponse
from app.services.market import StockMarketService
from app.services.portfolio import PortfolioService

FINANCIAL_TERMS: dict[str, dict[str, object]] = {
    "PER": {
        "name": "주가수익비율",
        "definition": "주가를 주당순이익(EPS)으로 나눈 값으로, 이익 대비 주가의 배수를 보여줍니다.",
        "caution": "업종, 성장성, 일회성 이익을 함께 비교해야 하며 낮다고 항상 저평가를 뜻하지 않습니다.",
    },
    "PBR": {
        "name": "주가순자산비율",
        "definition": "주가를 주당순자산(BPS)으로 나눈 값으로, 순자산 대비 주가의 배수를 보여줍니다.",
        "caution": "자산의 수익성과 업종별 자산 구조를 함께 확인해야 합니다.",
    },
    "ROE": {
        "name": "자기자본이익률",
        "definition": "자기자본으로 얼마의 이익을 냈는지 나타내는 비율입니다.",
        "caution": "부채가 많아도 높아질 수 있으므로 부채 수준과 함께 확인해야 합니다.",
    },
    "MDD": {
        "name": "최대낙폭",
        "definition": "측정 기간 중 고점에서 저점까지의 가장 큰 하락 폭입니다.",
        "caution": "과거 측정값이며 미래 손실 한도를 보장하지 않습니다.",
    },
    "리밸런싱": {
        "name": "리밸런싱",
        "definition": "현재 자산 비중을 정해진 목표 비중에 맞게 조정하는 과정입니다.",
        "caution": "거래 비용과 세금, 시장 상황을 함께 고려해야 합니다.",
    },
}


def _now() -> datetime:
    return datetime.now(UTC)


def _require_consent(session: Session, user_id: int) -> None:
    if not RecommendationRepository(session).has_ai_personalization_consent(user_id):
        raise ServiceError(
            "AI_PERSONALIZATION_CONSENT_REQUIRED",
            "개인화된 계좌 안내를 이용하려면 AI 개인화 동의가 필요합니다.",
            403,
        )


def get_financial_term(term: str) -> dict[str, object]:
    """공개 금융 용어 정의를 반환한다."""

    normalized = term.strip().upper()
    for key, value in FINANCIAL_TERMS.items():
        if key.upper() == normalized or key in term:
            return {"term": key, **value, "source": "FE!N glossary", "as_of": _now()}
    raise NotFoundError(
        "FINANCIAL_TERM_NOT_FOUND", "지원하는 금융 용어를 찾을 수 없습니다."
    )


def get_strategy_catalog(session: Session) -> dict[str, object]:
    """활성 전략만 반환하며 주문·변경 정보는 포함하지 않는다."""

    strategies = TradingRepository(session).strategies()
    return {
        "items": [
            {
                "strategy_id": strategy.id,
                "name": strategy.name,
                "description": strategy.description,
                "risk_level": strategy.risk_level,
                "rebalance_cycle": strategy.rebalance_cycle,
            }
            for strategy in strategies
        ],
        "source": "strategies",
        "as_of": _now(),
    }


def get_stock_summary(
    session: Session,
    stock_code: str,
    *,
    market_service: StockMarketService | None = None,
) -> dict[str, object]:
    """KRX/OpenDART 요약을 반환하고 제공된 데이터만 노출한다."""

    summary: StockSummaryResponse = (
        market_service or StockMarketService(MarketDataRepository(session))
    ).summary(stock_code)
    return {
        **summary.model_dump(),
        "source": "KRX/OpenDART",
        "as_of": summary.as_of or _now(),
    }


def _account_for_request(
    session: Session,
    user_id: int,
    account_id: UUID | None,
):
    repo = TradingRepository(session)
    if account_id is not None:
        account = repo.owned_account(account_id, user_id)
    else:
        user = repo.user(user_id)
        mode = user.active_operation_mode if user else None
        account = repo.account_for_user(user_id, mode) if mode else None
        if account is None:
            accounts = repo.accounts_for_user(user_id)
            account = next((item for item in accounts if item.status == "ACTIVE"), None)
    if account is None or account.status != "ACTIVE":
        raise NotFoundError("ACCOUNT_NOT_FOUND", "활성 계좌를 찾을 수 없습니다.")
    return account


def get_my_account_summary(
    session: Session,
    user_id: int,
    *,
    account_id: UUID | None = None,
) -> dict[str, object]:
    _require_consent(session, user_id)
    account = _account_for_request(session, user_id, account_id)
    strategy = (
        TradingRepository(session).strategy(account.selected_strategy_id)
        if account.selected_strategy_id
        else None
    )
    return {
        "account_id": account.id,
        "account_name": account.account_name,
        "operation_mode": account.operation_mode,
        "status": account.status,
        "cash_balance": account.cash_balance,
        "invested_principal": account.invested_principal,
        "selected_strategy": (
            {"strategy_id": strategy.id, "name": strategy.name} if strategy else None
        ),
        "source": "virtual_accounts",
        "as_of": _now(),
    }


def get_my_portfolio_summary(
    session: Session,
    user_id: int,
    *,
    account_id: UUID | None = None,
) -> dict[str, object]:
    _require_consent(session, user_id)
    account = _account_for_request(session, user_id, account_id)
    portfolio = PortfolioService(session).evaluate(user_id, account.id)
    valuation_as_of = max(
        (position.price_as_of for position in portfolio.positions),
        default=None,
    )
    return {
        "account_id": account.id,
        "cash_balance": portfolio.cash_balance,
        "total_assets": portfolio.total_assets,
        "valuation_profit": portfolio.valuation_profit,
        "return_rate": portfolio.return_rate,
        "positions": [position.model_dump() for position in portfolio.positions],
        "source": "virtual_accounts/KIS/KRX",
        "as_of": valuation_as_of or _now(),
    }
