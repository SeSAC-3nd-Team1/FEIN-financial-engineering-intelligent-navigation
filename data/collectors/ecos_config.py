"""검증된 한국은행 ECOS 거시경제 시계열 registry를 정의한다."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EcosSeries:
    """ECOS 통계표·항목·주기의 검증된 조합과 정규화 정책을 표현한다."""

    name: str
    stat_code: str
    item_code: str
    cycle: str
    unit: str
    description: str


ECOS_SERIES: dict[str, EcosSeries] = {
    "base_rate": EcosSeries(
        "base_rate", "722Y001", "0101000", "D", "연%", "한국은행 기준금리",
    ),
    "usd_krw": EcosSeries(
        "usd_krw", "731Y001", "0000001", "D", "원", "원/미국달러 매매기준율",
    ),
    "cpi": EcosSeries(
        "cpi", "901Y009", "0", "M", "2020=100", "소비자물가지수 총지수",
    ),
    "treasury_3y": EcosSeries(
        "treasury_3y", "817Y002", "010200000", "D", "연%", "국고채 3년 수익률",
    ),
    "treasury_10y": EcosSeries(
        "treasury_10y", "817Y002", "010210000", "D", "연%", "국고채 10년 수익률",
    ),
}


def get_ecos_series(name: str) -> EcosSeries:
    """이름으로 registry 항목을 조회하고 지원하지 않는 이름은 명확히 거부한다."""

    try:
        return ECOS_SERIES[name]
    except KeyError as exc:
        raise ValueError(f"unsupported ECOS series: {name}") from exc
