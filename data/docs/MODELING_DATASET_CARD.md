# 모델링 Dataset Card

## 1. 목적

이 문서는 모델 담당자가 Azure `features` 컨테이너의 Dataset을 별도 Raw 해석 없이 바로 판단할 수 있도록 용도, grain, 시간 기준, 사용 가능 상태, 누출 위험을 정리한다.

현재 v1은 **한투 API를 사용하지 않는다.** 현재 canonical Raw에 존재하는 공공데이터포털 금융 데이터를 기준으로 생성하며, KRX/OpenDART의 별도 보강 데이터는 향후 point-in-time enrichment 단계에서 추가한다.

## 2. Dataset 상태 요약

| Dataset | Grain | 상태 | 주요 용도 | 주의사항 |
|---|---|---|---|---|
| `model_stock_daily` | 종목 × 거래일 | `training_ready` | 개별주식 수익률/랭킹 모델 | `target_*`는 입력 Feature에서 제외 |
| `market_index_daily` | 지수 × 거래일 | `training_ready` | 시장국면/시장 모멘텀 보조 Feature | 사용할 지수 Universe를 모델에서 명시 |
| `security_master_latest` | 종목당 최신 1행 | `reference_only` | 종목코드·ISIN·법인번호·시장 매핑 | 과거 Universe 복원에 사용 금지 |
| `financial_snapshot` | 법인 × 재무기준일 × 재무구분 | `research_only_until_availability_date` | 재무비율 연구 | 공시 가능시점 확보 전 가격과 JOIN 금지 |
| `financial_company_year_latest` | 법인 × 사업연도 × 재무구분 | `research_only_until_availability_date` | YoY 성장성 연구 | latest 선택 자체가 미래정보가 될 수 있음 |

## 3. model_stock_daily

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
- 원본에서 동일 key가 중복될 경우 OHLCV/시총 값이 완전히 같을 때만 1행으로 축약한다.
- 동일 key의 값이 서로 다르면 자동 선택하지 않고 pipeline을 실패시킨다.

### 관측 Raw 범위

- 핵심 원본 `getstockpriceinfo`: **3,381,629 rows**
- `trade_date`: **2021-08-17 ~ 2026-08-13**
- 시장: KOSPI / KOSDAQ / KONEX

### Feature 사용 권장

가격/거래량 기반 Feature는 해당 행의 `trade_date`까지 공개된 과거 값만 사용해 계산한다.

모델 입력 후보:

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

- `target_return_5d`: 5거래일 후 수익률
- `target_return_20d`: 20거래일 후 수익률
- `target_up_20d`: 20거래일 후 수익률이 0보다 큰지 여부

**`target_*`, `target_date_*`는 절대로 입력 Feature에 포함하지 않는다.**

### Split

전체 거래일을 시간순으로 정렬해 다음과 같이 나눈다.

- train: 앞 70%
- validation: 다음 15%
- test: 마지막 15%

랜덤 split을 사용하지 않는다.

`eligible_target_5d`, `eligible_target_20d`는 미래 Target 날짜가 현재 split의 마지막 날짜를 넘어가지 않는 행만 `true`다. 예를 들어 20일 Target 학습에서는 다음 조건을 권장한다.

```python
trainable = df[
    df["history_120d_ready"]
    & df["eligible_target_20d"]
    & df["target_return_20d"].notna()
]
```

## 4. market_index_daily

### 저장 위치

```text
features/market_index_daily/version=v1/year=YYYY/month=MM/part-00000.parquet
```

### Source / Grain

- Source: `market_index / getstockmarketindex`
- Raw: **190,359 rows**
- 기간: **2021-08-17 ~ 2026-08-13**
- Grain: `index_name × trade_date`
- 관측된 지수명: 206개

### 생성 Feature

- `index_return_1d`
- `index_momentum_20d`
- `index_sma_20d`
- `index_above_sma_20d`
- `index_volatility_20d`

### 권장 결합

개별주식 행과 `trade_date` 기준으로 결합한다. 단, 206개 지수를 모두 wide feature로 만들기 전에 모델 목적에 맞춰 KOSPI/KOSDAQ/KOSPI200 등 사용할 지수 목록을 명시한다.

## 5. security_master_latest

### 목적

- `stock_code`
- `isin_code`
- `stock_name`
- `market_category`
- `corporation_number`

간 최신 매핑을 제공한다.

### 금지 용도

이 Dataset은 **현재/최신 reference**다. 이를 사용해 과거 특정 날짜의 상장 Universe를 필터링하면 당시 이미 상장폐지된 종목이 빠지는 survivorship bias가 발생할 수 있다.

따라서 이름 표시, 법인번호 연결 등 reference 용도로만 사용한다.

## 6. financial_snapshot

### Source

`financial_statement / getsummfinastat_v2`

Raw 관측:

- **645,536 rows**
- `base_date`: **2000-12-31 ~ 2026-08-13**
- 주요 원본: 매출, 영업이익, 순이익, 자산, 부채, 자본, 보고 부채비율

### 생성 재무지표

- `debt_to_equity`
- `debt_ratio_pct_calculated`
- `roa`
- `roe`
- `operating_margin`
- `net_margin`

### 현재 상태가 research-only인 이유

`base_date`는 회계 기준일 또는 API 기준일이지, 모델이 그 정보를 **시장 참여자가 실제로 알 수 있었던 날짜**를 보장하지 않는다.

예를 들어 2025-03-31 분기 값을 2025-03-31 주가 예측에 사용하면 실제 공시 전 정보를 미리 본 look-ahead bias가 될 수 있다.

따라서 `point_in_time_join_ready = false`이며, OpenDART 접수일/공시일 등 availability timestamp를 붙인 뒤에만 가격 데이터와 point-in-time JOIN한다.

## 7. financial_company_year_latest

회사/사업연도/재무구분별 latest Snapshot을 선택하고 다음 연구용 YoY를 계산한다.

- `sales_growth_yoy`
- `operating_profit_growth_yoy`
- `net_income_growth_yoy`

이 Dataset 역시 현재 `research_only = true`다. 사업연도 기준 latest 행을 전체 기간에서 선택하는 과정 자체가 미래정보를 포함할 수 있으므로 백테스트 입력으로 바로 사용하지 않는다.

## 8. 모델 담당자 기본 사용 순서

v1에서 바로 모델을 만들려면 다음 순서를 권장한다.

```text
model_stock_daily
      │
      ├─ price / momentum / volatility / liquidity features
      │
      ├── LEFT JOIN market_index_daily (trade_date)
      │
      └─ target_return_20d 또는 target_up_20d
             ↓
       시간순 train/validation/test
             ↓
          모델 학습
```

초기 모델에서는 재무 Dataset을 제외해도 된다. 재무 Dataset은 OpenDART availability date 보강이 끝난 뒤 별도 v2에서 안전하게 결합한다.

## 9. 모델 입력에서 기본 제외할 컬럼

다음은 식별/lineage/label/분할용이므로 수치 모델의 입력 Feature로 자동 투입하지 않는다.

- `target_*`
- `target_date_*`
- `eligible_target_*`
- `split`
- `_payload_hash`
- `_collected_at`
- `_source_blob`
- 종목명 등 고카디널리티 문자열

`stock_code`는 join/group key이며 숫자로 변환해 연속형 Feature처럼 사용하지 않는다.

## 10. 버전 및 재현성

- Processed schema: `v1`
- Feature schema: `v1`
- 각 Processed 월 파일에는 source blob 목록, accepted/rejected, conversion error, 생성 Git SHA가 quality manifest로 남는다.
- 각 Feature 파일에는 `feature_version`, `processed_schema_version`, Git SHA, record count metadata가 남는다.
- 최종 전체 manifest: `features/_manifests/model-datasets/version=v1/manifest.json`
