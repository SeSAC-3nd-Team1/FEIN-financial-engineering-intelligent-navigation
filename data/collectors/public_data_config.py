"""금융위원회 data.go.kr API의 dataset/operation catalog를 정의한다."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiOperation:
    """하나의 공공데이터 API operation과 소속 dataset 정보를 표현한다."""

    dataset: str
    base_url: str
    path: str

    @property
    def name(self) -> str:
        """URL path에서 operation 이름만 반환한다."""

        return self.path.removeprefix("/")

    @property
    def url(self) -> str:
        """실제 호출할 전체 endpoint URL을 만든다."""

        return f"{self.base_url}{self.path}"


# dataset 이름은 Blob 경로와 테스트에서 공통 식별자로 사용하므로 임의로 변경하지 않는다.
BASE_URLS = {
    "stock_issuance": "https://apis.data.go.kr/1160100/GetStocIssuInfoService_V3",
    "stock_price": "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService",
    "stock_dividend": "https://apis.data.go.kr/1160100/GetStocDiviInfoService_V2",
    "security_product": "https://apis.data.go.kr/1160100/service/GetSecuritiesProductInfoService",
    "market_index": "https://apis.data.go.kr/1160100/service/GetMarketIndexInfoService",
    "financial_statement": "https://apis.data.go.kr/1160100/service/GetFinaStatInfoService_V2",
    "stock_master": "https://apis.data.go.kr/1160100/service/GetKrxListedInfoService",
    "disclosure": "https://apis.data.go.kr/1160100/service/GetDiscInfoService_V2",
}


# 공식 서비스가 제공하는 8개 dataset의 전체 operation 목록이다.
# path는 외부 API 계약이므로 Python식 이름으로 바꾸지 않고 원문 그대로 유지한다.
OPERATION_PATHS = {
    "stock_issuance": [
        "/getStocIssuInfo_V3",
        "/getLockUpRetuInfo_V3",
        "/getItemBasiInfo_V3",
        "/getStocIssuStat_V3",
    ],
    "stock_price": [
        "/getStockPriceInfo",
        "/getPreemptiveRightCertificatePriceInfo",
        "/getSecuritiesPriceInfo",
        "/getPreemptiveRightSecuritiesPriceInfo",
    ],
    "stock_dividend": ["/getDiviInfo_V2"],
    "security_product": [
        "/getETFPriceInfo",
        "/getETNPriceInfo",
        "/getELWPriceInfo",
    ],
    "market_index": [
        "/getStockMarketIndex",
        "/getBondMarketIndex",
        "/getDerivationProductMarketIndex",
    ],
    "financial_statement": [
        "/getIncoStat_V2",
        "/getBs_V2",
        "/getSummFinaStat_V2",
    ],
    "stock_master": ["/getItemInfo"],
    "disclosure": [
        "/getDiviDiscInfo_V2",
        "/getCapiIncrWithConsDiscInfo_V2",
        "/getBonuIssuDiscInfo_V2",
        "/getCapiIncrWithConsBonuIssuDiscInfo_V2",
        "/getGeneMeetStocPublNotiDiscInfo_V2",
        "/getAsseTranPutBackOptiDiscInfo_V2",
        "/getDishDiscInfo_V2",
        "/getBusiSuspDiscInfo_V2",
        "/getReviProcDiscInfo_V2",
        "/getDissReasDiscInfo_V2",
        "/getReduCapiDiscInfo_V2",
        "/getProcByCredBankDiscInfo_V2",
        "/getLitiEtcDiscInfo_V2",
        "/getOffsSecuMarkListDiscInfo_V2",
        "/getOffsSecuMarkDeliDiscInfo_V2",
        "/getCbRighIssuDiscInfo_V2",
        "/getBwRighIssuDiscInfo_V2",
        "/getEbRighIssuDiscInfo_V2",
        "/getAmorCoCoBondDisclInfo_V2",
        "/getTreaStocRepuDiscInfo_V2",
        "/getTreaStocSellDiscInfo_V2",
        "/getBusiInhetDiscInfo_V2",
        "/getBusiConvDiscInfo_V2",
        "/getStocSubsCertInheDiscInfo_V2",
        "/getStocSubsCertConvDiscInfo_V2",
        "/getDebeRighInheDiscInfo_V2",
        "/getDebeRighConvDiscInfo_V2",
        "/getMnaDiscInfo_V2",
        "/getSpilUpDiscInfo_V2",
        "/getDiviCombDiscInfo_V2",
        "/getStocExchTranDiscInfo_V2",
        "/getStocOptiRepo_V2",
        "/getOutsDireHumaResoAffaRepo_V2",
    ],
}


OPERATIONS = {
    dataset: [
        ApiOperation(dataset=dataset, base_url=BASE_URLS[dataset], path=path)
        for path in paths
    ]
    for dataset, paths in OPERATION_PATHS.items()
}

# 기본 수집은 호출량을 제한하기 위해 dataset별 대표 operation 하나만 사용한다.
# 전체 endpoint가 필요할 때만 --all-operations로 명시적으로 확장한다.
PRIMARY_OPERATION_NAMES = {
    "stock_issuance": "getItemBasiInfo_V3",
    "stock_price": "getStockPriceInfo",
    "stock_dividend": "getDiviInfo_V2",
    "security_product": "getETFPriceInfo",
    "market_index": "getStockMarketIndex",
    "financial_statement": "getSummFinaStat_V2",
    "stock_master": "getItemInfo",
    "disclosure": "getDiviDiscInfo_V2",
}


def select_operations(
    datasets: list[str], *, include_all: bool = False
) -> list[ApiOperation]:
    """선택한 dataset별 대표 operation 또는 전체 operation 목록을 반환한다."""

    selected: list[ApiOperation] = []
    for dataset in datasets:
        candidates = OPERATIONS[dataset]
        if include_all:
            selected.extend(candidates)
        else:
            primary = PRIMARY_OPERATION_NAMES[dataset]
            selected.append(next(item for item in candidates if item.name == primary))
    return selected
