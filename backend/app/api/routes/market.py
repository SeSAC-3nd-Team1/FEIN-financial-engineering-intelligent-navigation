from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends

from app.api.deps import current_user
from app.models import User
from app.schemas.api import PriceResponse
from app.services.market import MarketService

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/stocks/{stock_code}/price", response_model=PriceResponse)
def current_price(stock_code: str, _: User = Depends(current_user)) -> PriceResponse:
    price, as_of, source = MarketService().get_price(stock_code)
    return PriceResponse(stock_code=stock_code, price=price, as_of=as_of, source=source)
