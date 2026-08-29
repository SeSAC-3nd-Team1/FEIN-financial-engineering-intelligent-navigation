# Risk-adjusted Momentum v2

`risk-adjusted-momentum-v2`는 공개된 기관형 Momentum Factor의 일반 원칙을 FE!N의
한국 주식 데이터 계약에 적용한 독립 모델이다. 특정 기관의 지수나 상품을 1:1 복제한다고
주장하지 않으며 기존 `price-momentum-v1` 코드와 artifact는 변경하지 않는다.

## Point-in-time 신호

종목별 거래 관측치를 날짜순으로 정렬하고 `S=21`, `M6=126`, `M12=252`로 둔다.

- `return_6m_skip1m(t) = close(t-S) / close(t-S-M6) - 1`
- `return_12m_skip1m(t) = close(t-S) / close(t-S-M12) - 1`
- `volatility_3y_weekly(t) = std(완료된 주말 종가 수익률 156개) × sqrt(52)`
- `RAM_h = (return_h - risk_free_return_h) / volatility_3y_weekly`

현재 Azure `macro_daily`에는 한국은행 기준금리와 국고채 3년/10년물은 있지만 KOFR 등
적절한 단기 무위험금리가 없다. 기준금리나 3년물을 임의로 대용하지 않으며 기본
`risk_free_policy`는 `neutral_no_short_rate_available`이다. 따라서 현재 `RAM`의 분자는
원 momentum이다. 향후 실제 point-in-time 연율 컬럼을 명시적으로 전달할 때만 기간 수익률로
환산해 차감하는 확장 지점을 제공한다.

각 거래일의 투자 가능 universe 안에서 6M/12M RAM을 각각 population z-score로 바꾸고
`[-3, 3]`으로 winsorize한다. `combined_z_raw = 0.5*z6 + 0.5*z12`를 다시 z-score 및
winsorize한 뒤 순서를 보존하는 양수 percentile `momentum_score`로 변환한다.

## Universe, selection, weighting

Azure `algorithm_ohlcv.is_tradable`과 기존 `StockRiskConfig`의 가격, 시가총액, 20일 거래대금,
60일 변동성, 이상 거래량, 120일 history 검사를 재사용한다. 여기에 v2 장기 history,
양의 3년 주간 변동성, corporate-action safety를 요구한다. 이 중 유효 시가총액 상위 100개를
cross-section universe로 사용한다.

상위 20%를 선택하되 Backend의 추천 최대 20개 계약을 지킨다. 주식 95%와 종목당 5% cap을
동시에 만족하려면 최소 19개가 필요하므로 선택/양의 비중 종목이 19개 미만이면 fail-closed한다.

`raw_weight_i = market_cap_i * momentum_score_i`를 정규화하고 5%를 넘는 비중을 고정한 뒤
잔여 종목에 반복 재분배한다. 마지막으로 소수점 8자리 `Decimal` 단위로 내림하고 잔여 quantum을
순위순으로 배분한다. 직렬화 후 합계가 정확히 `0.95`가 아니면 artifact를 발행하지 않는다.

## Corporate action 정책

현재 `model_stock_daily.close_price`는 수정주가가 아니고 별도 수정계수나 corporate-action
이벤트도 없다. v2는 `listed_shares`가 10%를 초과해 변할 때 가격이 연속적이면 원가격을 유지하고,
가격도 단절됐지만 주식수 비율이 일반적인 split/reverse-split 비율의 1% 안이고
`가격비율 × 주식수비율`로 계산한 조정 수익률이 KRX 일일 가격제한폭 30% 안이면 split형 이벤트로 판정한다.
이때 이벤트 당일부터 주식수 비율을 누적한 forward-adjusted 가격을
사용하므로 미래 기업행위가 과거 신호에 반영되지 않는다. 결측·비양수 또는 조정 후에도 30%를 넘는
설명 불가능한 단절은 fail-closed한다. 합병 상장폐지처럼 현금정산/교환비율이 필요한 이벤트도
관련 데이터가 없으면 전체기간 백테스트를 중단한다.

## Artifact와 서비스 계약

기본 v2 경로는 `/model-artifacts/risk-adjusted-momentum-v2.json`이며 v1 기본 경로를 덮어쓰지
않는다. 검증 후 `MODEL_RECOMMENDATION_SNAPSHOT_PATH`가 이 파일을 가리키면 Backend 변경 없이
사용할 수 있다. Snapshot 및 recommendation 필드는 기존 계약과 동일하다. `market_regime=neutral`은
계약 호환용 필드이고 v2가 regime을 예측했다는 의미가 아니다.

```bash
python -m inference.generate_risk_adjusted_momentum \
  --model-version 2 --algorithm-version 2 --master-version 1 \
  --output /model-artifacts/risk-adjusted-momentum-v2.json
```

## Backtest

`evaluation.run_momentum_comparison`은 동일 Azure 주식 history에서 v1, v2를 공통 분기말에
리밸런싱하고 KOSPI와 비교한다. 의사결정일 종가까지의 feature만 사용하며 새 목표는 다음 거래일
수익률부터 적용한다. forward return은 평가에만 쓰인다. cumulative return, CAGR, MDD,
연환산 변동성, Sharpe, 평균/총 one-way turnover를 출력한다. 거래비용 기본값은 0이며
`--transaction-cost-bps`를 명시했을 때만 turnover에 비례해 반영한다.

```bash
python -m evaluation.run_momentum_comparison \
  --model-version 2 --algorithm-version 2 --master-version 1 \
  --market-version 2 --benchmark-name 코스피 --start-date 2023-04-01 \
  --end-date 2025-12-12 \
  --transaction-cost-bps 0
```

## 남은 한계

- 수정주가가 없어 corporate action 주변 종목/백테스트를 제외 또는 중단한다.
- `security_master_latest`는 표시 이름에만 사용한다. 가격 관측과 당일 `is_tradable`을 쓰지만
  완전한 역사적 security master가 없어 survivorship bias가 남을 수 있다.
- 거래대금 threshold 기본값은 기존 설정을 따르며 시장 충격/체결 가능성을 모델링하지 않는다.
- 거래비용은 사용자가 명시한 선형 bps이며 세금, bid-ask spread, market impact를 포함하지 않는다.
- 분기 리밸런싱과 turnover 측정은 구현했지만 보유 종목 buffer는 향후 확장 항목이다.

## 실제 Azure 검증 결과

전체 가용기간 실행은 `000060`의 2023-02-20 이후 가격 소멸처럼 합병/상장폐지 정산정보가
필요한 보유 이벤트에서 fail-closed한다. 비교 가능한 공통 구간을 명시적으로
`2023-04-01 ~ 2025-12-12`로 설정하면 첫 리밸런싱 다음 거래일인 2023-07-03부터
597거래일, 분기 리밸런싱 10회의 결과를 얻는다.

| Metric | price-momentum-v1 | risk-adjusted-momentum-v2 | KOSPI |
|---|---:|---:|---:|
| Cumulative Return | 139.25% | 127.27% | 62.51% |
| CAGR | 44.52% | 41.42% | 22.75% |
| MDD | -44.13% | -25.81% | -20.67% |
| Annualized Volatility | 40.95% | 26.88% | 19.99% |
| Sharpe | 1.104 | 1.424 | 1.126 |
| Average Turnover | 72.20% | 50.87% | 0.00% |

동일 구간에 리밸런싱 one-way turnover당 10bp를 적용하면 v1/v2 CAGR은 각각
44.08%/41.11%, Sharpe는 1.097/1.416이다. 이 값은 특정 기간의 과거 실험 결과이며
미래 성과를 보장하지 않는다.
