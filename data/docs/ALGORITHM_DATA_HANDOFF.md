# Algorithm OHLCV v2 전달 가이드

## 1. 전달 대상

Algorithm ver.0/ver.1/ver.1.1 담당자는 Azure Blob `features` 컨테이너의 아래 Dataset을 사용한다.

```text
algorithm_ohlcv/version=v2/year=YYYY/month=MM/part-00000.parquet
```

Manifest:

```text
_manifests/algorithm_ohlcv/version=v2/manifest.json
```

`v1`은 직접 입력 Feature에서 일중 가격이 형성되지 않은 패턴의 181,224행을 출력에서 제외한 과거 버전이다. 원천 KRX Raw와 `model_stock_daily/version=v2`를 삭제한 것은 아니다. 신규 연동은 시계열 행과 상태를 보존하는 `v2`만 사용하며, 외부 v1 소비 여부는 저장소만으로 확인할 수 없어 v1 산출물은 deprecated 상태로 보존한다.

데이터 계보와 값의 성격:

```text
KRX 공식 API
  → canonical Raw JSONL.gz
  → krx_stock_price_daily Processed
  → model_stock_daily/version=v2 Feature
  → algorithm_ohlcv/version=v2
```

- OHLCV: `model_stock_daily/version=v2`에서 계승한 저장값이다. Algorithm Dataset 생성 단계에서는 추가 보간·대체하지 않는다.
- `is_tradable`, `data_status`, `quality_reason`: Data 계층에서 가격 패턴으로 계산한 파생값이다.
- v2 생성 단계가 KRX API Raw를 직접 다시 읽거나 공식 거래상태 필드를 결합하지는 않는다.

## 2. 전달 계약

자연키:

```text
symbol + Date
```

컬럼 순서:

| 컬럼             | 타입          | 역할                                          |
| ---------------- | ------------- | --------------------------------------------- |
| `symbol`         | string        | 종목 식별자, 선행 0 보존                      |
| `Date`           | timestamp[ns] | 거래 관측일                                   |
| `Open`           | double        | 입력 Feature에서 계승한 시가                  |
| `High`           | double        | 입력 Feature에서 계승한 고가                  |
| `Low`            | double        | 입력 Feature에서 계승한 저가                  |
| `Close`          | double        | 입력 Feature에서 계승한 종가                  |
| `Volume`         | int64         | 입력 Feature에서 계승한 거래량                |
| `is_tradable`    | bool          | 품질 규칙으로 계산한 신규 주문·체결 허용 flag |
| `data_status`    | string        | `TRADABLE` 또는 `NOT_TRADABLE`                |
| `quality_reason` | string        | 거래 불가 또는 품질 사유. 정상행은 빈 문자열  |

Algorithm 입력 컬럼은 다음 6개다.

```text
Date, Open, High, Low, Close, Volume
```

`symbol`, `is_tradable`, `data_status`, `quality_reason`은 입력 전 종목 분리와 실행 제어에 사용한다.

## 3. 반드시 지킬 처리 규칙

1. `symbol`을 숫자로 변환하지 않는다. `005930`의 선행 0을 유지한다.
2. 종목별로 `Date` 오름차순 정렬한다.
3. `is_tradable=false` 행을 전체 Dataset에서 삭제하지 않는다.
4. `is_tradable=false` 행에서는 신규 주문·체결을 만들지 않는다.
5. 0인 OHLC를 전일 종가나 당일 종가로 대체하지 않는다.
6. 거래 가능일 기반 기술지표가 필요하면 계산할 때만 `is_tradable=true`를 필터링한다.
7. 달력상 상태 전이·거래정지 기간 분석에는 전체 행을 유지한다.
8. `quality_reason=NO_INTRADAY_PRICE`를 법적·공식 거래정지로 단정하지 않는다. 이는 직접 입력 Feature에서 `Open/High/Low`가 모두 0인 패턴을 Data 계층이 보수적으로 분류한 코드다.
9. Target 컬럼은 Dataset에 포함되지 않는다.
10. 수정주가가 아니므로 기업행동 영향을 별도로 고려한다.

## 4. 권장 연결 패턴

```python
import pandas as pd

panel = pd.concat(monthly_frames, ignore_index=True)
stock_calendar = panel.loc[panel["symbol"] == "005930"].sort_values("Date")

tradable_bars = stock_calendar.loc[
    stock_calendar["is_tradable"],
    ["Date", "Open", "High", "Low", "Close", "Volume"],
].reset_index(drop=True)
```

- `stock_calendar`: 날짜와 거래 가능 상태를 유지하는 전체 시계열
- `tradable_bars`: OHLCV 지표 계산과 주문 후보 생성용 시계열

백테스트 엔진이 전체 Calendar를 순회한다면 `stock_calendar`를 사용하고 `is_tradable=false`일 때 주문을 건너뛴다. 엔진이 유효 Bar만 받는 구조라면 `tradable_bars`를 전달하되, 보유 중 거래 불가 기간의 평가·청산 정책을 별도로 구현해야 한다.

## 5. 현재 v2 규모

| 항목              |                      값 |
| ----------------- | ----------------------: |
| 기간              | 2018-01-02 ~ 2026-08-25 |
| 월별 Parquet      |                   104개 |
| 전체 행           |               5,238,800 |
| 거래 가능 행      |               5,057,576 |
| 거래 불가 상태 행 |                 181,224 |
| 종목              |                   3,104 |
| 파일 총크기       |        64,917,014 bytes |

현재 거래 불가 상태 사유는 모두 `NO_INTRADAY_PRICE`다. 이 값은 KRX 공식 거래정지 코드가 아니라 Algorithm의 신규 주문을 보수적으로 차단하기 위한 품질 분류다. 공식 원인 구분에는 별도의 거래정지·시장조치 데이터 또는 Raw 상태 필드 결합이 필요하다.

- 해당 행: 181,224건
- 영향 종목: 1,316개
- 종가 양수: 181,224건
- 거래량 0: 181,213건
- 거래량 양수: 11건

거래량 양수 11건도 일중 OHLC가 없어 `is_tradable=false`로 분류한다.

## 6. 전달 전후 검증

Data 담당자와 Algorithm 담당자 모두 아래 명령으로 동일 산출물을 검증할 수 있다.

```bash
docker compose --profile data run --rm --no-deps data \
  python -m scripts.validate_algorithm_dataset --version 2
```

성공 조건:

- Manifest version과 요청 version 일치
- Manifest에 선언된 104개 파일 존재
- 모든 파일의 컬럼 순서 일치
- `symbol + Date` null·중복 없음
- `is_tradable`과 `data_status` 일치
- 거래 가능행의 `quality_reason`은 빈 문자열
- 거래 불가행의 `quality_reason`은 비어 있지 않음
- 파일 집계와 Manifest 행 수·종목 수·사유별 수 일치

## 7. 담당자 연결 체크리스트

### Data 담당자

- [x] `v2` Parquet 104개 생성
- [x] v1과 다른 경로로 저장해 기존 산출물 보존
- [x] 상태 컬럼과 품질 사유 추가
- [x] 직접 입력 Feature 5,238,800행 전부 보존
- [x] Manifest 생성
- [x] 재현 스크립트와 검증 CLI 제공
- [x] 단위 테스트 제공

### Algorithm 담당자

- [ ] Dataset 경로를 `version=v2`로 고정
- [ ] `symbol` 문자열 타입 유지
- [ ] 월 파티션 로더 구현
- [ ] `is_tradable=false` 신규 주문·체결 차단
- [ ] 거래 불가 기간의 보유 포지션 평가 정책 결정
- [ ] 지표 계산 시 전체 Calendar 또는 거래 가능 Bar 기준을 명시
- [ ] 313행 최소 이력 조건을 거래 가능행 기준으로 재검증
- [ ] 기업행동 미조정 가격 위험 반영
- [ ] 검증 CLI 성공 결과를 PR에 첨부
- [ ] `NO_INTRADAY_PRICE`를 공식 거래정지 사유로 표시하지 않음

## 8. 변경 요청 경계

다음 변경은 Data 담당자와 합의 후 새 Dataset version으로 처리한다.

- 상태 컬럼 삭제 또는 의미 변경
- 거래 불가행 삭제·보간 정책 도입
- 자연키 변경
- 기업행동 조정 OHLCV 도입
- KRX 거래일 Calendar reindex
- 보통주·ETF 등 Universe 필터 내장

기존 `v2` 경로의 의미를 조용히 변경하지 않는다.
