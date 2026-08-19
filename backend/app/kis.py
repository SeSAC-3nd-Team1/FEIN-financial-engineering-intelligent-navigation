from __future__ import annotations

import asyncio
import json
import math
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, AsyncIterator, Literal

import httpx
import websockets
from fastapi import HTTPException
from pydantic import BaseModel, Field


class OrderRequest(BaseModel):
    symbol: str = Field(pattern=r"^\d{6}$")
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0)
    order_type: Literal["market", "limit"] = "market"
    price: int | None = Field(default=None, ge=0)


@dataclass(frozen=True)
class KISSettings:
    app_key: str
    app_secret: str
    account_no: str
    account_product_code: str
    mode: Literal["paper", "real"]
    enable_live_trading: bool
    use_mock_fallback: bool

    @classmethod
    def from_env(cls) -> "KISSettings":
        mode = os.getenv("KIS_MODE", "paper").lower()
        if mode not in {"paper", "real"}:
            mode = "paper"
        return cls(
            app_key=os.getenv("KIS_APP_KEY", "").strip(),
            app_secret=os.getenv("KIS_APP_SECRET", "").strip(),
            account_no=os.getenv("KIS_ACCOUNT_NO", "").strip(),
            account_product_code=os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01").strip() or "01",
            mode=mode,  # type: ignore[arg-type]
            enable_live_trading=os.getenv("KIS_ENABLE_LIVE_TRADING", "false").lower() == "true",
            use_mock_fallback=os.getenv("KIS_USE_MOCK_FALLBACK", "true").lower() == "true",
        )

    @property
    def base_url(self) -> str:
        return (
            "https://openapivts.koreainvestment.com:29443"
            if self.mode == "paper"
            else "https://openapi.koreainvestment.com:9443"
        )

    @property
    def websocket_url(self) -> str:
        return (
            "ws://ops.koreainvestment.com:31000/tryitout"
            if self.mode == "paper"
            else "ws://ops.koreainvestment.com:21000/tryitout"
        )

    @property
    def configured(self) -> bool:
        return bool(self.app_key and self.app_secret)

    @property
    def account_configured(self) -> bool:
        return bool(self.configured and self.account_no and self.account_product_code)


class KISClient:
    def __init__(self) -> None:
        self.settings = KISSettings.from_env()
        self._token: str | None = None
        self._token_expires_at = datetime.min
        self._token_lock = asyncio.Lock()
        self._mock_price = 72000.0
        self._mock_holdings: dict[str, dict[str, Any]] = {
            "005930": {"name": "삼성전자", "quantity": 10, "avg_price": 69800.0},
            "000660": {"name": "SK하이닉스", "quantity": 3, "avg_price": 184500.0},
        }

    @property
    def mock_mode(self) -> bool:
        return not self.settings.configured and self.settings.use_mock_fallback

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.settings.configured,
            "accountConfigured": self.settings.account_configured,
            "mode": self.settings.mode,
            "source": "mock" if self.mock_mode else "kis",
            "liveTradingEnabled": self.settings.enable_live_trading,
            "message": (
                "KIS 키가 없어 Mock 데이터로 실행 중입니다."
                if self.mock_mode
                else f"한국투자증권 {self.settings.mode} 환경을 사용합니다."
            ),
        }

    async def _access_token(self) -> str:
        if self._token and datetime.now() < self._token_expires_at:
            return self._token
        if not self.settings.configured:
            raise HTTPException(503, "KIS_APP_KEY / KIS_APP_SECRET이 설정되지 않았습니다.")
        async with self._token_lock:
            if self._token and datetime.now() < self._token_expires_at:
                return self._token
            payload = {
                "grant_type": "client_credentials",
                "appkey": self.settings.app_key,
                "appsecret": self.settings.app_secret,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{self.settings.base_url}/oauth2/tokenP",
                    json=payload,
                    headers={"content-type": "application/json"},
                )
            response.raise_for_status()
            body = response.json()
            self._token = body["access_token"]
            expires_in = int(body.get("expires_in", 86400))
            self._token_expires_at = datetime.now() + timedelta(seconds=max(60, expires_in - 300))
            return self._token

    async def _headers(self, tr_id: str) -> dict[str, str]:
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {await self._access_token()}",
            "appkey": self.settings.app_key,
            "appsecret": self.settings.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }

    async def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{self.settings.base_url}{path}",
                params=params,
                headers=await self._headers(tr_id),
            )
        response.raise_for_status()
        body = response.json()
        if body.get("rt_cd") not in {None, "0"}:
            raise HTTPException(502, body.get("msg1", "KIS API 요청 실패"))
        return body

    async def _post(self, path: str, tr_id: str, payload: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{self.settings.base_url}{path}",
                json=payload,
                headers=await self._headers(tr_id),
            )
        response.raise_for_status()
        body = response.json()
        if body.get("rt_cd") not in {None, "0"}:
            raise HTTPException(502, body.get("msg1", "KIS API 요청 실패"))
        return body

    def _next_mock_price(self) -> int:
        self._mock_price = max(1000, self._mock_price * (1 + random.uniform(-0.0012, 0.0012)))
        return int(round(self._mock_price / 100) * 100)

    async def price(self, symbol: str) -> dict[str, Any]:
        if self.mock_mode:
            price = self._next_mock_price()
            return {"symbol": symbol, "price": price, "change": price - 72000, "changeRate": (price / 72000 - 1) * 100, "source": "mock"}
        body = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol},
        )
        output = body.get("output", {})
        return {
            "symbol": symbol,
            "price": int(float(output.get("stck_prpr", 0) or 0)),
            "change": int(float(output.get("prdy_vrss", 0) or 0)),
            "changeRate": float(output.get("prdy_ctrt", 0) or 0),
            "source": "kis",
        }

    async def chart(self, symbol: str) -> list[dict[str, Any]]:
        if self.mock_mode:
            now = datetime.now().replace(second=0, microsecond=0)
            price = 71600.0
            rows: list[dict[str, Any]] = []
            for index in range(60):
                point_time = now - timedelta(minutes=59 - index)
                open_price = price
                close = open_price * (1 + math.sin(index / 8) * 0.0005 + random.uniform(-0.001, 0.001))
                high = max(open_price, close) * (1 + random.uniform(0, 0.0007))
                low = min(open_price, close) * (1 - random.uniform(0, 0.0007))
                price = close
                rows.append({
                    "time": point_time.strftime("%H%M%S"),
                    "open": int(open_price), "high": int(high), "low": int(low), "close": int(close),
                    "volume": random.randint(1000, 12000),
                })
            self._mock_price = rows[-1]["close"]
            return rows
        body = await self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "FHKST03010200",
            {
                "FID_ETC_CLS_CODE": "",
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_HOUR_1": datetime.now().strftime("%H%M%S"),
                "FID_PW_DATA_INCU_YN": "Y",
            },
        )
        result = []
        for row in reversed(body.get("output2", []) or []):
            try:
                result.append({
                    "time": row.get("stck_cntg_hour", ""),
                    "open": int(float(row.get("stck_oprc", 0) or 0)),
                    "high": int(float(row.get("stck_hgpr", 0) or 0)),
                    "low": int(float(row.get("stck_lwpr", 0) or 0)),
                    "close": int(float(row.get("stck_prpr", 0) or 0)),
                    "volume": int(float(row.get("cntg_vol", 0) or 0)),
                })
            except (TypeError, ValueError):
                continue
        return result[-120:]

    async def account(self) -> dict[str, Any]:
        if self.mock_mode:
            holdings = []
            total_eval = 0
            total_purchase = 0
            for symbol, item in self._mock_holdings.items():
                price = self._next_mock_price() if symbol == "005930" else int(item["avg_price"] * 1.018)
                quantity = int(item["quantity"])
                eval_amount = price * quantity
                purchase = int(item["avg_price"] * quantity)
                pnl = eval_amount - purchase
                holdings.append({
                    "symbol": symbol, "name": item["name"], "quantity": quantity,
                    "availableQuantity": quantity, "avgPrice": item["avg_price"], "currentPrice": price,
                    "evaluationAmount": eval_amount, "profitLoss": pnl,
                    "profitLossRate": (pnl / purchase * 100) if purchase else 0,
                })
                total_eval += eval_amount
                total_purchase += purchase
            cash = 5_000_000
            return {
                "summary": {"cash": cash, "stockEvaluation": total_eval, "totalEvaluation": cash + total_eval,
                            "profitLoss": total_eval - total_purchase,
                            "profitLossRate": ((total_eval - total_purchase) / total_purchase * 100) if total_purchase else 0},
                "holdings": holdings, "source": "mock",
            }
        if not self.settings.account_configured:
            raise HTTPException(503, "KIS_ACCOUNT_NO / KIS_ACCOUNT_PRODUCT_CODE가 필요합니다.")
        tr_id = "VTTC8434R" if self.settings.mode == "paper" else "TTTC8434R"
        body = await self._get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            {
                "CANO": self.settings.account_no,
                "ACNT_PRDT_CD": self.settings.account_product_code,
                "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "02", "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
            },
        )
        holdings = []
        for row in body.get("output1", []) or []:
            quantity = int(float(row.get("hldg_qty", 0) or 0))
            if quantity <= 0:
                continue
            holdings.append({
                "symbol": row.get("pdno", ""), "name": row.get("prdt_name", ""), "quantity": quantity,
                "availableQuantity": int(float(row.get("ord_psbl_qty", 0) or 0)),
                "avgPrice": float(row.get("pchs_avg_pric", 0) or 0), "currentPrice": int(float(row.get("prpr", 0) or 0)),
                "evaluationAmount": int(float(row.get("evlu_amt", 0) or 0)),
                "profitLoss": int(float(row.get("evlu_pfls_amt", 0) or 0)),
                "profitLossRate": float(row.get("evlu_pfls_rt", 0) or 0),
            })
        summary_row = (body.get("output2", []) or [{}])[0]
        return {
            "summary": {
                "cash": int(float(summary_row.get("dnca_tot_amt", 0) or 0)),
                "stockEvaluation": int(float(summary_row.get("scts_evlu_amt", 0) or 0)),
                "totalEvaluation": int(float(summary_row.get("tot_evlu_amt", 0) or 0)),
                "profitLoss": int(float(summary_row.get("evlu_pfls_smtl_amt", 0) or 0)),
                "profitLossRate": float(summary_row.get("asst_icdc_erng_rt", 0) or 0),
            },
            "holdings": holdings, "source": "kis",
        }

    async def order(self, order: OrderRequest) -> dict[str, Any]:
        if self.mock_mode:
            item = self._mock_holdings.setdefault(order.symbol, {"name": order.symbol, "quantity": 0, "avg_price": float(order.price or self._mock_price)})
            fill_price = float(order.price or self._mock_price)
            if order.side == "buy":
                old_qty = int(item["quantity"])
                new_qty = old_qty + order.quantity
                item["avg_price"] = ((item["avg_price"] * old_qty) + fill_price * order.quantity) / new_qty
                item["quantity"] = new_qty
            else:
                item["quantity"] = max(0, int(item["quantity"]) - order.quantity)
            return {"accepted": True, "orderNumber": f"MOCK-{datetime.now():%H%M%S}", "message": "Mock 주문이 처리되었습니다.", "source": "mock"}
        if not self.settings.account_configured:
            raise HTTPException(503, "KIS 계좌 정보가 설정되지 않았습니다.")
        if self.settings.mode == "real" and not self.settings.enable_live_trading:
            raise HTTPException(403, "실전 주문은 KIS_ENABLE_LIVE_TRADING=true 설정 전까지 차단됩니다.")
        if order.order_type == "limit" and not order.price:
            raise HTTPException(422, "지정가 주문에는 가격이 필요합니다.")
        if self.settings.mode == "paper":
            tr_id = "VTTC0012U" if order.side == "buy" else "VTTC0011U"
        else:
            tr_id = "TTTC0012U" if order.side == "buy" else "TTTC0011U"
        payload = {
            "CANO": self.settings.account_no,
            "ACNT_PRDT_CD": self.settings.account_product_code,
            "PDNO": order.symbol,
            "ORD_DVSN": "01" if order.order_type == "market" else "00",
            "ORD_QTY": str(order.quantity),
            "ORD_UNPR": "0" if order.order_type == "market" else str(order.price or 0),
            "EXCG_ID_DVSN_CD": "KRX",
            "SLL_TYPE": "01" if order.side == "sell" else "",
            "CNDT_PRIC": "",
        }
        body = await self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, payload)
        output = body.get("output", {})
        return {"accepted": True, "orderNumber": output.get("ODNO", ""), "message": body.get("msg1", "주문 접수"), "source": "kis"}

    async def _approval_key(self) -> str:
        payload = {"grant_type": "client_credentials", "appkey": self.settings.app_key, "secretkey": self.settings.app_secret}
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{self.settings.base_url}/oauth2/Approval", json=payload)
        response.raise_for_status()
        return response.json()["approval_key"]

    async def stream(self, symbol: str) -> AsyncIterator[dict[str, Any]]:
        if self.mock_mode:
            while True:
                await asyncio.sleep(1)
                price = self._next_mock_price()
                yield {"symbol": symbol, "time": datetime.now().strftime("%H%M%S"), "price": price, "change": price - 72000,
                       "changeRate": (price / 72000 - 1) * 100, "volume": random.randint(1, 800), "source": "mock"}
        approval_key = await self._approval_key()
        subscribe = {
            "header": {"approval_key": approval_key, "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
            "body": {"input": {"tr_id": "H0STCNT0", "tr_key": symbol}},
        }
        async with websockets.connect(self.settings.websocket_url, ping_interval=20, ping_timeout=20) as ws:
            await ws.send(json.dumps(subscribe))
            async for raw in ws:
                if not raw:
                    continue
                if raw[0] in {"0", "1"}:
                    parts = raw.split("|", 3)
                    if len(parts) < 4 or parts[1] != "H0STCNT0":
                        continue
                    values = parts[3].split("^")
                    if len(values) < 14:
                        continue
                    yield {
                        "symbol": values[0], "time": values[1], "price": int(float(values[2] or 0)),
                        "change": int(float(values[4] or 0)), "changeRate": float(values[5] or 0),
                        "ask": int(float(values[10] or 0)), "bid": int(float(values[11] or 0)),
                        "volume": int(float(values[12] or 0)), "accumulatedVolume": int(float(values[13] or 0)), "source": "kis",
                    }
                else:
                    try:
                        message = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if message.get("header", {}).get("tr_id") == "PINGPONG":
                        await ws.pong(raw.encode())


kis_client = KISClient()
