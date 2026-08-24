# Portfolio Feature 평가와 판단 이력 명세

## 원칙

화면의 “AI 평가”는 생성형 모델이 만든 임의 점수가 아니라 `stock-feature-v1` 고정 산식이다.
입력값, 기준일, 산식 버전을 응답에 포함하며 표본이나 재무값이 부족한 축은 0점이 아니라
`UNAVAILABLE/null`로 반환한다. 점수는 투자 권유나 미래 수익 예측이 아니다.

## 종목별 5축 산식

공통 점수 범위는 0~100이며 선형 구간 밖은 경계값으로 제한한다.

| 축 | 실제 입력 | `stock-feature-v1` 산식 | unavailable 조건 |
| --- | --- | --- | --- |
| 안정성 | 최근 180일 KRX 종가 수익률 | 일별 표준편차를 연환산하고 변동성 10%=100, 60%=0으로 역선형 scaling | 수익률 40개 미만 |
| 재무 건전성 | 최신 FY OpenDART 자산·자본·영업현금흐름 | 자본/자산(0~70%) 점수와 영업현금흐름/자산(-5~10%) 점수의 평균 | 필수 값 누락 또는 자산<=0 |
| 성장성 | 최근 2개 FY 매출·영업이익 | 각 YoY -20%=0, +20%=100 점수의 평균 | 2개 연도 미존재, 값 누락, 이전 값<=0 |
| 방어력 | 종목·KOSPI 공통 일별 수익률 | KOSPI 하락일 하락 포착률 -50%=100, 200%=0 역선형 scaling | 공통 하락일 10개 미만 |
| 분산 기여 | 해당 종목과 나머지 보유종목 시가가중 수익률 | 상관계수 -1=100, +1=0 역선형 scaling | 공통 수익률 40개 미만 또는 변화 없음 |

재무제표는 같은 연도에 CFS가 있으면 OFS보다 우선한다. 분산 기여 계산에서 특정 일자의
다른 보유종목 가격 커버리지가 전체 시가의 70% 미만이면 그 일자를 제외한다. 현재 전략의
최신 단일 `strategy_target_weights.effective_from` 버전만 목표 비중 설명에 사용한다.

API: `GET /api/v1/portfolio/stock-evaluation?account_id=&stock_code=`

## 리밸런싱 판단 이력

`POST /api/v1/portfolio/decisions`는 클라이언트가 금액이나 비중을 보내지 않는다. Backend가
요청 시점의 실제 포트폴리오를 다시 평가해 유효한 제안을 찾고 다음 값을 저장한다.

- 전략 ID, 종목, BUY/SELL
- 현재·목표·차이 비중과 추천 금액
- 사용자 선택 `ACCEPTED` 또는 `HELD`
- 가장 최근 일별 스냅샷의 날짜와 총자산
- 계좌 범위 idempotency key

결과는 기준일보다 이후의 최신 `portfolio_snapshots.total_assets`와 비교한 실제 계좌 수익률만
계산한다. 종목 제안을 따랐을 경우의 반사실 수익률이나 인과 효과는 신뢰성 있게 재구성할 수
없으므로 만들지 않는다. 기준 스냅샷 또는 이후 스냅샷이 없으면 결과는 null이다. 최근 6개월
요약의 수락·보류 평균은 각 선택 이후 실제 계좌 수익률의 단순 평균이며 기간 길이가 서로
다를 수 있으므로 투자 성과 우열로 해석하지 않는다.

API:

- `POST /api/v1/portfolio/decisions`
- `GET /api/v1/portfolio/decisions?account_id=`

## 출처와 기준시각

- 가격·KOSPI: PostgreSQL `market_stock_prices`, `market_indices`에 적재된 KRX 일별 데이터
- 재무: PostgreSQL `company_financials`에 적재된 OpenDART FY 데이터
- 보유·목표·판단: `positions`, `strategy_target_weights`, `rebalancing_decisions`
- 판단 결과: 평일 장 마감 후 생성되는 `portfolio_snapshots`
