"""실제 PostgreSQL/Redis를 사용하는 회원→계좌→매수→평가→매도 통합 테스트."""

from datetime import UTC, datetime
import json
import os
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
import redis

from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.skipif(os.getenv("RUN_INTEGRATION") != "1", reason="RUN_INTEGRATION=1 required")


def test_virtual_trading_end_to_end() -> None:
    suffix = uuid4().hex[:8]
    phone_suffix = f"{uuid4().int % 100_000_000:08d}"
    user_id = f"u{suffix}"[:16]
    password = "Integration!49"
    stock_code = "005930"
    cache = redis.from_url(settings.redis_url, decode_responses=True)
    cache.setex(
        f"price:{stock_code}",
        300,
        json.dumps({"price": "70000", "as_of": datetime.now(UTC).isoformat()}),
    )

    with TestClient(app) as client:
        signup = client.post("/api/v1/auth/signup", json={
            "user_id": user_id, "password": password, "name": "통합테스트",
            "birthdate": "900101", "phone_number": f"010{phone_suffix}",
            "email": f"{suffix}@example.com", "phone_verified": True, "email_verified": True,
        })
        assert signup.status_code == 201, signup.text
        login = client.post("/api/v1/auth/login", json={"user_id": user_id, "password": password})
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        created = client.post("/api/v1/accounts", headers=headers, json={"account_name": "통합테스트 계좌"})
        assert created.status_code == 201, created.text
        account_id = created.json()["id"]
        assert client.put(f"/api/v1/accounts/{account_id}/strategy", headers=headers, json={"strategy_id": "low"}).status_code == 200

        buy_payload = {
            "account_id": account_id, "stock_code": stock_code, "side": "BUY",
            "order_type": "MARKET", "quantity": 10, "idempotency_key": f"buy-{suffix}",
        }
        buy = client.post("/api/v1/orders", headers=headers, json=buy_payload)
        assert buy.status_code == 201, buy.text
        assert buy.json()["status"] == "FILLED"
        # 같은 요청은 기존 주문을 반환하고 체결/원장을 중복 생성하지 않는다.
        assert client.post("/api/v1/orders", headers=headers, json=buy_payload).json()["id"] == buy.json()["id"]

        portfolio = client.get(f"/api/v1/portfolio?account_id={account_id}", headers=headers)
        assert portfolio.status_code == 200, portfolio.text
        assert portfolio.json()["positions"][0]["quantity"] == 10
        assert portfolio.json()["total_assets"] == "10000000.00"

        sell = client.post("/api/v1/orders", headers=headers, json={
            "account_id": account_id, "stock_code": stock_code, "side": "SELL",
            "order_type": "MARKET", "quantity": 4, "idempotency_key": f"sell-{suffix}",
        })
        assert sell.status_code == 201, sell.text
        after = client.get(f"/api/v1/portfolio?account_id={account_id}", headers=headers).json()
        assert after["positions"][0]["quantity"] == 6
        assert after["cash_balance"] == "9580000.00"
