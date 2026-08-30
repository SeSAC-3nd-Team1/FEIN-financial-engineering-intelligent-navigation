"""OpenDART 정제 데이터의 공개 조회 규칙을 제공한다."""

from datetime import date

from app.core.errors import NotFoundError
from app.repositories.opendart import OpenDartRepository
from app.schemas.api import CompanyDisclosureListResponse, CompanyFinancialListResponse, CompanyResponse


class OpenDartService:
    def __init__(self, repository: OpenDartRepository) -> None:
        self.repository = repository

    def company(self, stock_code: str) -> CompanyResponse:
        company = self.repository.company_by_stock_code(stock_code)
        if company is None:
            raise NotFoundError("COMPANY_NOT_FOUND", "OpenDART 기업정보를 찾을 수 없습니다.")
        return CompanyResponse.model_validate(company)

    def financials(self, stock_code: str, *, year: str | None, quarter: str | None) -> CompanyFinancialListResponse:
        self.company(stock_code)
        return CompanyFinancialListResponse(
            stock_code=stock_code,
            items=self.repository.financials(stock_code, year=year, quarter=quarter),
        )

    def disclosures(
        self,
        stock_code: str,
        *,
        start_date: date | None,
        end_date: date | None,
        disclosure_type: str | None,
        limit: int,
    ) -> CompanyDisclosureListResponse:
        self.company(stock_code)
        return CompanyDisclosureListResponse(
            stock_code=stock_code,
            items=self.repository.disclosures(
                stock_code,
                start_date=start_date,
                end_date=end_date,
                disclosure_type=disclosure_type,
                limit=limit,
            ),
        )
