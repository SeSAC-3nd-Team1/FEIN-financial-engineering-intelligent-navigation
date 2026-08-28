"""MBGCoordinator-gated Algorithm v2.3 paper-trading endpoint (fix1)."""

import os

from azure.identity.aio import DefaultAzureCredential
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_session
from app.models import User
from app.repositories import TradingRepository
from app.services.market import MarketService
from app.services.trading import TradingService
from app.trading_engine.contracts import EngineRunRequest, EngineRunResponse
from app.trading_engine.engine_base_fix1 import IntegratedTradingEngineFix1
from app.trading_engine.engine_fix1 import IntegratedTradingEngineGateFix1
from app.trading_engine.mbg_coordinator_adapter_fix1 import DEFAULT_MBG_COORDINATOR_ENDPOINT, MBGCoordinatorAdapterFix1

router = APIRouter(tags=["trading-engine-fix"])


@router.post("/trading-engine-fix/runs", response_model=EngineRunResponse)
async def run_engine_fix1(payload: EngineRunRequest, user: User = Depends(current_user),
                         session: Session = Depends(get_session)) -> EngineRunResponse:
    credential = DefaultAzureCredential()
    try:
        coordinator = MBGCoordinatorAdapterFix1(
            credential,
            endpoint=os.getenv("MBG_COORDINATOR_ENDPOINT", DEFAULT_MBG_COORDINATOR_ENDPOINT),
        )
        market = MarketService()
        base = IntegratedTradingEngineFix1(TradingRepository(session), market, TradingService(session, market))
        return await IntegratedTradingEngineGateFix1(base, coordinator).run(user.id, payload)
    finally:
        await credential.close()
