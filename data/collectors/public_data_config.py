"""Official Financial Services Commission data.go.kr operation catalog."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiOperation:
    dataset: str
    base_url: str
    path: str

    @property
    def name(self) -> str:
        return self.path.removeprefix("/")

    @property
    def url(self) -> str:
        return f"{self.base_url}{self.path}"


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
    selected: list[ApiOperation] = []
    for dataset in datasets:
        candidates = OPERATIONS[dataset]
        if include_all:
            selected.extend(candidates)
        else:
            primary = PRIMARY_OPERATION_NAMES[dataset]
            selected.append(next(item for item in candidates if item.name == primary))
    return selected
