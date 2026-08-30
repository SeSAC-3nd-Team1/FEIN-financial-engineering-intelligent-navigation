# Azure Raw 금융 데이터 분석

## 목적

Azure Blob canonical Raw를 수정하지 않고, 월별 coverage·건수·분포·품질을 분석해 모델링과 수집 운영에 사용할 인사이트를 도출한다. 분석 스크립트는 한 Blob씩 읽으므로 전체 Raw를 메모리에 적재하지 않는다.

## 실행

프로젝트 루트에서 실행한다.

```bash

docker compose --profile data run --rm --no-deps data \
  python -m scripts.analyze_raw_data \
  --output-dir reports/raw-analysis
```

특정 dataset만 분석할 수도 있다.

```bash

docker compose --profile data run --rm --no-deps data \
  python -m scripts.analyze_raw_data \
  --dataset stock_price \
  --dataset market_index
```

Azure 인증은 프로젝트의 `BlobStorage.from_env()` 정책을 따르며, Secret은 출력하거나 결과에 저장하지 않는다.

## 산출물

- `reports/raw-analysis/analysis.json`: 기계 판독용 집계 결과
- `reports/raw-analysis/analysis.md`: 인사이트 및 한계 요약
- `reports/raw-analysis/stock_price_monthly_rows.svg`: 주가 월별 관측 건수
- `reports/raw-analysis/market_index_monthly_rows.svg`: 시장지수 월별 관측 건수

이 산출물은 실제 Raw 파일이나 Parquet을 포함하지 않는다. 분석 결과 파일과 SVG는 로컬에서 확인하고, 대용량 또는 실행 시점이 포함된 결과를 GitHub에 커밋할 때는 팀과 먼저 공유한다.

## 분석 해석 기준

- `stock_price`: `basDt`, 종목코드, 종가, 거래량을 사용해 기간·종목 Universe·월별 관측량·분포를 집계한다.
- `market_index`: 지수명별 관측량과 월별 coverage를 집계한다.
- `financial_statement`: `baseDate` 범위와 주요 필드 존재율을 집계한다.
- 빈 값은 0으로 대체하지 않는다.
- 재무 `baseDate`는 실제 공개일이 아니므로 가격과의 인과적 JOIN 근거로 사용하지 않는다.
- 기간별 종목 수 변화는 상장·편출입·수집 coverage 변화 및 survivorship bias와 함께 해석한다.

## 현재 분석의 한계

- Raw 원문은 API operation별 schema가 다르므로 모든 dataset을 하나의 테이블로 합치지 않는다.
- 현재 시각화는 월별 coverage 중심이다. 모델 검증에 필요한 수익률·변동성·섹터별 분석은 Processed/Features에서 별도 수행한다.
- SVG 시각화는 외부 JavaScript 의존성이 없는 재현 가능한 기본 결과다.
