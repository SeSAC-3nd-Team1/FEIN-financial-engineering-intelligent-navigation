from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.errors import NotFoundError, ServiceError
from app.schemas.api import StockSummaryResponse
from app.services import chat_tools


class FakeSession:
    pass


def test_get_financial_term_includes_source_and_as_of() -> None:
    result = chat_tools.get_financial_term("per")

    assert result["term"] == "PER"
    assert result["source"] == "FE!N glossary"
    assert result["as_of"] is not None


def test_get_financial_term_rejects_unknown_term() -> None:
    with pytest.raises(NotFoundError) as error:
        chat_tools.get_financial_term("UNKNOWN")

    assert error.value.code == "FINANCIAL_TERM_NOT_FOUND"


def test_stock_summary_preserves_source_and_as_of() -> None:
    summary = StockSummaryResponse(
        stock_code="005930",
        stock_name="삼성전자",
        market="KOSPI",
        sector="전기전자",
        listing_date=None,
        listed_shares=None,
        security_type="COMMON",
        description=None,
        price=None,
        previous_close=None,
        change_amount=None,
        change_rate=None,
        volume=None,
        market_cap=None,
        per=None,
        pbr=None,
        roe=None,
        dividend_yield=None,
        financial_year=None,
        as_of=None,
        sources={},
    )

    class FakeMarketService:
        def summary(self, stock_code):
            assert stock_code == "005930"
            return summary

    result = chat_tools.get_stock_summary(
        FakeSession(), "005930", market_service=FakeMarketService()
    )

    assert result["stock_code"] == "005930"
    assert result["source"] == "KRX/OpenDART"
    assert result["as_of"] is not None


def test_personal_tools_require_ai_consent(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_tools.RecommendationRepository,
        "has_ai_personalization_consent",
        lambda *_: False,
    )

    with pytest.raises(ServiceError) as error:
        chat_tools.get_my_account_summary(FakeSession(), 7)

    assert error.value.code == "AI_PERSONALIZATION_CONSENT_REQUIRED"
    assert error.value.status_code == 403


def test_account_tool_uses_owned_active_account_and_selected_strategy(
    monkeypatch,
) -> None:
    account = SimpleNamespace(
        id=uuid4(),
        status="ACTIVE",
        account_name="내 계좌",
        operation_mode="SEMI_AUTO",
        cash_balance=1000,
        invested_principal=5000,
        selected_strategy_id="balanced",
    )
    strategy = SimpleNamespace(id="balanced", name="균형형")
    monkeypatch.setattr(
        chat_tools.RecommendationRepository,
        "has_ai_personalization_consent",
        lambda *_: True,
    )
    monkeypatch.setattr(
        chat_tools.TradingRepository,
        "owned_account",
        lambda *_: account,
    )
    monkeypatch.setattr(chat_tools.TradingRepository, "strategy", lambda *_: strategy)

    result = chat_tools.get_my_account_summary(FakeSession(), 7, account_id=account.id)

    assert result["account_id"] == account.id
    assert result["selected_strategy"] == {"strategy_id": "balanced", "name": "균형형"}
    assert result["source"] == "virtual_accounts"
    assert result["as_of"] is not None


def test_account_tool_rejects_missing_account(monkeypatch) -> None:
    monkeypatch.setattr(
        chat_tools.RecommendationRepository,
        "has_ai_personalization_consent",
        lambda *_: True,
    )
    monkeypatch.setattr(chat_tools.TradingRepository, "owned_account", lambda *_: None)

    with pytest.raises(NotFoundError) as error:
        chat_tools.get_my_account_summary(FakeSession(), 7, account_id=uuid4())

    assert error.value.code == "ACCOUNT_NOT_FOUND"


def test_strategy_catalog_is_read_only_and_active(monkeypatch) -> None:
    strategies = [
        SimpleNamespace(
            id="balanced",
            name="균형형",
            description="분산 전략",
            risk_level="MEDIUM",
            rebalance_cycle="MONTHLY",
        )
    ]
    monkeypatch.setattr(
        chat_tools.TradingRepository, "strategies", lambda *_: strategies
    )

    result = chat_tools.get_strategy_catalog(FakeSession())

    assert result["items"][0]["strategy_id"] == "balanced"
    assert result["source"] == "strategies"
    assert "order" not in result["items"][0]
