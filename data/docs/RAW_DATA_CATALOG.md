# Raw 데이터 카탈로그와 5년 수집 범위

## 목적과 범위

FE!N의 전략 비교, 백테스트, 재무 안정성 설명에 필요한 원본 데이터 목록과 초기 수집
범위를 정리한다. 이 단계는 API 응답을 수정하지 않고 Azure Blob Storage의 canonical
Raw에 저장하는 데까지만 포함한다. 정규화, 결측 처리, Parquet 변환, Feature/Factor 계산은
실행하지 않는다.

최소 이력 기준은 핵심 일별 시계열인 주식 가격과 주식시장 지수가 첫 월과 마지막 월
사이에 **60개월 이상** 떨어져 있는지로 판정한다. 월 범위 감사는 빠른 운영 점검이며 개별
거래일의 완전성을 보증하지 않는다.

## 수집 대상

### P0: 현재 수집·적재 가능

아래 8개 dataset, 52개 operation은 금융위원회 공공데이터 API → canonical Raw Blob
경로가 구현되어 있다. 관측 범위와 건수는 2026-08-16 Azure Raw 전수 프로파일 결과다.
이후 2026-08-19 실행에서 `stock_price`, `market_index`, `stock_master`의 2026-08-18
원본 5,798건을 증분 적재했으며, 아래 전수 프로파일 건수에는 이 증분이 포함되지 않는다.

| 우선 | Dataset | 핵심 내용 | 모델/서비스 용도 | 관측 `basDt` 범위 | 건수 | 주기 |
|---|---|---|---|---|---:|---|
| P0 | `stock_price` | 종목별 OHLCV, 거래대금, 상장주식수, 시가총액 | Momentum, Low Volatility, 유동성, 백테스트 | 2021-08-17 ~ 2026-08-18 | 3,505,298 + 증분 2,872 | 일 |
| P0 | `market_index` | 주식·채권·파생 지수 | Benchmark, 시장 추세·변동성 | 2021-08-17 ~ 2026-08-18 | 467,358 + 증분 168 | 일 |
| P0 | `stock_master` | 종목코드, ISIN, 법인번호, 상장 기준정보 | 종목 매핑·표시, universe 근거 | 2021-08-17 ~ 2026-08-18 | 3,211,333 + 증분 2,758 | 일/snapshot 혼재 |
| P0 | `financial_statement` | 재무상태표, 손익계산서, 요약재무 | Value, Quality, 재무 안정성의 원천 | 2000-12-31 ~ 2026-08-13 | 1,239,611 | 분기·연 |
| P1 | `disclosure` | 배당·증자·M&A 등 33개 공시 유형 | 이벤트 설명·연구 | 2009-07-30 ~ 2026-08-04 | 80,045 | 수시 |
| P1 | `stock_issuance` | 종목기본, 발행, 보호예수, 발행통계 | corporate action·기준정보 보강 | 2021-08-16 ~ 2026-08-13 | 10,135,621 | 일/snapshot 혼재 |
| P1 | `stock_dividend` | 배당 기준일·지급일·배당 정보 | 배당 이벤트·수익률 보강 | 2026-08-13 snapshot | 71,681 | snapshot |
| P2 | `security_product` | ETF, ETN, ELW 시세 | 확장 universe·시장 참고 | 2021-08-17 ~ 2026-08-13 | 5,362,704 | 일 |

공식 출처:

- [금융위원회 주식시세정보](https://www.data.go.kr/data/15094808/openapi.do): 주식과 관련 증권의 시가·종가·고가·저가·거래량을 제공하며, 공식 안내상 영업일 다음 날 갱신된다.
- 나머지 금융위 operation의 실제 endpoint 목록은 `collectors/public_data_config.py`가 단일 코드 계약이다.

### P1: 별도 수집기로 후속 추가

| 데이터 | 공식 출처 | 최소 범위 | 필요한 이유 | 현재 상태 |
|---|---|---:|---|---|
| KOSPI/KOSDAQ 일별 매매·valuation | [KRX OPEN API](https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC) | 5년 | PER/PBR/배당수익률, 거래소 원천 대조 | `KRX_AUTH_KEY` 발급 후 별도 Issue |
| 과거 KOSPI 200 구성종목 | KRX Data Marketplace | 5년+ | survivorship bias 없는 과거 universe | 제공 방식·라이선스 확인 후 별도 Issue |
| 공시 접수시각·원문 | [OpenDART 공시검색](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001) | 5년 | 재무정보의 실제 공개 가능시각과 point-in-time 결합 | `OPENDART_API_KEY` 사용 별도 Issue |
| 기준금리·환율·CPI | [한국은행 ECOS Open API](https://ecos.bok.or.kr/api/) | 5년+ | 시장 국면과 거시 설명 | `ECOS_API_KEY` 사용 별도 Issue |
| 실시간 시세·모의투자 | KIS Developers | 축적 시작일 이후 | 화면 현재가와 모의 주문 | 학습용 5년 Raw와 분리 |

OpenDART·KRX·ECOS는 프로젝트에 필요하지만 인증·호출 계약·Raw 경로가 서로 다르므로 현재
금융위 수집기에 억지로 섞지 않는다. 각 source는 별도 collector와
`raw/{source}/{dataset}/...` lineage를 갖도록 후속 작업으로 분리한다.

## Raw 저장 계약

```text
raw/data-go-kr/{dataset}/operation={operation}/year=YYYY/month=MM/{sha256}.jsonl.gz
```

한 줄은 API payload와 lineage envelope로 구성한다.

```json
{
  "collectedAt": "2026-08-19T00:00:00+00:00",
  "dataset": "stock_price",
  "operation": "getStockPriceInfo",
  "payload": {"basDt": "20260818", "srtnCd": "005930"},
  "payloadHash": "...",
  "source": "data-go-kr"
}
```

- `payload`는 수정하지 않는다.
- `payload.basDt`만 월 partition의 기준으로 사용한다.
- payload hash와 batch hash로 같은 batch의 재실행을 멱등 처리한다.
- 실제 Azure는 Entra ID/`DefaultAzureCredential`만 사용한다.
- API Key, `.env`, CSV/Parquet/DB 파일은 Git에 저장하지 않는다.

## 실행

### 모델 핵심 데이터 5년 백필

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.collect_public_data \
  --dataset stock_price \
  --dataset market_index \
  --dataset stock_master \
  --dataset financial_statement \
  --history-years 5 \
  --all-pages \
  --rows 10000
```

`--history-years 5`는 실행일을 종료일로 사용한다. 재현 가능한 백필은
`--end-date YYYY-MM-DD`를 함께 지정한다.

### 8개 dataset, 52개 operation 전체 백필

호출량과 소요 시간을 확인한 뒤 실행한다. 공공데이터포털 개발계정 호출 한도는 공식 페이지
기준 일 10,000회이므로, 필요하면 dataset 단위로 나누어 재실행한다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.collect_public_data \
  --all-datasets \
  --all-operations \
  --history-years 5 \
  --all-pages \
  --rows 10000
```

장기간 범위 요청이 시간 초과되는 operation은 날짜 분할 백필을 사용한다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.backfill_public_data_by_date \
  --dataset stock_issuance \
  --operation getStocIssuStat_V3 \
  --start-date 2021-08-17 \
  --end-date 2026-08-19 \
  --workers 4
```

이 CLI는 각 `basDt`를 독립 호출하므로 큰 범위 filter에서 API gateway가 시간 초과되는
경우에도 이미 완료된 날짜를 content-addressed Blob으로 보존한다.

### 증분 수집

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.collect_public_data \
  --all-datasets \
  --all-operations \
  --date 2026-08-18 \
  --all-pages \
  --rows 10000
```

### 매일 자동 증분 수집

`.github/workflows/raw-daily-collection.yml`은 매일 15:30 KST에 전체 8개 dataset과
52개 operation을 갱신한다. 금요일 데이터의 차주 월요일 제공, 공휴일, 지연 갱신을 놓치지
않도록 최근 7일을 **일자별 독립 요청**으로 다시 확인한다. 같은 날짜의 같은 payload batch는
content-addressed 경로가 같아 기존 Blob을 재사용한다.

필요한 GitHub Actions 설정:

- Secret `DATA_GO_KR_API_KEY`
- OIDC Secret `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- OIDC principal에 Storage Blob Data Contributor 권한

스케줄 workflow는 GitHub 기본 브랜치의 파일을 기준으로 실행되므로 이 변경이 `main`에
반영된 뒤 자동 실행이 시작된다. 수동 실행에서는 `lookback_days`를 1~31 사이로 지정할 수
있다.

### 실제 Raw 보유기간 감사

payload를 전수 다운로드하지 않고 canonical 경로의 월 partition을 읽는다. 기본 필수 대상은
`stock_price/getstockpriceinfo`와 `market_index/getstockmarketindex`다.

```bash
docker compose --env-file .env.azure --profile data run --rm --no-deps data \
  python -m scripts.audit_raw_coverage --minimum-years 5
```

## 완료 기준

- 핵심 가격·주가지수 operation의 첫 월과 마지막 월 간격이 60개월 이상이다.
- Azure `raw` container에 8개 dataset의 canonical prefix가 존재한다.
- 최신 증분 수집은 실패 operation 없이 종료된다.
- Raw 외의 `processed`, `features`, PostgreSQL 금융 테이블은 이 작업에서 변경하지 않는다.

## 2020-01-01 이후 전체 백필 실행 결과

2026-08-20에 8개 dataset, 52개 operation을 대상으로 `2020-01-01~2026-08-19`
수집을 실행했다. 일반 operation은 범위 조회로 적재했고, 장기간 범위 요청이 시간 초과된
`getStocIssuStat_V3`는 날짜 분할 백필로 전환했다.

- 전체 operation: 52개 조회·적재 완료
- 핵심 주가·시장지수·종목마스터·ETF/ETN/ELW: `2020-01~2026-08`, 월 누락 0
- `getStocIssuStat_V3`: 2020-01-01~2026-08-19의 2,423일을 날짜별 조회
- `getStocIssuStat_V3` 원천 제공 범위: `2020-07~2026-08`, 월 누락 0
- `getStocIssuStat_V3` 적재 처리: 17,310,302 records, 최종 실패 0
- `stock_master/getItemInfo`: 4,172,408 records, 실패 0
- `stock_price` 4 operations: 4,567,680 records, 실패 0
- 전처리·Processed·Features 생성: 실행하지 않음

`stock_dividend/getDiviInfo_V2`와 `stock_issuance/getItemBasiInfo_V3`는 API의 `basDt`가
과거 일별 history가 아니라 현재 snapshot을 나타내므로 Raw 월 범위가 2026-08 하나다.
배당일·발행일 같은 실제 event 날짜는 payload의 별도 필드에 존재하며 이 작업에서는
해석하거나 전처리하지 않는다. 공시처럼 사건이 없을 수 있는 데이터의 빈 월도 수집 실패로
간주하지 않는다.
