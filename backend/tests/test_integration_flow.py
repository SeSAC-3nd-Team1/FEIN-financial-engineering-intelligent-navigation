"""seeded PostgreSQL/Redis를 사용하는 회원→가상거래 E2E."""

from datetime import UTC, datetime
from decimal import Decimal
import json
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
import redis
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models import AccountDeposit, CashLedger, Execution, InvestmentOnboarding, Order, Position, Term, User, UserAgreement, VirtualAccount

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 required")


def _cleanup_test_user(user_id: str, cache: redis.Redis, stock_code: str) -> None:
    """이 테스트가 만든 관계만 FK 역순으로 제거한다."""
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.user_id == user_id))
        if user:
            account_ids = list(session.scalars(select(VirtualAccount.id).where(VirtualAccount.user_id == user.id)))
            if account_ids:
                session.execute(delete(AccountDeposit).where(AccountDeposit.account_id.in_(account_ids)))
                session.execute(delete(Execution).where(Execution.account_id.in_(account_ids)))
                session.execute(delete(CashLedger).where(CashLedger.account_id.in_(account_ids)))
                session.execute(delete(Order).where(Order.account_id.in_(account_ids)))
                session.execute(delete(Position).where(Position.account_id.in_(account_ids)))
            session.execute(delete(InvestmentOnboarding).where(InvestmentOnboarding.user_id == user.id))
            if account_ids:
                session.execute(delete(VirtualAccount).where(VirtualAccount.id.in_(account_ids)))
            session.execute(delete(UserAgreement).where(UserAgreement.user_id == user.id))
            session.delete(user)
            session.commit()
        assert session.scalar(select(User).where(User.user_id == user_id)) is None
    cache.delete(f"price:{stock_code}")


def _signup_payload(user_id: str, suffix: str, agreements: list[dict]) -> dict:
    return {
        "user_id": user_id,
        "password": "Integration!51",
        "name": "통합테스트",
        "birthdate": "900101",
        "phone_number": f"010{int(suffix, 16) % 100_000_000:08d}",
        "email": f"{user_id}@example.com",
        "phone_verified": True,
        "email_verified": True,
        "agreements": agreements,
    }


def test_seeded_terms_signup_and_virtual_trading_end_to_end() -> None:
    suffix = uuid4().hex[:8]
    user_id = f"e2e{suffix}"[:16]
    missing_user_id = f"m{suffix}"
    declined_user_id = f"f{suffix}"
    invalid_user_id = f"i{suffix}"
    test_user_ids = [user_id, missing_user_id, declined_user_id, invalid_user_id]
    stock_code = f"E{suffix[:5]}".upper()
    cache = redis.from_url(settings.redis_url, decode_responses=True)

    try:
        cache.setex(
            f"price:{stock_code}",
            300,
            json.dumps({"price": "70000", "as_of": datetime.now(UTC).isoformat()}),
        )

        with TestClient(app) as client:
            terms_response = client.get("/api/v1/auth/terms")
            assert terms_response.status_code == 200, terms_response.text
            terms = terms_response.json()
            required = [term for term in terms if term["is_required"]]
            assert required, "integration DB must contain seeded required terms"
            accepted = [
                {"term_code": term["term_code"], "version": term["version"], "agreed": True}
                for term in terms
            ]
            first_required_key = (required[0]["term_code"], required[0]["version"])
            missing_agreements = [
                item for item in accepted
                if (item["term_code"], item["version"]) != first_required_key
            ]

            missing = client.post(
                "/api/v1/auth/signup",
                json=_signup_payload(missing_user_id, suffix, missing_agreements),
            )
            assert missing.status_code == 400
            assert missing.json()["code"] == "REQUIRED_TERMS_NOT_AGREED"

            declined = [dict(item) for item in accepted]
            next(
                item for item in declined
                if (item["term_code"], item["version"]) == first_required_key
            )["agreed"] = False
            false_agreement = client.post(
                "/api/v1/auth/signup",
                json=_signup_payload(declined_user_id, suffix, declined),
            )
            assert false_agreement.status_code == 400
            assert false_agreement.json()["code"] == "REQUIRED_TERMS_NOT_AGREED"

            invalid = [
                *accepted,
                {"term_code": required[0]["term_code"], "version": "not-current", "agreed": True},
            ]
            invalid_term = client.post(
                "/api/v1/auth/signup",
                json=_signup_payload(invalid_user_id, suffix, invalid),
            )
            assert invalid_term.status_code == 400
            assert invalid_term.json()["code"] == "INVALID_TERM_VERSION"

            signup = client.post("/api/v1/auth/signup", json=_signup_payload(user_id, suffix, accepted))
            assert signup.status_code == 201, signup.text

            with SessionLocal() as session:
                user = session.scalar(select(User).where(User.user_id == user_id))
                assert user is not None
                agreement_rows = session.execute(
                    select(UserAgreement, Term)
                    .join(Term, Term.id == UserAgreement.term_id)
                    .where(UserAgreement.user_id == user.id)
                ).all()
                assert {(term.term_code, term.version) for _, term in agreement_rows} == {
                    (term["term_code"], term["version"]) for term in terms
                }
                assert all(agreement.is_agreed and agreement.agreed_at for agreement, _ in agreement_rows)

            login = client.post(
                "/api/v1/auth/login",
                json={"user_id": user_id, "password": "Integration!51"},
            )
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            me = client.get("/api/v1/auth/me", headers=headers)
            assert me.status_code == 200, me.text
            assert me.json()["user_id"] == user_id

            onboarding = client.post(
                "/api/v1/investment/onboardings",
                headers=headers,
                json={
                    "strategy_id": "low",
                    "investment_amount": 1_000_000,
                    "operation_mode": "AUTO",
                },
            )
            assert onboarding.status_code == 200, onboarding.text
            onboarding_id = onboarding.json()["id"]
            investment_terms = client.get(
                "/api/v1/investment/terms?strategy_id=low",
                headers=headers,
            )
            assert investment_terms.status_code == 200, investment_terms.text
            investment_agreements = [
                {
                    "term_code": term["term_code"],
                    "version": term["version"],
                    "agreed": True,
                }
                for term in investment_terms.json()
            ]
            agreed = client.post(
                f"/api/v1/investment/onboardings/{onboarding_id}/agreements",
                headers=headers,
                json={"agreements": investment_agreements},
            )
            assert agreed.status_code == 200, agreed.text
            assert agreed.json()["next_step"] == "ACCOUNT"
            prepared = client.post(
                f"/api/v1/investment/onboardings/{onboarding_id}/account",
                headers=headers,
                json={"account_name": "통합테스트 계좌"},
            )
            assert prepared.status_code == 200, prepared.text
            assert prepared.json()["created"] is True
            assert prepared.json()["account"]["operation_mode"] == "AUTO"
            assert prepared.json()["account"]["initial_cash"] == "0.00"
            assert prepared.json()["account"]["cash_balance"] == "0.00"
            assert prepared.json()["required_deposit_amount"] == "1000000.00"
            assert prepared.json()["onboarding"]["next_step"] == "DEPOSIT"
            account_id = prepared.json()["account"]["id"]
            deposited = client.post(
                f"/api/v1/investment/onboardings/{onboarding_id}/deposit",
                headers=headers,
                json={
                    "amount": 1_000_000,
                    "idempotency_key": f"deposit-{suffix}",
                },
            )
            assert deposited.status_code == 200, deposited.text
            assert deposited.json()["balance_after"] == "1000000.00"
            assert deposited.json()["required_deposit_amount"] == "0.00"
            assert deposited.json()["onboarding"]["next_step"] == "CONFIRM"
            deposit_retry = client.post(
                f"/api/v1/investment/onboardings/{onboarding_id}/deposit",
                headers=headers,
                json={
                    "amount": 1_000_000,
                    "idempotency_key": f"deposit-{suffix}",
                },
            )
            assert deposit_retry.status_code == 200
            assert deposit_retry.json()["deposit_id"] == deposited.json()["deposit_id"]
            completed = client.post(
                f"/api/v1/investment/onboardings/{onboarding_id}/complete",
                headers=headers,
            )
            assert completed.status_code == 200, completed.text
            assert completed.json()["next_step"] == "PORTFOLIO"
            repeated_prepare = client.post(
                f"/api/v1/investment/onboardings/{onboarding_id}/account",
                headers=headers,
                json={"account_name": "무시되는 계좌명"},
            )
            assert repeated_prepare.status_code == 200, repeated_prepare.text
            assert repeated_prepare.json()["created"] is False
            assert repeated_prepare.json()["onboarding"]["next_step"] == "PORTFOLIO"
            repeated_complete = client.post(
                f"/api/v1/investment/onboardings/{onboarding_id}/complete",
                headers=headers,
            )
            assert repeated_complete.status_code == 200, repeated_complete.text
            assert repeated_complete.json()["completed_at"] == completed.json()["completed_at"]

            semi_onboarding = client.post(
                "/api/v1/investment/onboardings",
                headers=headers,
                json={
                    "strategy_id": "low",
                    "investment_amount": 500_000,
                    "operation_mode": "SEMI_AUTO",
                },
            )
            assert semi_onboarding.status_code == 200, semi_onboarding.text
            semi_onboarding_id = semi_onboarding.json()["id"]
            assert semi_onboarding.json()["next_step"] == "ACCOUNT"
            semi_prepared = client.post(
                f"/api/v1/investment/onboardings/{semi_onboarding_id}/account",
                headers=headers,
                json={"account_name": "반자동 통합테스트 계좌"},
            )
            assert semi_prepared.status_code == 200, semi_prepared.text
            assert semi_prepared.json()["account"]["operation_mode"] == "SEMI_AUTO"
            assert semi_prepared.json()["account"]["id"] != account_id
            all_accounts = client.get("/api/v1/accounts/me/all", headers=headers)
            assert all_accounts.status_code == 200, all_accounts.text
            assert {account["operation_mode"] for account in all_accounts.json()} == {
                "AUTO",
                "SEMI_AUTO",
            }

            buy_payload = {
                "account_id": account_id,
                "stock_code": stock_code,
                "side": "BUY",
                "order_type": "MARKET",
                "quantity": 10,
                "idempotency_key": f"buy-{suffix}",
            }
            buy = client.post("/api/v1/orders", headers=headers, json=buy_payload)
            assert buy.status_code == 201, buy.text
            assert buy.json()["status"] == "FILLED"
            retry = client.post("/api/v1/orders", headers=headers, json=buy_payload)
            assert retry.status_code == 201
            assert retry.json()["id"] == buy.json()["id"]

            portfolio = client.get(f"/api/v1/portfolio?account_id={account_id}", headers=headers)
            assert portfolio.status_code == 200, portfolio.text
            assert Decimal(portfolio.json()["positions"][0]["quantity"]) == Decimal("10")
            assert portfolio.json()["total_assets"] == "1000000.00"

            sell = client.post("/api/v1/orders", headers=headers, json={
                "account_id": account_id,
                "stock_code": stock_code,
                "side": "SELL",
                "order_type": "MARKET",
                "quantity": 4,
                "idempotency_key": f"sell-{suffix}",
            })
            assert sell.status_code == 201, sell.text
            after = client.get(f"/api/v1/portfolio?account_id={account_id}", headers=headers).json()
            assert Decimal(after["positions"][0]["quantity"]) == Decimal("6")
            assert after["cash_balance"] == "580000.00"

            with SessionLocal() as session:
                account = session.get(VirtualAccount, account_id)
                latest_ledger = session.scalar(
                    select(CashLedger)
                    .where(CashLedger.account_id == account_id)
                    .order_by(CashLedger.created_at.desc(), CashLedger.id.desc())
                    .limit(1)
                )
                orders = list(session.scalars(select(Order).where(Order.account_id == account_id)))
                executions = list(session.scalars(select(Execution).where(Execution.account_id == account_id)))
                assert account is not None and latest_ledger is not None
                assert account.initial_cash == Decimal("1000000.00")
                assert account.cash_balance == latest_ledger.balance_after
                assert len(orders) == len(executions) == 2
                assert {execution.order_id for execution in executions} == {order.id for order in orders}
    finally:
        for test_user_id in test_user_ids:
            _cleanup_test_user(test_user_id, cache, stock_code)
