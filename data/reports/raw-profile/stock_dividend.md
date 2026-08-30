# Raw Payload Profile - stock_dividend

> Raw JSONL의 `payload` 내부 API 필드를 기준으로 분석한 결과다. Envelope은 lineage metadata로 별도 집계한다.

- generated_at: `2026-08-16T07:05:17.712582+00:00`
- total_blobs: **2**
- total_rows: **71,681**
- compressed_bytes: **4,331,523**
- invalid_paths: **0**

## Operation summary

| operation(path) | API operation | blobs | rows | basDt range | payload fields | invalid payload |
|---|---|---:|---:|---|---:|---:|
| `getdiviinfo_v2` | `getDiviInfo_V2` | 2 | 71,681 | 20260813 ~ 20260813 | 22 | 0 |

## getdiviinfo_v2

Rows: **71,681**, Blobs: **2**, basDt: `20260813 ~ 20260813`
Envelope: payloadHash 71,681/71,681, legacy 71,681/71,681

### Payload field profile

| field | inferred | present% | null/empty% | unique | max len | min | max | examples |
|---|---|---:|---:|---:|---:|---|---|---|
| `basDt` | date(YYYYMMDD) | 100.00 | 0.00 | 1 | 8 | 20260813 | 20260813 | 20260813 |
| `cashDvdnPayDt` | date(YYYYMMDD) | 100.00 | 41.49 | 4857 | 8 | 19860104 | 99991231 | 20200401, 20210412, 20220407, 20230407, 20240408 |
| `cashGrdnDvdnRt` | numeric-like | 100.00 | 0.00 | 119 | 12 | 0 | 5.5221197729 | 0, .08, .12, .1, .2 |
| `crno` | integer-like | 100.00 | 0.00 | 4445 | 13 | 0 | 4646743520000 | 1801110331502, 1350110029576, 1101113329631, 1101113352004, 1301110057421 |
| `dvdnBasDt` | date(YYYYMMDD) | 100.00 | 0.00 | 1944 | 8 | 19851231 | 20261123 | 20191231, 20201231, 20211231, 20221231, 20231231 |
| `isinCd` | string | 100.00 | 0.00 | 6255 | 12 | HK0000065257 | KYG2115T1076 | KR7086670007, KR7086710001, KR7086720000, KR7086790003, KR7086820008 |
| `isinCdNm` | string | 100.00 | 0.00 | 6247 | 33 | (주)라닉스 | 힘스 | 비엠티, 선진뷰티사이언스, 코크렙제7호위탁관리부동산투자회사, 하나금융지주, 바이오솔루션 |
| `scrsItmsKcd` | integer-like | 100.00 | 0.00 | 24 | 4 | 101 | 223 | 0101, 0201, 0202, 0203, 0204 |
| `scrsItmsKcdNm` | string | 100.00 | 0.00 | 24 | 5 | 10우선주 | 우선주 | 보통주, 우선주, 2우선주, 3우선주, 4우선주 |
| `stckDvdnRcd` | integer-like | 100.00 | 0.00 | 4 | 2 | 1 | 4 | 02, 03, 04, 01 |
| `stckDvdnRcdNm` | string | 100.00 | 0.00 | 4 | 4 | 동시배당 | 현금배당 | 현금배당, 동시배당, 무배당, 주식배당 |
| `stckGenrCashDvdnRt` | numeric-like | 100.00 | 0.00 | 2496 | 15 | 0 | 10962 | 30, 40, 50, 120, 4 |
| `stckGenrDvdnAmt` | numeric-like | 100.00 | 0.00 | 1213 | 10 | 0 | 1851481913 | 150, 200, 250, 600, 20 |
| `stckGenrDvdnRt` | numeric-like | 100.00 | 0.00 | 433 | 12 | 0 | 400 | 0, 1, 3, 5, 1.65563 |
| `stckGrdnDvdnAmt` | numeric-like | 100.00 | 0.00 | 81 | 5 | 0 | 9600 | 0, 40, 60, 50, 1000 |
| `stckGrdnDvdnRt` | numeric-like | 100.00 | 0.00 | 9 | 10 | 0 | 0.1252408 | 0, .1, .005, .001349315, .05 |
| `stckHndvDt` | date(YYYYMMDD) | 100.00 | 97.31 | 878 | 8 | 19880418 | 20260424 | 20060404, 20190425, 20200424, 20210423, 20220425 |
| `stckIssuCmpyNm` | string | 100.00 | 0.00 | 4438 | 33 | (주)넥스트솔루션 | 힘스 | 비엠티, 선진뷰티사이언스, 코크렙제7호위탁관리부동산투자회사, 하나금융지주, 바이오솔루션 |
| `stckParPrc` | numeric-like | 100.00 | 0.00 | 30 | 9 | 0 | 100000000 | 500, 5000, 100, 1000, 2500 |
| `stckStacMd` | integer-like | 100.00 | 0.01 | 12 | 2 | 1 | 12 | 12, 10, 05, 06, 09 |
| `trsnmDptyDcd` | integer-like | 100.00 | 0.00 | 5 | 2 | 1 | 99 | 02, 01, 90, 03, 99 |
| `trsnmDptyDcdNm` | string | 100.00 | 0.00 | 5 | 7 | 국민은행 | 해당없음 | 국민은행, 한국예탁결제원, 자체, 하나은행, 해당없음 |

### Monthly row distribution

| month | rows |
|---|---:|
| 2026-08 | 71,681 |
