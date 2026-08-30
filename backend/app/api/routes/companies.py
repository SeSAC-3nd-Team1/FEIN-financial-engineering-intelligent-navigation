"""OpenDART 기업·재무·공시 공개 조회 API."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.repositories.opendart import OpenDartRepository
from app.schemas.api import CompanyDisclosureListResponse, CompanyFinancialListResponse, CompanyResponse
from app.services.opendart import OpenDartService

router = APIRouter(prefix="/companies", tags=["companies"])


def get_opendart_service(session: Session = Depends(get_session)) -> OpenDartService:
    return OpenDartService(OpenDartRepository(session))


@router.get("/{stock_code}", response_model=CompanyResponse)
def company(
    stock_code: str = Path(pattern=r"^[0-9A-Z]{6,12}$"),
    service: OpenDartService = Depends(get_opendart_service),
) -> CompanyResponse:
    return service.company(stock_code)


@router.get("/{stock_code}/financials", response_model=CompanyFinancialListResponse)
def financials(
    stock_code: str = Path(pattern=r"^[0-9A-Z]{6,12}$"),
    year: str | None = Query(default=None, pattern=r"^\d{4}$"),
    quarter: Literal["Q1", "Q2", "Q3", "FY"] | None = None,
    service: OpenDartService = Depends(get_opendart_service),
) -> CompanyFinancialListResponse:
    return service.financials(stock_code, year=year, quarter=quarter)


@router.get("/{stock_code}/disclosures", response_model=CompanyDisclosureListResponse)
def disclosures(
    stock_code: str = Path(pattern=r"^[0-9A-Z]{6,12}$"),
    start_date: date | None = None,
    end_date: date | None = None,
    disclosure_type: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    service: OpenDartService = Depends(get_opendart_service),
) -> CompanyDisclosureListResponse:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date must not be after end_date")
    return service.disclosures(
        stock_code,
        start_date=start_date,
        end_date=end_date,
        disclosure_type=disclosure_type,
        limit=limit,
    )
