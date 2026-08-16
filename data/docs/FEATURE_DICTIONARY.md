# Feature Dictionary v1

## model_stock_daily

| 컬럼 | 정의 | 계산 기준 | 입력/Target |
|---|---|---|---|
| `stock_code` | 종목 단축코드 | Raw `srtnCd`, 문자열 보존 | Key |
| `trade_date` | 거래일 | Raw `basDt` | Key |
| `close_price` | 종가 | Raw `clpr` | 원본 Feature 후보 |
| `open_price` | 시가 | Raw `mkp` | 원본 Feature 후보 |
| `high_price` | 고가 | Raw `hipr` | 원본 Feature 후보 |
| `low_price` | 저가 | Raw `lopr` | 원본 Feature 후보 |
| `volume` | 거래량 | Raw `trqu` | 원본 Feature 후보 |
| `trading_value` | 거래대금 | Raw `trPrc` | 원본 Feature 후보 |
| `market_cap` | 시가총액 | Raw `mrktTotAmt` | 원본 Feature 후보 |
| `listed_shares` | 상장주식수 | Raw `lstgStCnt` | 원본 Feature 후보 |
| `return_1d` | 1거래일 수익률 | `close_t / close_t-1 - 1` | Feature |
| `momentum_5d` | 5거래일 모멘텀 | `close_t / close_t-5 - 1` | Feature |
| `momentum_20d` | 20거래일 모멘텀 | `close_t / close_t-20 - 1` | Feature |
| `momentum_60d` | 60거래일 모멘텀 | `close_t / close_t-60 - 1` | Feature |
| `momentum_120d` | 120거래일 모멘텀 | `close_t / close_t-120 - 1` | Feature |
| `sma_5d` | 5일 단순이동평균 | 과거 포함 최근 5거래일 종가 평균 | Feature |
| `sma_20d` | 20일 단순이동평균 | 최근 20거래일 종가 평균 | Feature |
| `sma_60d` | 60일 단순이동평균 | 최근 60거래일 종가 평균 | Feature |
| `price_to_sma_20d` | 20일선 대비 가격 괴리 | `close / sma_20d - 1` | Feature |
| `volatility_20d` | 20일 연환산 실현변동성 | 최근 20일 `return_1d` 표준편차 × √252 | Feature |
| `volatility_60d` | 60일 연환산 실현변동성 | 최근 60일 `return_1d` 표준편차 × √252 | Feature |
| `volume_sma_20d` | 20일 평균 거래량 | 최근 20거래일 거래량 평균 | Feature |
| `volume_ratio_20d` | 평균 대비 거래량 | `volume / volume_sma_20d` | Feature |
| `trading_value_sma_20d` | 20일 평균 거래대금 | 최근 20거래일 거래대금 평균 | Feature |
| `log_market_cap` | 로그 시가총액 | `ln(market_cap)`, 양수만 | Feature |
| `history_120d_ready` | 120거래일 history 확보 여부 | `momentum_120d` 존재 여부 | Filter |
| `target_return_5d` | 5거래일 미래 수익률 | `close_t+5 / close_t - 1` | Target |
| `target_return_20d` | 20거래일 미래 수익률 | `close_t+20 / close_t - 1` | Target |
| `target_up_20d` | 20일 후 상승 여부 | `target_return_20d > 0` | Target |
| `target_date_5d` | 5일 Target의 실제 거래일 | 종목별 5행 이후 날짜 | Label metadata |
| `target_date_20d` | 20일 Target의 실제 거래일 | 종목별 20행 이후 날짜 | Label metadata |
| `split` | 시간순 데이터 구간 | 70% train / 15% validation / 15% test | Split |
| `eligible_target_5d` | 5일 Target이 split 경계 안에 있는지 | Target 날짜 ≤ 해당 split 마지막 날짜 | Filter |
| `eligible_target_20d` | 20일 Target이 split 경계 안에 있는지 | Target 날짜 ≤ 해당 split 마지막 날짜 | Filter |

### 누출 방지

`target_*`, `target_date_*`, `eligible_target_*`, `split`은 학습 입력 X에 포함하지 않는다. `eligible_target_*`는 학습 행을 선택할 때만 사용한다.

## market_index_daily

| 컬럼 | 정의 | 계산 |
|---|---|---|
| `trade_date` | 지수 거래일 | Raw `basDt` |
| `index_name` | 지수명 | Raw `idxNm` |
| `close_index` | 지수 종가 | Raw `clpr` |
| `index_return_1d` | 지수 일간 수익률 | `index_t / index_t-1 - 1` |
| `index_momentum_20d` | 지수 20일 모멘텀 | `index_t / index_t-20 - 1` |
| `index_sma_20d` | 지수 20일 이동평균 | 최근 20거래일 평균 |
| `index_above_sma_20d` | 지수가 20일선 위인지 | `close_index > index_sma_20d` |
| `index_volatility_20d` | 지수 20일 연환산 변동성 | 최근 20일 수익률 표준편차 × √252 |

## financial_snapshot

현재는 research-only다.

| 컬럼 | 정의 | 계산 |
|---|---|---|
| `corporation_number` | 법인등록번호 | Raw `crno`, 문자열 보존 |
| `base_date` | 재무 데이터 기준일 | Raw `basDt` |
| `business_year` | 사업연도 | Raw `bizYear` |
| `financial_division_code` | 재무 구분 코드 | Raw `fnclDcd`, 문자열 보존 |
| `sales` | 매출액 | Raw `enpSaleAmt` |
| `operating_profit` | 영업이익 | Raw `enpBzopPft` |
| `net_income` | 당기순이익 | Raw `enpCrtmNpf` |
| `total_assets` | 자산총계 | Raw `enpTastAmt` |
| `total_liabilities` | 부채총계 | Raw `enpTdbtAmt` |
| `total_equity` | 자본총계 | Raw `enpTcptAmt` |
| `reported_debt_ratio_pct` | 원 API 보고 부채비율(%) | Raw `fnclDebtRto` |
| `debt_to_equity` | 부채/자본 배수 | `total_liabilities / total_equity` |
| `debt_ratio_pct_calculated` | 계산 부채비율(%) | `debt_to_equity × 100` |
| `roa` | 총자산이익률 근사 | `net_income / total_assets` |
| `roe` | 자기자본이익률 근사 | `net_income / total_equity` |
| `operating_margin` | 영업이익률 | `operating_profit / sales` |
| `net_margin` | 순이익률 | `net_income / sales` |
| `point_in_time_join_ready` | 시점 안전 JOIN 준비 여부 | 현재 항상 `false` |

### 재무 Feature 해석 주의

`ROA`, `ROE`는 평균자산/평균자본이 아니라 해당 Snapshot 총계로 계산한 단순 근사값이다. 모델 연구 시 이 정의를 그대로 기록하고, 필요하면 평균잔액 기반 정의를 v2에서 추가한다.

## financial_company_year_latest

| 컬럼 | 정의 |
|---|---|
| `sales_growth_yoy` | 동일 법인·재무구분의 직전 사업연도 대비 매출 성장률 |
| `operating_profit_growth_yoy` | 직전 사업연도 대비 영업이익 성장률 |
| `net_income_growth_yoy` | 직전 사업연도 대비 순이익 성장률 |
| `research_only` | 현재 항상 `true` |
| `point_in_time_join_ready` | 현재 항상 `false` |

이 Dataset은 전체 관측값에서 사업연도별 latest Snapshot을 선택하므로 공시 availability date가 없는 상태에서 역사적 가격과 JOIN하지 않는다.
