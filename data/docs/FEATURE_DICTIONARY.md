# Feature Dictionary v1

## 공통 horizon 해석

현재 가격/지수 Feature의 `rolling(N)`, `shift(N)`은 **각 종목/지수의 정렬된 N번째 관측치**를 기준으로 한다.

따라서 문서의 `5d`, `20d`, `60d`, `120d`는 일반적으로 거래일 시계열과 대응하지만, 거래정지나 관측 누락이 있는 종목에서는 독립적인 KRX 시장 N거래일 calendar와 정확히 같지 않을 수 있다.

## model_stock_daily

| 컬럼 | 정의 | 계산 기준 | 입력/Target |
|---|---|---|---|
| `stock_code` | 종목 단축코드 | Raw `srtnCd`, 문자열 보존 | Key |
| `trade_date` | 해당 종목 가격 관측일 | Raw `basDt` | Key |
| `close_price` | 종가 | Raw `clpr` | 원본 Feature 후보 |
| `open_price` | 시가 | Raw `mkp` | 원본 Feature 후보 |
| `high_price` | 고가 | Raw `hipr` | 원본 Feature 후보 |
| `low_price` | 저가 | Raw `lopr` | 원본 Feature 후보 |
| `volume` | 거래량 | Raw `trqu` | 원본 Feature 후보 |
| `trading_value` | 거래대금 | Raw `trPrc` | 원본 Feature 후보 |
| `market_cap` | 시가총액 | Raw `mrktTotAmt` | 원본 Feature 후보 |
| `listed_shares` | 상장주식수 | Raw `lstgStCnt` | 원본 Feature 후보 |
| `return_1d` | 직전 관측치 대비 수익률 | `close_t / close_t-1 - 1` | Feature |
| `momentum_5d` | 5번째 이전 관측치 대비 모멘텀 | `close_t / close_t-5obs - 1` | Feature |
| `momentum_20d` | 20번째 이전 관측치 대비 모멘텀 | `close_t / close_t-20obs - 1` | Feature |
| `momentum_60d` | 60번째 이전 관측치 대비 모멘텀 | `close_t / close_t-60obs - 1` | Feature |
| `momentum_120d` | 120번째 이전 관측치 대비 모멘텀 | `close_t / close_t-120obs - 1` | Feature |
| `sma_5d` | 최근 5개 관측치 단순이동평균 | 현재 포함 최근 5개 종가 평균 | Feature |
| `sma_20d` | 최근 20개 관측치 단순이동평균 | 최근 20개 종가 평균 | Feature |
| `sma_60d` | 최근 60개 관측치 단순이동평균 | 최근 60개 종가 평균 | Feature |
| `price_to_sma_20d` | 20관측치 평균 대비 가격 괴리 | `close / sma_20d - 1` | Feature |
| `volatility_20d` | 최근 20개 관측치 수익률의 연환산 표준편차 | std(`return_1d`) × √252 | Feature |
| `volatility_60d` | 최근 60개 관측치 수익률의 연환산 표준편차 | std(`return_1d`) × √252 | Feature |
| `volume_sma_20d` | 최근 20개 관측치 평균 거래량 | rolling mean | Feature |
| `volume_ratio_20d` | 평균 대비 거래량 | `volume / volume_sma_20d` | Feature |
| `trading_value_sma_20d` | 최근 20개 관측치 평균 거래대금 | rolling mean | Feature |
| `log_market_cap` | 로그 시가총액 | `ln(market_cap)`, 양수만 | Feature |
| `history_120d_ready` | 120번째 이전 관측치 확보 여부 | `momentum_120d` 존재 여부 | Filter |
| `target_return_5d` | 5번째 미래 관측치 수익률 | `close_t+5obs / close_t - 1` | Target |
| `target_return_20d` | 20번째 미래 관측치 수익률 | `close_t+20obs / close_t - 1` | Target |
| `target_up_20d` | 20번째 미래 관측치 가격 상승 여부 | `target_return_20d > 0` | Target |
| `target_date_5d` | 5번째 미래 관측치의 실제 날짜 | 종목별 `shift(-5)` 날짜 | Label metadata |
| `target_date_20d` | 20번째 미래 관측치의 실제 날짜 | 종목별 `shift(-20)` 날짜 | Label metadata |
| `split` | 시간순 데이터 구간 | 전체 관측 거래일 70% train / 15% validation / 15% test | Split |
| `eligible_target_5d` | 5관측치 Target이 split 경계 안에 있는지 | Target 날짜 ≤ 해당 split 마지막 날짜 | Filter |
| `eligible_target_20d` | 20관측치 Target이 split 경계 안에 있는지 | Target 날짜 ≤ 해당 split 마지막 날짜 | Filter |

### 누출 방지

`target_*`, `target_date_*`, `eligible_target_*`, `split`은 학습 입력 X에 포함하지 않는다. `eligible_target_*`는 학습 행 필터에만 사용한다.

### 가격 조정 주의

현재 Feature는 원천 `close_price` 기준이다. 수정주가/Corporate Action adjustment가 별도로 완성되기 전에는 액면분할·권리락 등이 장기 수익률/변동성에 영향을 줄 수 있다.

## market_index_daily

| 컬럼 | 정의 | 계산 |
|---|---|---|
| `trade_date` | 지수 관측일 | Raw `basDt` |
| `index_name` | 지수명 | Raw `idxNm` |
| `close_index` | 지수 종가 | Raw `clpr` |
| `index_return_1d` | 직전 관측치 대비 지수 수익률 | `index_t / index_t-1 - 1` |
| `index_momentum_20d` | 20번째 이전 관측치 대비 모멘텀 | `index_t / index_t-20obs - 1` |
| `index_sma_20d` | 최근 20개 지수 관측치 평균 | rolling mean |
| `index_above_sma_20d` | 현재 지수가 20관측치 평균 위인지 | `close_index > index_sma_20d` |
| `index_volatility_20d` | 최근 20개 관측치 수익률의 연환산 변동성 | rolling std × √252 |

## financial_snapshot

현재는 `research_only_until_availability_date`다.

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

`ROA`, `ROE`는 평균자산/평균자본이 아니라 해당 Snapshot 총계로 계산한 단순 근사값이다. `base_date`는 실제 시장 공개 시각이 아니다.

## financial_company_year_latest

| 컬럼 | 정의 |
|---|---|
| `sales_growth_yoy` | 동일 법인·재무구분의 직전 사업연도 대비 매출 성장률 |
| `operating_profit_growth_yoy` | 직전 사업연도 대비 영업이익 성장률 |
| `net_income_growth_yoy` | 직전 사업연도 대비 순이익 성장률 |
| `research_only` | 현재 항상 `true` |
| `point_in_time_join_ready` | 현재 항상 `false` |

이 Dataset은 전체 관측값에서 사업연도별 latest Snapshot을 선택하므로 실제 공시 availability date가 없는 상태에서 역사적 가격과 JOIN하지 않는다.
## ECOS `macro_daily` v1

| column | 정의 |
|---|---|
| `date` | 환율·국고채 ECOS 관측일 합집합 |
| `base_rate` | 해당 일자에 가용한 최근 기준금리(연%) |
| `base_rate_change` | 직전 거래일 대비 기준금리 변화 |
| `usd_krw` | 원/미국달러 매매기준율 |
| `usd_krw_return_{1,5,20}d` | 환율 단순 수익률 |
| `usd_krw_volatility_20d` | 1일 수익률 20일 표준편차 × √252 |
| `cpi` | 해당 일자에 가용한 최근 CPI(2020=100) |
| `cpi_mom`, `cpi_yoy` | 월간 원자료에서 계산한 전월비·전년동월비 |
| `treasury_3y`, `treasury_10y` | 국고채 3년·10년 수익률(연%) |
| `treasury_3y_change`, `treasury_10y_change` | 직전 거래일 대비 금리 변화 |
| `yield_spread_10y_3y` | 10년 수익률 - 3년 수익률 |

결측은 임의의 0으로 채우지 않는다. rolling feature의 초기 구간과 CPI 가용일 이전 값은
의도적으로 null이며, 학습자는 해당 feature별 warm-up 정책을 적용해야 한다.
