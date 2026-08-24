"""OpenDART 공개 조회 endpoint 계약을 검증한다."""

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.api.routes.companies import get_opendart_service
from app.core.errors import NotFoundError
from app.main import app
from app.schemas.api import CompanyDisclosureListResponse, CompanyDisclosureResponse, CompanyFinancialListResponse, CompanyFinancialResponse, CompanyResponse


class FakeOpenDartService:
    def __init__(self, missing: bool = False) -> None:
        self.missing = missing
        self.calls = []

    def company(self, stock_code: str) -> CompanyResponse:
        if self.missing:
            raise NotFoundError("COMPANY_NOT_FOUND", "OpenDART 기업정보를 찾을 수 없습니다.")
        return CompanyResponse(corp_code="00126380", stock_code=stock_code, corp_name="삼성전자", corp_name_eng="Samsung Electronics", stock_name="삼성전자", market="Y", ceo_name="대표", jurir_no=None, bizr_no=None, address=None, homepage_url=None, ir_url=None, phone_number=None, industry_code=None, established_date=None, accounting_month="12")

    def financials(self, stock_code: str, *, year, quarter) -> CompanyFinancialListResponse:
        self.calls.append(("financials", stock_code, year, quarter))
        return CompanyFinancialListResponse(stock_code=stock_code, items=[CompanyFinancialResponse(
            business_year="2025", report_code="11011", quarter="FY", fs_div="CFS", revenue=Decimal("100"), operating_income=None, net_income=None, total_assets=None, total_liabilities=None, total_equity=None, operating_cash_flow=None, investing_cash_flow=None, financing_cash_flow=None,
        )])

    def disclosures(self, stock_code: str, *, start_date, end_date, disclosure_type, limit) -> CompanyDisclosureListResponse:
        self.calls.append(("disclosures", stock_code, start_date, end_date, disclosure_type, limit))
        return CompanyDisclosureListResponse(stock_code=stock_code, items=[CompanyDisclosureResponse(
            receipt_no="202608240001", corp_code="00126380", stock_code=stock_code, corp_name="삼성전자", report_name="사업보고서", filer_name="삼성전자", receipt_date=date(2026, 8, 24), remarks=None,
        )])


def test_company_endpoint_returns_opendart_source() -> None:
    app.dependency_overrides[get_opendart_service] = lambda: FakeOpenDartService()
    try:
        response = TestClient(app).get("/api/v1/companies/005930")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["stock_code"] == "005930"
    assert response.json()["source"] == "OpenDART"


def test_financial_and_disclosure_query_parameters() -> None:
    service = FakeOpenDartService()
    app.dependency_overrides[get_opendart_service] = lambda: service
    try:
        client = TestClient(app)
        assert client.get("/api/v1/companies/005930/financials?year=2025&quarter=FY").status_code == 200
        assert client.get("/api/v1/companies/005930/disclosures?start_date=2026-08-01&end_date=2026-08-24&disclosure_type=사업&limit=10").status_code == 200
    finally:
        app.dependency_overrides.clear()
    assert service.calls[0] == ("financials", "005930", "2025", "FY")
    assert service.calls[1] == ("disclosures", "005930", date(2026, 8, 1), date(2026, 8, 24), "사업", 10)


def test_company_endpoint_uses_standard_not_found_contract() -> None:
    app.dependency_overrides[get_opendart_service] = lambda: FakeOpenDartService(missing=True)
    try:
        response = TestClient(app).get("/api/v1/companies/999999")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 404
    assert response.json()["code"] == "COMPANY_NOT_FOUND"
