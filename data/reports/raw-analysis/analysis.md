# Azure Raw 금융 데이터 분석 결과

- 생성 시각: `2026-08-26T05:45:52.497204+00:00`
- 원본: Azure Blob canonical Raw

## 핵심 인사이트

1. 주가 Raw는 `2020-01` ~ `2026-08` 월 범위이며 관측 종목 수는 **4,001개**다.
2. 주가 행이 가장 많은 월은 `2025-07` (**134,524건**)이다.
3. 시장지수 Raw는 **554개** 지수명을 포함한다.
4. 재무 `basDt`는 기준일일 뿐 실제 공시 가능일이 아니므로 가격과 직접 결합해 인과적 모델 입력으로 사용하면 안 된다.

## 데이터 품질 및 해석 한계

- Raw는 분석 중 수정하지 않았으며 빈 값은 0으로 대체하지 않았다.
- 주가 관측 종목 수는 기간별 Universe 변화와 survivorship bias의 영향을 받을 수 있다.
- 재무 `basDt`는 관측 기준일이지 재무정보의 실제 공개일을 의미하지 않는다.
- 분포는 극단값 영향을 받으므로 평균 대신 분위수로 요약했다.

## 집계 요약

| dataset | rows | date/base_date range | 주요 지표 |
|---|---:|---|---|
| stock_price | 7,983,519 | 2020-01 ~ 2026-08 | stocks=4,001 |
| market_index | 936,175 | monthly coverage | indices=554 |
| financial_statement | 2,403,567 | 2000-12-31 ~ 2026-08-24 | fields=1 |

## 시각화

- `stock_price_monthly_rows.svg`: 주가 월별 관측 건수
- `market_index_monthly_rows.svg`: 시장지수 월별 관측 건수
