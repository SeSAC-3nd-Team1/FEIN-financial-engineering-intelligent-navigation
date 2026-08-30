"""seeded PostgreSQL/Redis를 사용하는 회원→가상거래 E2E."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import os
import secrets
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
import redis
from sqlalchemy import delete, select

from app.core.config import settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AccountDeposit,
    CashLedger,
    Execution,
    InvestmentOnboarding,
    Order,
    PortfolioSnapshot,
    Position,
    Term,
    User,
    UserAgreement,
    VirtualAccount,
)
from app.repositories.email_verification import RedisEmailVerificationRepository

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 required")


def _cleanup_test_user(user_id: str, cache: redis.Redis, stock_code: str) -> None:
    """이 테스트가 만든 관계만 FK 역순으로 제거한다."""
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.user_id == user_id))
        if user:
            account_ids = list(session.scalars(select(VirtualAccount.id).where(VirtualAccount.user_id == user.id)))
            if account_ids:
                session.execute(delete(AccountDeposit).where(AccountDeposit.account_id.in_(account_ids)))
                session.execute(delete(PortfolioSnapshot).where(PortfolioSnapshot.account_id.in_(account_ids)))
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


def _signup_payload(
    user_id: str,
    suffix: str,
    agreements: list[dict],
    verification_token: str = "x" * 32,
) -> dict:
    return {
        "user_id": user_id,
        "password": "Integration!51",
        "name": "통합테스트",
        "birthdate": "900101",
        "phone_number": f"010{int(suffix, 16) % 100_000_000:08d}",
        "email": f"{user_id}@example.com",
        "email_verification_token": verification_token,
        "agreements": agreements,
    }


def _verified_signup_payload(
    cache: redis.Redis,
    user_id: str,
    suffix: str,
    agreements: list[dict],
) -> dict:
    """외부 메일 발송 없이 Redis에 검증 완료 증명을 준비해 통합 가입 흐름을 검증한다."""

    token = secrets.token_urlsafe(32)
    repository = RedisEmailVerificationRepository(cache)
    repository.create_verification_token(
        sha256(token.encode()).hexdigest(),
        f"{user_id}@example.com",
        settings.email_verification_token_ttl_seconds,
    )
    return _signup_payload(user_id, suffix, agreements, token)


def test_seeded_terms_signup_and_virtual_trading_end_to_end() -> None:
    suffix = uuid4().hex[:8]
    user_id = f"e2e{suffix}"[:16]
    missing_user_id = f"m{suffix}"
    declined_user_id = f"f{suffix}"
    invalid_user_id = f"i{suffix}"
    intruder_suffix = uuid4().hex[:8]
    intruder_user_id = f"x{intruder_suffix}"
    test_user_ids = [user_id, missing_user_id, declined_user_id, invalid_user_id, intruder_user_id]
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

            signup = client.post(
                "/api/v1/auth/signup",
                json=_verified_signup_payload(cache, user_id, suffix, accepted),
            )
            assert signup.status_code == 201, signup.text

            intruder_signup = client.post(
                "/api/v1/auth/signup",
                json=_verified_signup_payload(
                    cache,
                    intruder_user_id,
                    intruder_suffix,
                    accepted,
                ),
            )
            assert intruder_signup.status_code == 201, intruder_signup.text
            intruder_login = client.post(
                "/api/v1/auth/login",
                json={"user_id": intruder_user_id, "password": "Integration!51"},
            )
            assert intruder_login.status_code == 200, intruder_login.text
            intruder_headers = {
                "Authorization": f"Bearer {intruder_login.json()['access_token']}"
            }

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
            active_after_auto = client.get("/api/v1/auth/me", headers=headers)
            assert active_after_auto.status_code == 200, active_after_auto.text
            assert active_after_auto.json()["active_operation_mode"] == "AUTO"

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
            semi_account_id = semi_prepared.json()["account"]["id"]
            semi_deposited = client.post(
                f"/api/v1/investment/onboardings/{semi_onboarding_id}/deposit",
                headers=headers,
                json={
                    "amount": 500_000,
                    "idempotency_key": f"semi-deposit-{suffix}",
                },
            )
            assert semi_deposited.status_code == 200, semi_deposited.text
            semi_completed = client.post(
                f"/api/v1/investment/onboardings/{semi_onboarding_id}/complete",
                headers=headers,
            )
            assert semi_completed.status_code == 200, semi_completed.text
            assert semi_completed.json()["next_step"] == "PORTFOLIO"

            switched_auto = client.put(
                "/api/v1/accounts/me/active-operation-mode",
                headers=headers,
                json={"operation_mode": "AUTO"},
            )
            assert switched_auto.status_code == 200, switched_auto.text
            assert switched_auto.json()["previous_operation_mode"] == "SEMI_AUTO"
            assert switched_auto.json()["operation_mode"] == "AUTO"
            assert switched_auto.json()["changed"] is True
            assert switched_auto.json()["account"]["id"] == account_id
            assert switched_auto.json()["notice"]["code"] == "OPERATION_MODE_CHANGED"

            switch_retry = client.put(
                "/api/v1/accounts/me/active-operation-mode",
                headers=headers,
                json={"operation_mode": "AUTO"},
            )
            assert switch_retry.status_code == 200, switch_retry.text
            assert switch_retry.json()["changed"] is False
            assert switch_retry.json()["notice"]["code"] == "OPERATION_MODE_UNCHANGED"

            switched_semi = client.put(
                "/api/v1/accounts/me/active-operation-mode",
                headers=headers,
                json={"operation_mode": "SEMI_AUTO"},
            )
            assert switched_semi.status_code == 200, switched_semi.text
            assert switched_semi.json()["previous_operation_mode"] == "AUTO"
            assert switched_semi.json()["operation_mode"] == "SEMI_AUTO"
            assert switched_semi.json()["account"]["id"] == semi_account_id
            assert "자산과 거래내역은 이동하지 않고 그대로 유지" in (
                switched_semi.json()["notice"]["message"]
            )
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

            snapshot_dates = [date.today() - timedelta(days=1), date.today()]
            with SessionLocal() as session:
                session.add_all(
                    [
                        PortfolioSnapshot(
                            account_id=account_id,
                            snapshot_date=snapshot_dates[0],
                            cash_balance=Decimal("300000.00"),
                            total_purchase_amount=Decimal("700000.00"),
                            total_evaluation_amount=Decimal("700000.00"),
                            total_assets=Decimal("1000000.00"),
                            unrealized_profit=Decimal("0.00"),
                            realized_profit=Decimal("0.00"),
                            return_rate=Decimal("0.00"),
                        ),
                        PortfolioSnapshot(
                            account_id=account_id,
                            snapshot_date=snapshot_dates[1],
                            cash_balance=Decimal("580000.00"),
                            total_purchase_amount=Decimal("420000.00"),
                            total_evaluation_amount=Decimal("440000.00"),
                            total_assets=Decimal("1020000.00"),
                            unrealized_profit=Decimal("20000.00"),
                            realized_profit=Decimal("0.00"),
                            return_rate=Decimal("4.76"),
                        ),
                    ]
                )
                session.commit()

            home = client.get(
                "/api/v1/portfolio/home",
                headers=headers,
                params={
                    "account_id": account_id,
                    "period": "1M",
                    "sort": "return_rate",
                    "order": "desc",
                },
            )
            assert home.status_code == 200, home.text
            home_payload = home.json()
            assert home_payload["account"]["id"] == account_id
            assert home_payload["account"]["operation_mode"] == "AUTO"
            assert home_payload["summary"]["cash_balance"] == "580000.00"
            assert home_payload["summary"]["total_assets"] == "1000000.00"
            assert home_payload["positions"][0]["stock_code"] == stock_code
            assert Decimal(home_payload["positions"][0]["quantity"]) == Decimal("6")
            allocations = {item["type"]: item for item in home_payload["allocations"]}
            assert allocations["STOCK"]["amount"] == "420000.00"
            assert allocations["CASH"]["amount"] == "580000.00"
            assert [item["total_assets"] for item in home_payload["trend"]["items"]] == [
                "1000000.00",
                "1020000.00",
            ]
            assert [item["portfolio_return_rate"] for item in home_payload["trend"]["items"]] == [
                "0.00",
                "2.00",
            ]
            # CI에는 아직 리밸런싱 모델 deployment를 연결하지 않는다. 홈의 나머지 데이터는
            # 정상 제공하고 AI 영역만 명시적인 부분 실패로 내려가야 한다.
            assert home_payload["rebalancing_insight"]["status"] == "UNAVAILABLE"
            assert home_payload["rebalancing_insight"]["model_version"] is None
            assert home_payload["rebalancing_proposals"] == []

            first_transactions = client.get(
                "/api/v1/portfolio/transactions",
                headers=headers,
                params={"account_id": account_id, "limit": 1},
            )
            assert first_transactions.status_code == 200, first_transactions.text
            first_page = first_transactions.json()
            assert first_page["has_more"] is True
            assert first_page["next_cursor"]
            assert first_page["items"][0]["side"] == "SELL"
            assert first_page["items"][0]["transaction_amount"] == "280000.00"

            second_transactions = client.get(
                "/api/v1/portfolio/transactions",
                headers=headers,
                params={
                    "account_id": account_id,
                    "limit": 1,
                    "cursor": first_page["next_cursor"],
                },
            )
            assert second_transactions.status_code == 200, second_transactions.text
            second_page = second_transactions.json()
            assert second_page["has_more"] is False
            assert second_page["next_cursor"] is None
            assert second_page["items"][0]["side"] == "BUY"
            assert second_page["items"][0]["transaction_amount"] == "700000.00"

            invalid_cursor = client.get(
                "/api/v1/portfolio/transactions",
                headers=headers,
                params={"account_id": account_id, "cursor": "not-a-cursor"},
            )
            assert invalid_cursor.status_code == 422, invalid_cursor.text
            assert invalid_cursor.json()["code"] == "INVALID_TRANSACTION_CURSOR"

            intruder_home = client.get(
                "/api/v1/portfolio/home",
                headers=intruder_headers,
                params={"account_id": account_id},
            )
            assert intruder_home.status_code == 404, intruder_home.text
            assert intruder_home.json()["code"] == "ACCOUNT_NOT_FOUND"
            intruder_transactions = client.get(
                "/api/v1/portfolio/transactions",
                headers=intruder_headers,
                params={"account_id": account_id},
            )
            assert intruder_transactions.status_code == 404, intruder_transactions.text
            assert intruder_transactions.json()["code"] == "ACCOUNT_NOT_FOUND"

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
