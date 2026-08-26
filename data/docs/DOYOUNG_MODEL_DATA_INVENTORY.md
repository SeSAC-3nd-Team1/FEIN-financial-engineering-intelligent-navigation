# 정도영 모델 데이터 인벤토리

## 저장 위치와 사용 우선순위

모델 학습 원본의 Source of Truth는 Azure Blob `raw` 컨테이너다. `market_stock_prices`는
화면 조회·백테스트 서빙용 PostgreSQL 테이블이며 대규모 학습 원본으로 사용하지 않는다.

| Source | Blob prefix | 핵심 식별자/날짜 | 형식 | 모델 용도 |
|---|---|---|---|---|
| KRX | `krx/stock_price`, `krx/stock_master`, `krx/market_index` | `BAS_DD`, 6자리 영문·숫자 종목코드 | JSONL.gz | OHLCV·거래대금·시총·시장지수 |
| ECOS | `ecos-bok/ecos/operation=<series>` | `TIME`, `DATA_VALUE` | JSONL.gz | 기준금리·USD/KRW·CPI·국고채 3Y/10Y |
| OpenDART | `opendart/corp_code`, `financial_multi`, `disclosure_market` | `corp_code`, `rcept_no`, `rcept_dt` | ZIP/JSON 원문 | 기업 매핑·재무·공시 이벤트 |
| data.go.kr | 기존 `data-go-kr/...` | dataset별 `basDt` | JSONL.gz | 기존 보조 금융 Raw(이번 수집기는 변경하지 않음) |

## Point-in-Time 주의사항

- OpenDART 재무값은 결산일이 아니라 해당 보고서의 실제 `rcept_dt` 이후에만 Feature로 결합한다.
- 공급자가 요청 사업연도와 다른 값을 반환한 원문은 `financial_multi_anomaly`에 격리하며 canonical 학습 입력에서 제외한다.
- ECOS 월간 CPI는 공표 지연을 반영한 `available_at` 정책을 적용한 Processed/Feature를 사용한다.
- 모든 종목·회사 코드는 숫자로 변환하지 말고 문자열로 읽어 선행 0을 보존한다.
- 결측·휴장일을 0으로 채우지 않는다. 거래일 기준 KRX 시계열에 발표 시점이 지난 거시값만 결합한다.

## 재현과 lineage

Raw 객체는 payload/content hash 경로라 같은 응답의 재실행이 새 객체를 만들지 않는다.
수집 범위와 완료 partition은 `raw/_manifests/model_raw_coverage.json`, 실행 성능은
`data/reports/MODEL_RAW_COLLECTION_SUMMARY.{json,md}`, Blob 전수 감사 결과는
`data/reports/MODEL_RAW_AUDIT.json`에서 확인한다.
