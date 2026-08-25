"""승인된 KRX OPEN API 7개 endpoint의 계약을 정의한다."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KrxOperation:
    """KRX endpoint와 canonical dataset/시장 구분을 묶는다."""

    name: str
    dataset: str
    market: str
    path: str


OPERATIONS = (
    KrxOperation("stk_bydd_trd", "stock_price", "KOSPI", "sto/stk_bydd_trd"),
    KrxOperation("ksq_bydd_trd", "stock_price", "KOSDAQ", "sto/ksq_bydd_trd"),
    KrxOperation("stk_isu_base_info", "stock_master", "KOSPI", "sto/stk_isu_base_info"),
    KrxOperation("ksq_isu_base_info", "stock_master", "KOSDAQ", "sto/ksq_isu_base_info"),
    KrxOperation("kospi_dd_trd", "market_index", "KOSPI", "idx/kospi_dd_trd"),
    KrxOperation("kosdaq_dd_trd", "market_index", "KOSDAQ", "idx/kosdaq_dd_trd"),
    KrxOperation("krx_dd_trd", "market_index", "KRX", "idx/krx_dd_trd"),
)

