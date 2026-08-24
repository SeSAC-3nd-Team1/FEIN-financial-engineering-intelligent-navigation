"""OpenDART 정제 행의 transaction 단위 UPSERT를 제공한다."""

from sqlalchemy.orm import Session

from db.models.opendart import Company, CompanyDisclosure, CompanyFinancial, CompanyFinancialAccount
from loaders.upsert import upsert_rows


CASH_FLOW_COLUMNS = (
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
)


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
        """보고서 요약을 UPSERT하고 sparse 응답에서는 기존 현금흐름 값을 보존한다.

        ``fnlttMultiAcnt``는 주요 BS/IS 계정 중심이라 현금흐름 3종이 모두 비어 들어온다.
        배치 전체에서 현금흐름이 하나도 관측되지 않으면 sparse source로 판단해 해당 컬럼을
        UPDATE 대상에서 제외한다. 따라서 기존 단일회사 전체재무제표에서 확보한 non-null
        현금흐름을 ``None``으로 지우지 않는다.
        """

        sparse_cash_flow_batch = bool(rows) and all(
            row.get(column) is None
            for row in rows
            for column in CASH_FLOW_COLUMNS
        )
        preserve_cash_flows = preserve_existing_cash_flows or sparse_cash_flow_batch
        conflict_columns = ["corp_code", "business_year", "report_code", "fs_div"]

        if not preserve_cash_flows:
            # 기존 단일회사 전체재무제표 경로는 모든 제공 지표를 그대로 갱신한다.
            return upsert_rows(
                self.session,
                CompanyFinancial,
                rows,
                conflict_columns=conflict_columns,
            )

        return upsert_rows(
            self.session,
            CompanyFinancial,
            rows,
            conflict_columns=conflict_columns,
            update_columns=[
                "stock_code",
                "quarter",
                "revenue",
                "operating_income",
                "net_income",
                "total_assets",
                "total_liabilities",
                "total_equity",
            ],
        )

    def upsert_disclosures(self, rows: list[dict]) -> int:
        return upsert_rows(self.session, CompanyDisclosure, rows, conflict_columns=["receipt_no"])
