"""OpenDART 정제 행의 transaction 단위 UPSERT를 제공한다."""

from sqlalchemy.orm import Session

from db.models.opendart import Company, CompanyDisclosure, CompanyFinancial, CompanyFinancialAccount
from loaders.upsert import upsert_rows


class OpenDartRepository:
    """OpenDART 테이블별 충돌키를 한 곳에서 관리한다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_companies(self, rows: list[dict]) -> int:
        return upsert_rows(self.session, Company, rows, conflict_columns=["corp_code"])

    def upsert_financial_accounts(self, rows: list[dict]) -> int:
        return upsert_rows(
            self.session,
            CompanyFinancialAccount,
            rows,
            conflict_columns=["corp_code", "business_year", "report_code", "fs_div", "sj_div", "account_id"],
        )

    def upsert_financials(self, rows: list[dict]) -> int:
        return upsert_rows(
            self.session,
            CompanyFinancial,
            rows,
            conflict_columns=["corp_code", "business_year", "report_code", "fs_div"],
        )

    def upsert_disclosures(self, rows: list[dict]) -> int:
        return upsert_rows(self.session, CompanyDisclosure, rows, conflict_columns=["receipt_no"])
