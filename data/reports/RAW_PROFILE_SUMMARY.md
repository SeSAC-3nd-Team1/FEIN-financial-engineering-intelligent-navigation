# 금융 Raw 실데이터 프로파일링 결과

> 기준: Azure Blob canonical Raw 전수 프로파일링. GitHub Actions run `31932890997` (2026-08-16).

## 핵심 결론

- Raw JSONL 한 줄은 API business row 자체가 아니라 `payload`와 lineage metadata를 함께 가진 envelope이다.
- 실제 전처리/모델링 컬럼은 `payload` 내부를 기준으로 하고, `payloadHash`, `collectedAt`, source blob 경로는 lineage로 보존한다.
- 8개 dataset, 52 operation, 4,228 blobs, 24,073,651 records를 전수 확인했다.
- malformed JSON, invalid payload, missing/invalid `payload.basDt`는 전 operation에서 0건이었다.
- 모든 dataset을 동일한 '5년 일별 시계열'로 해석하면 안 된다. 가격/지수는 일별 시계열이지만 배당·일부 발행정보는 snapshot이고, 재무/공시는 훨씬 오래된 기준일을 포함한다.
- 숫자처럼 보이는 식별자(`srtnCd`, `crno`, ISIN 등)는 문자열로 보존한다. 일부 공시 숫자형 문자열은 int64 범위를 초과하므로 안전한 범위를 벗어나면 문자열로 유지한다.

## Dataset 요약

| dataset | operations | blobs | records | compressed | basDt range | invalid |
|---|---:|---:|---:|---:|---|---:|
| `disclosure` | 33 | 1,749 | 80,045 | 12.8 MiB | 20090730 ~ 20260804 | 0 |
| `financial_statement` | 3 | 1,030 | 1,239,611 | 104.0 MiB | 20001231 ~ 20260813 | 0 |
| `market_index` | 3 | 191 | 467,358 | 46.9 MiB | 20210817 ~ 20260813 | 0 |
| `security_product` | 3 | 288 | 5,362,704 | 504.6 MiB | 20210817 ~ 20260813 | 0 |
| `stock_dividend` | 1 | 2 | 71,681 | 4.1 MiB | 20260813 ~ 20260813 | 0 |
| `stock_issuance` | 4 | 528 | 10,135,621 | 705.4 MiB | 20210816 ~ 20260813 | 0 |
| `stock_master` | 1 | 126 | 3,211,333 | 295.6 MiB | 20210817 ~ 20260813 | 0 |
| `stock_price` | 4 | 314 | 3,505,298 | 402.3 MiB | 20210817 ~ 20260813 | 0 |

## Dataset별 해석

### stock_price
- 3,505,298 rows. 핵심 `getstockpriceinfo`는 3,381,629 rows, 2021-08-17~2026-08-13.
- KOSPI/KOSDAQ/KONEX 종목의 일별 OHLCV, 거래대금, 상장주식수, 시가총액을 보유한다.
- `srtnCd`는 `005930`처럼 선행 0이 있으므로 문자열 타입이 필수다.

### market_index
- 467,358 rows. 주가지수 핵심 `getstockmarketindex`는 190,359 rows.
- KOSPI/KOSDAQ/KRX/테마지수 등 206개 지수명이 관측됐다.
- 모델의 시장국면·시장 모멘텀·시장 변동성 Feature로 사용할 수 있다.

### stock_master
- 3,211,333 rows, `getiteminfo` 1개 operation.
- 종목코드/ISIN/종목명/시장/법인명/법인번호 매핑에 적합하다.
- 최신 snapshot만 사용해 과거 유니버스를 재구성하면 survivorship bias가 생길 수 있으므로 모델 학습용 역사적 편입판단에는 직접 쓰지 않는다.

### financial_statement
- 1,239,611 rows. BS 400,496 / IS 193,579 / 요약재무 645,536.
- `basDt`가 2000년까지 존재하므로 수집 파티션 기간과 business 기준일 범위가 동일하지 않다.
- 요약재무에는 매출, 영업이익, 순이익, 자산, 부채, 자본, 부채비율 등이 존재한다.
- 회계 기준일은 실제 시장 공개일과 다를 수 있으므로 OpenDART 접수일 등 availability date를 붙이기 전에는 주가와 point-in-time JOIN하지 않는다.

### security_product
- 5,362,704 rows. ELW 3,934,588 / ETF 992,348 / ETN 435,768.
- 모델 v1의 개별주식 ranking에는 직접 포함하지 않지만 추후 ETF/ETN 전략 확장에 사용할 수 있다.

### stock_issuance
- 10,135,621 rows로 가장 크다. `getstocissustat_v3`가 9,959,677 rows.
- `getitembasiinfo_v3`는 `basDt=20260813` 한 시점 snapshot이며 일부 날짜 필드는 결측률이 매우 높다.
- snapshot과 event history를 동일한 시간축 데이터처럼 처리하지 않는다.

### stock_dividend
- 71,681 rows. `basDt=20260813` 한 시점 snapshot.
- 별도 `dvdnBasDt`, 지급일 등 실제 배당 event 관련 날짜가 있으므로 `basDt`를 배당 발생일로 사용하면 안 된다.
- `cashDvdnPayDt` 약 41.5%, `stckHndvDt` 약 97.3%가 빈 값으로 관측됐다.

### disclosure
- 80,045 rows, 33 operations.
- 넓고 sparse한 schema가 많으며 일부 operation은 100% 빈 필드를 포함한다.
- `basDt`가 2009년까지 내려가는 operation도 있어 단일 5년 필터 가정을 적용하지 않는다.
- 공시 유형별 schema가 크게 달라 공통 wide table보다 operation별 Processed dataset을 유지하는 편이 안전하다.

## 전체 Operation 통계

| dataset | operation | blobs | rows | fields | all-empty fields | partial fields | basDt range |
|---|---|---:|---:|---:|---:|---:|---|
| `disclosure` | `getamorcocobonddisclinfo_v2` | 113 | 346 | 39 | 7 | 19 | 20140731 ~ 20260803 |
| `disclosure` | `getassetranputbackoptidiscinfo_v2` | 36 | 73 | 3 | 0 | 0 | 20211022 ~ 20260519 |
| `disclosure` | `getbonuissudiscinfo_v2` | 60 | 312 | 18 | 2 | 5 | 20210817 ~ 20260731 |
| `disclosure` | `getbusiconvdiscinfo_v2` | 34 | 61 | 44 | 8 | 15 | 20210817 ~ 20260626 |
| `disclosure` | `getbusiinhetdiscinfo_v2` | 31 | 51 | 51 | 12 | 14 | 20210820 ~ 20260709 |
| `disclosure` | `getbusisuspdiscinfo_v2` | 53 | 159 | 18 | 4 | 6 | 20210901 ~ 20260731 |
| `disclosure` | `getbwrighissudiscinfo_v2` | 58 | 325 | 60 | 9 | 13 | 20210819 ~ 20260630 |
| `disclosure` | `getcapiincrwithconsbonuissudiscinfo_v2` | 51 | 159 | 73 | 16 | 21 | 20210831 ~ 20260731 |
| `disclosure` | `getcapiincrwithconsdiscinfo_v2` | 61 | 5,912 | 71 | 11 | 29 | 20210817 ~ 20260804 |
| `disclosure` | `getcbrighissudiscinfo_v2` | 61 | 3,995 | 66 | 40 | 9 | 20210817 ~ 20260803 |
| `disclosure` | `getdeberighconvdiscinfo_v2` | 46 | 83 | 51 | 13 | 5 | 20160325 ~ 20260720 |
| `disclosure` | `getdeberighinhediscinfo_v2` | 51 | 71 | 120 | 38 | 32 | 20160325 ~ 20260427 |
| `disclosure` | `getdishdiscinfo_v2` | 16 | 43 | 9 | 1 | 2 | 20210901 ~ 20260619 |
| `disclosure` | `getdissreasdiscinfo_v2` | 61 | 376 | 9 | 2 | 2 | 20210824 ~ 20260803 |
| `disclosure` | `getdivicombdiscinfo_v2` | 31 | 48 | 94 | 16 | 23 | 20160621 ~ 20250605 |
| `disclosure` | `getdividiscinfo_v2` | 111 | 32,409 | 47 | 0 | 3 | 20131231 ~ 20260531 |
| `disclosure` | `getebrighissudiscinfo_v2` | 58 | 325 | 45 | 7 | 9 | 20210819 ~ 20260630 |
| `disclosure` | `getgenemeetstocpublnotidiscinfo_v2` | 61 | 16,978 | 3 | 0 | 0 | 20210817 ~ 20260804 |
| `disclosure` | `getlitietcdiscinfo_v2` | 59 | 275 | 10 | 1 | 6 | 20210909 ~ 20260803 |
| `disclosure` | `getmnadiscinfo_v2` | 61 | 1,262 | 79 | 17 | 21 | 20210818 ~ 20260804 |
| `disclosure` | `getoffssecumarkdelidiscinfo_v2` | 20 | 22 | 13 | 2 | 3 | 20100709 ~ 20250213 |
| `disclosure` | `getoffssecumarklistdiscinfo_v2` | 11 | 11 | 13 | 3 | 1 | 20100917 ~ 20260713 |
| `disclosure` | `getoutsdirehumaresoaffarepo_v2` | 61 | 7,577 | 16 | 9 | 2 | 20210817 ~ 20260804 |
| `disclosure` | `getprocbycredbankdiscinfo_v2` | 64 | 91 | 9 | 1 | 1 | 20090730 ~ 20260713 |
| `disclosure` | `getreducapidiscinfo_v2` | 61 | 591 | 34 | 3 | 8 | 20210819 ~ 20260804 |
| `disclosure` | `getreviprocdiscinfo_v2` | 49 | 122 | 8 | 1 | 3 | 20210917 ~ 20260730 |
| `disclosure` | `getspilupdiscinfo_v2` | 28 | 189 | 50 | 12 | 13 | 20210930 ~ 20260331 |
| `disclosure` | `getstocexchtrandiscinfo_v2` | 39 | 114 | 58 | 17 | 14 | 20210903 ~ 20260720 |
| `disclosure` | `getstocoptirepo_v2` | 61 | 3,861 | 30 | 12 | 8 | 20210817 ~ 20260804 |
| `disclosure` | `getstocsubscertconvdiscinfo_v2` | 61 | 501 | 49 | 9 | 15 | 20210817 ~ 20260804 |
| `disclosure` | `getstocsubscertinhediscinfo_v2` | 60 | 583 | 80 | 20 | 26 | 20210817 ~ 20260731 |
| `disclosure` | `gettreastocrepudiscinfo_v2` | 60 | 992 | 109 | 5 | 3 | 20210817 ~ 20260804 |
| `disclosure` | `gettreastocselldiscinfo_v2` | 61 | 2,128 | 85 | 2 | 18 | 20210817 ~ 20260804 |
| `financial_statement` | `getbs_v2` | 125 | 400,496 | 13 | 0 | 0 | 20150331 ~ 20260531 |
| `financial_statement` | `getincostat_v2` | 96 | 193,579 | 13 | 0 | 0 | 20150331 ~ 20260531 |
| `financial_statement` | `getsummfinastat_v2` | 809 | 645,536 | 15 | 0 | 0 | 20001231 ~ 20260813 |
| `market_index` | `getbondmarketindex` | 61 | 3,662 | 15 | 0 | 0 | 20210817 ~ 20260813 |
| `market_index` | `getderivationproductmarketindex` | 66 | 273,337 | 10 | 0 | 1 | 20210817 ~ 20260813 |
| `market_index` | `getstockmarketindex` | 64 | 190,359 | 21 | 0 | 2 | 20210817 ~ 20260813 |
| `security_product` | `getelwpriceinfo` | 139 | 3,934,588 | 15 | 0 | 0 | 20210817 ~ 20260813 |
| `security_product` | `getetfpriceinfo` | 80 | 992,348 | 18 | 0 | 1 | 20210817 ~ 20260813 |
| `security_product` | `getetnpriceinfo` | 69 | 435,768 | 18 | 0 | 1 | 20210817 ~ 20260813 |
| `stock_dividend` | `getdiviinfo_v2` | 2 | 71,681 | 22 | 0 | 3 | 20260813 ~ 20260813 |
| `stock_issuance` | `getitembasiinfo_v3` | 1 | 17,528 | 15 | 0 | 6 | 20260813 ~ 20260813 |
| `stock_issuance` | `getlockupretuinfo_v3` | 61 | 6,390 | 18 | 0 | 1 | 20210817 ~ 20260813 |
| `stock_issuance` | `getstocissuinfo_v3` | 205 | 152,026 | 15 | 0 | 2 | 20210817 ~ 20260813 |
| `stock_issuance` | `getstocissustat_v3` | 261 | 9,959,677 | 5 | 0 | 0 | 20210816 ~ 20260813 |
| `stock_master` | `getiteminfo` | 126 | 3,211,333 | 7 | 0 | 0 | 20210817 ~ 20260813 |
| `stock_price` | `getpreemptiverightcertificatepriceinfo` | 61 | 1,439 | 20 | 0 | 3 | 20210819 ~ 20260813 |
| `stock_price` | `getpreemptiverightsecuritiespriceinfo` | 61 | 20,260 | 21 | 0 | 0 | 20210817 ~ 20260813 |
| `stock_price` | `getsecuritiespriceinfo` | 63 | 101,970 | 14 | 0 | 0 | 20210817 ~ 20260813 |
| `stock_price` | `getstockpriceinfo` | 129 | 3,381,629 | 15 | 0 | 0 | 20210817 ~ 20260813 |

## 전처리 규칙

1. canonical Raw는 수정/삭제하지 않는다.
2. `payload`만 business data로 정규화하고 envelope은 lineage로 유지한다.
3. `basDt`는 YYYYMMDD 검증 후 date로 변환한다.
4. 빈 문자열은 Processed에서 NULL로 정규화한다.
5. 프로파일 결과가 100% 안전하게 숫자 변환 가능한 경우에만 숫자 타입을 적용한다.
6. 식별자/코드는 숫자처럼 보여도 문자열로 유지한다.
7. int64/float64 안전 범위를 벗어나는 숫자형 문자열은 원문 문자열을 보존한다.
8. 핵심 모델링 operation은 필수 business key/값을 별도 품질검사한다.
9. 월별 Parquet으로 저장하고 각 파일에 source blob, accepted/rejected, conversion error를 manifest로 기록한다.
10. 가격 Feature는 과거 데이터만 사용하고 미래 수익률은 `target_*` 컬럼으로 분리한다.

## 프로파일 재현

세부 field-level 분포(JSON/Markdown)는 프로파일 workflow artifact로 남는다. 동일 프로파일러를 실행하면 field별 present/null/empty, numeric/date 변환률, cardinality(상한), min/max, 예시값, 월별 row 분포를 다시 생성할 수 있다.
