# 모델링 Dataset Card

## 1. 목적

Azure `features` 컨테이너의 Dataset을 모델 담당자가 Raw를 다시 해석하지 않고 사용할 수 있도록 용도, grain, 시간 기준, 상태, 누출 위험을 정리한다.

현재 v1은 KIS를 학습 Raw로 사용하지 않는다. 공공데이터포털 canonical Raw를 기준으로 만들며 KRX/OpenDART/ECOS 등의 보강 데이터는 이후 enrichment 단계에서 추가한다.

## 2. Dataset 상태 요약

| Dataset | Grain | 상태 | 주요 용도 | 주의사항 |
|---|---|---|---|---|
| `model_stock_daily` | 종목 × 가격 관측일 | `training_ready` | 개별주식 수익률/랭킹 모델 | `target_*` 입력 금지, 수정주가 보강 필요 |
| `market_index_daily` | 지수 × 관측일 | `training_ready` | 시장국면/모멘텀 보조 Feature | 사용할 지수 Universe 명시 |
| `security_master_latest` | 종목당 최신 1행 | `reference_only` | 종목코드/ISIN/법인번호/시장 매핑 | 과거 Universe 복원 금지 |
| `financial_snapshot` | 법인 × 재무기준일 × 재무구분 | `research_only_until_availability_date` | 재무비율 연구 | 실제 공개시점 확보 전 가격 JOIN 금지 |
| `financial_company_year_latest` | 법인 × 사업연도 × 재무구분 | `research_only_until_availability_date` | YoY 성장성 연구 | latest 선택 자체가 미래정보가 될 수 있음 |

## 3. Horizon 의미

현재 가격 Feature/Target은 종목별로 `trade_date` 정렬 후 pandas `shift(N)` / `rolling(N)`으로 계산한다.

따라서 `5d`, `20d`, `60d`, `120d`는 **종목별 N번째 관측치**를 의미한다. 대부분 정상 거래 종목에서는 N거래일과 유사하지만 거래정지/관측 누락이 있으면 독립적인 KRX 시장 N거래일과 다를 수 있다.

시장 session 기준 horizon이 필요하면 별도 KRX 거래일 calendar로 reindex하는 v2가 필요하다.

## 4. model_stock_daily

### 저장 위치

```text
features/model_stock_daily/version=v1/year=YYYY/month=MM/part-00000.parquet
```

### Source

```text
Raw stock_price / getstockpriceinfo
→ Processed stock_price / getstockpriceinfo
→ model_stock_daily
```

### Grain / Key

- Grain: `stock_code × trade_date`
- Natural key: `stock_code`, `trade_date`
- 동일 key 중복은 OHLCV/시총 값이 완전히 같을 때만 1행으로 축약
- 동일 key의 주요 값이 충돌하면 pipeline 실패

### 관측 Raw 범위

- 핵심 `getstockpriceinfo`: 3,381,629 rows
- `trade_date`: 2021-08-17 ~ 2026-08-13
- 시장: KOSPI / KOSDAQ / KONEX

### 입력 후보

- `return_1d`
- `momentum_5d`
- `momentum_20d`
- `momentum_60d`
- `momentum_120d`
- `sma_5d`
- `sma_20d`
- `sma_60d`
- `price_to_sma_20d`
- `volatility_20d`
- `volatility_60d`
- `volume_ratio_20d`
- `trading_value_sma_20d`
- `log_market_cap`
- 필요 시 당일 OHLCV/시가총액 원본값

### Target

- `target_return_5d`: 종목별 5번째 미래 관측치 수익률
- `target_return_20d`: 종목별 20번째 미래 관측치 수익률
- `target_up_20d`: `target_return_20d > 0`

`target_*`, `target_date_*`는 입력 Feature에 포함하지 않는다.

### Split

전체 관측 거래일을 시간순으로 정렬해 70/15/15로 train/validation/test를 나눈다. 랜덤 split은 사용하지 않는다.

`eligible_target_5d`, `eligible_target_20d`는 실제 target 관측일이 해당 split의 마지막 날짜를 넘지 않는 행만 true다.

예시:

```python
trainable = df[
    df["history_120d_ready"]
    & df["eligible_target_20d"]
    & df["target_return_20d"].notna()
]
```

### 수정주가 주의

현재 계산은 원천 `close_price`를 사용한다. 액면분할, 권리락, 무상증자 등 corporate action을 완전히 반영한 adjusted price 계열이 별도 보강되기 전에는 장기 수익률/모멘텀/변동성/백테스트 결과를 최종 확정값처럼 해석하지 않는다.

## 5. market_index_daily

### 저장 위치

```text
features/market_index_daily/version=v1/year=YYYY/month=MM/part-00000.parquet
```

### Source / Grain

- Source: `market_index / getstockmarketindex`
- Raw: 190,359 rows
- 기간: 2021-08-17 ~ 2026-08-13
- Grain: `index_name × trade_date`
- 관측된 지수명: 206개

### Feature

- `index_return_1d`
- `index_momentum_20d`
- `index_sma_20d`
- `index_above_sma_20d`
- `index_volatility_20d`

개별주식과 `trade_date`로 결합할 수 있지만 206개 지수를 무조건 wide feature로 넣지 말고 KOSPI/KOSDAQ/KOSPI200 등 모델 목적에 맞는 지수 목록을 명시한다.

## 6. security_master_latest

최신 `stock_code`, `isin_code`, `stock_name`, `market_category`, `corporation_number` 매핑을 제공한다.

이 Dataset은 최신 reference다. 과거 특정 날짜의 상장 Universe 필터로 사용하면 상장폐지 종목 등이 빠져 survivorship bias가 생길 수 있으므로 표시/매핑용으로만 사용한다.

## 7. financial_snapshot

### Source

`financial_statement / getsummfinastat_v2`

- Raw: 645,536 rows
- `base_date`: 2000-12-31 ~ 2026-08-13
- 주요 원본: 매출, 영업이익, 순이익, 자산, 부채, 자본, 부채비율

### 생성 재무지표

- `debt_to_equity`
- `debt_ratio_pct_calculated`
- `roa`
- `roe`
- `operating_margin`
- `net_margin`

`base_date`는 시장 참여자가 해당 정보를 실제로 알 수 있었던 날짜가 아니다. OpenDART 접수일 등 availability timestamp를 확보하기 전에는 가격과 point-in-time JOIN하지 않는다. 현재 `point_in_time_join_ready = false`다.

## 8. financial_company_year_latest

회사/사업연도/재무구분별 latest Snapshot을 선택해 다음 연구용 YoY를 계산한다.

- `sales_growth_yoy`
- `operating_profit_growth_yoy`
- `net_income_growth_yoy`

현재 `research_only = true`이며 실제 공시 availability가 없는 상태에서 역사적 가격과 JOIN하지 않는다.

## 9. 모델 담당자 기본 사용 순서

```text
model_stock_daily
      │
      ├─ price / momentum / volatility / liquidity features
      │
      ├─ LEFT JOIN market_index_daily (trade_date, 선택 지수)
      │
      └─ target_return_20d 또는 target_up_20d
             ↓
       시간순 train/validation/test
             ↓
          모델 학습
```

초기 v1에서는 재무 Dataset을 제외할 수 있다. 재무는 availability date 보강 후 v2에서 PIT 방식으로 결합한다.

## 10. 입력에서 기본 제외할 컬럼

- `target_*`
- `target_date_*`
- `eligible_target_*`
- `split`
- `_payload_hash`
- `_collected_at`
- `_source_blob`
- 종목명 등 고카디널리티 문자열

`stock_code`는 join/group key이며 숫자로 변환해 연속형 Feature로 사용하지 않는다.

## 11. 버전 및 재현성

- Processed schema: `v1`
- Feature schema: `v1`
- Processed 월별 quality manifest: source blobs, accepted/rejected, conversion error, Git SHA
- Feature metadata: feature version, Processed schema version, Git SHA, record count
- 전체 manifest: `features/_manifests/model-datasets/version=v1/manifest.json`

Feature 정의나 horizon 의미를 바꾸는 경우 같은 v1의 의미를 조용히 변경하지 않고 새 version을 검토한다.
## ECOS macro_daily v1

한국은행 ECOS의 기준금리·환율·CPI·국고채를 일별 시장 모델에 결합하기 위한 보조
데이터셋이다. 2021-01-01 이후를 기본 백필 범위로 한다.

- 시간축: 환율 및 국고채 중 하나 이상이 관측된 날짜
- PIT 정책: `available_at <= date` as-of join만 허용
- CPI 제한: 공식 조회 응답에 공표 timestamp가 없어 관측월 + 2개월의 1일을 보수적으로 사용
- 생존자/미래 정보: 종목 universe를 만들지 않으며 target 컬럼도 포함하지 않음
- 재현성: Raw content hash, Processed schema version, feature version, git SHA 및 입력 lineage 기록
- 권장 용도: 시장 국면 feature, 환율·금리 민감도 연구
- 비권장 용도: 장중 의사결정, 정확한 CPI 발표 시각 반응 연구

공표 시각이 확보되면 새 feature version에서 `available_at` 정책을 변경해야 하며 기존
version을 덮어쓰지 않는다.
