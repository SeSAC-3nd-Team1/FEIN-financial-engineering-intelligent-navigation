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

    def upsert_financials(
        self,
        rows: list[dict],
        *,
        preserve_existing_cash_flows: bool = False,
    ) -> int:
        """보고서 요약을 UPSERT하고 필요 시 기존 현금흐름 값을 보존한다.

        ``fnlttMultiAcnt``는 주요 BS/IS 계정 중심이라 현금흐름 3종이 비어 있을 수 있다.
        이 응답을 기존 단일회사 전체재무제표 결과 위에 적재할 때는 해당 컬럼을 UPDATE 대상에서
        제외해 이미 확보한 non-null 현금흐름을 ``None``으로 지우지 않는다.
        """

        update_columns = None
        if preserve_existing_cash_flows:
            update_columns = [
                "stock_code",
                "quarter",
                "revenue",
                "operating_income",
                "net_income",
                "total_assets",
                "total_liabilities",
                "total_equity",
            ]
        return upsert_rows(
            self.session,
            CompanyFinancial,
            rows,
            conflict_columns=["corp_code", "business_year", "report_code", "fs_div"],
            update_columns=update_columns,
        )

    def upsert_disclosures(self, rows: list[dict]) -> int:
        return upsert_rows(self.session, CompanyDisclosure, rows, conflict_columns=["receipt_no"])
