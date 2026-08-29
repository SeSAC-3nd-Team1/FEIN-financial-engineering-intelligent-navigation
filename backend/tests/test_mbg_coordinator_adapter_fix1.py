import asyncio
import json
from decimal import Decimal

import httpx

from app.trading_engine.mbg_coordinator_adapter_fix1 import MBGCoordinatorAdapterFix1


class Credential:
    async def get_token(self, *scopes):
        assert scopes == ("https://ai.azure.com/.default",)
        return type("Token", (), {"token": "test-token"})()


def test_adapter_uses_entra_and_parses_strict_weight_response():
    def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer test-token"
        payload = {
            "request_id": "req-1", "confidence": "0.8", "risk_flags": [], "summary": "유지",
            "proposals": [{
                "stock_code": "005930", "baseline_weight": "0.5",
                "proposed_weight": "0.55", "reason": "검증된 범위 내 상향",
            }],
        }
        return httpx.Response(200, json={"output_text": json.dumps(payload)})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            adapter = MBGCoordinatorAdapterFix1(Credential(), http=http)
            return await adapter.propose(
                request_id="req-1", generated_at="2026-08-28T00:00:00Z",
                baseline_weights={"005930": "0.5"}, market_context={},
            )

    result = asyncio.run(run())
    assert result.proposals[0].proposed_weight == Decimal("0.55")
