"""MBGCoordinator-gated Algorithm v2.3 paper-trading endpoint."""

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
from app.trading_engine.engine import IntegratedTradingEngine
from app.trading_engine.engine_fix import IntegratedTradingEngineFix
from app.trading_engine.mbg_coordinator_adapter_fix import DEFAULT_MBG_COORDINATOR_ENDPOINT, MBGCoordinatorAdapterFix

router = APIRouter(tags=["trading-engine-fix"])


@router.post("/trading-engine-fix/runs", response_model=EngineRunResponse)
async def run_engine_fix(payload: EngineRunRequest, user: User = Depends(current_user),
                         session: Session = Depends(get_session)) -> EngineRunResponse:
    credential = DefaultAzureCredential()
    try:
        coordinator = MBGCoordinatorAdapterFix(
            credential,
            endpoint=os.getenv("MBG_COORDINATOR_ENDPOINT", DEFAULT_MBG_COORDINATOR_ENDPOINT),
        )
        market = MarketService()
        base = IntegratedTradingEngine(TradingRepository(session), market, TradingService(session, market))
        return await IntegratedTradingEngineFix(base, coordinator).run(user.id, payload)
    finally:
        await credential.close()
