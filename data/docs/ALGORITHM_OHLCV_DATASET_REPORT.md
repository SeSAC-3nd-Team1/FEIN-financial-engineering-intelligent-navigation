# Algorithm OHLCV Dataset 보고서

## 1. 목적

이 문서는 `Algorithm ver.0`, `ver.1`, `ver.1.1`에 전달하는 일별 OHLCV Dataset의 범위, 스키마, 품질 상태, 거래 가능 여부, 사용 제약과 재현 방법을 기록한다.

Dataset 파일은 Git에 저장하지 않는다. Azure Blob Storage에 월별 Parquet으로 저장하고, Git에는 생성 코드와 이 보고서만 관리한다.

용어를 다음처럼 구분한다.

- **제공기관 원천**: KRX 공식 API가 제공한 일별 OHLCV 응답
- **직접 입력 Dataset**: KRX 응답을 정규화·Feature 처리한 `features/model_stock_daily/version=v2/`
- **v2 저장값**: 직접 입력 Dataset의 `stock_code`, `trade_date`, OHLCV를 이름·타입만 변환한 값
- **v2 파생값**: Data 계층이 품질 규칙으로 계산한 `is_tradable`, `data_status`, `quality_reason`

따라서 이 보고서에서 OHLCV의 “원천값 보존”은 KRX API 응답을 v2 생성기가 직접 다시 읽었다는 뜻이 아니라, **직접 입력 Feature에 저장된 OHLCV를 추가 보간·대체·삭제하지 않았다는 뜻**이다. 제공기관 원문과 최종 v2 값의 byte-level 동일성은 이번 감사 범위가 아니며, 직접 입력 Feature부터 v2 출력까지의 값 보존을 검증했다.

## 2. Dataset 식별 정보

| 항목              | 값                                                             |
| ----------------- | -------------------------------------------------------------- |
| Dataset           | `algorithm_ohlcv`                                              |
| Dataset version   | `v2`                                                           |
| 상태              | 생성·검증 완료, Algorithm 전달 대상                            |
| 제공기관 원천     | 한국거래소 KRX 공식 API                                        |
| 직접 입력 Dataset | `features/model_stock_daily/version=v2/`                       |
| 입력 계보         | KRX API → Raw → 정규화/Feature → Algorithm OHLCV v2            |
| 출력 경로         | `features/algorithm_ohlcv/version=v2/`                         |
| Manifest          | `features/_manifests/algorithm_ohlcv/version=v2/manifest.json` |
| 파일 형식         | Apache Parquet                                                 |
| 압축              | Zstandard                                                      |
| 파티션            | `year=YYYY/month=MM`                                           |
| 생성 시각         | 2026-08-26 07:40:56 UTC                                        |
| 출력 파일 수      | 104개                                                          |
| 출력 파일 총크기  | 64,917,014 bytes, 약 61.91 MiB                                 |

월별 파일 경로:

```text
features/algorithm_ohlcv/version=v2/year=YYYY/month=MM/part-00000.parquet
```

## 3. 용도와 데이터 단위

적합한 용도:

- Algorithm ver.0/ver.1/ver.1.1 입력
- 종목별 일봉 기술적 지표 계산
- 종목별 과거 백테스트
- OHLCV 기반 전략 연구

Dataset에 포함하지 않은 항목:

- 학습 Target 및 미래 수익률
- 사전 계산된 기술적 지표
- 시장지수, 거시경제, 재무, 수급 Feature
- 종목명 및 업종
- 기업행동 조정계수

데이터 단위는 **종목 × 거래 관측일**이고 자연키는 `symbol + Date`다. 전체 파일은 여러 종목을 포함한 패널 데이터이므로 실제 Algorithm 호출 전 `symbol`로 한 종목씩 분리해야 한다.

## 4. 컬럼 명세

| 컬럼             | Parquet 타입  | 설명                                    | Algorithm 입력 | 품질 조건                      |
| ---------------- | ------------- | --------------------------------------- | -------------- | ------------------------------ |
| `symbol`         | string        | KRX 종목 단축코드                       | 분리·식별용    | null 불가, 문자열 유지         |
| `Date`           | timestamp[ns] | 가격 관측 거래일                        | 필수           | null 불가                      |
| `Open`           | double        | 입력 Feature에서 계승한 시가            | 필수           | 거래 불가 상태에서 0 가능      |
| `High`           | double        | 입력 Feature에서 계승한 고가            | 필수           | 거래 불가 상태에서 0 가능      |
| `Low`            | double        | 입력 Feature에서 계승한 저가            | 필수           | 거래 불가 상태에서 0 가능      |
| `Close`          | double        | 입력 Feature에서 계승한 종가            | 필수           | 현재 관측 범위에서 양수        |
| `Volume`         | int64         | 입력 Feature에서 계승한 거래량          | 필수           | 0 이상                         |
| `is_tradable`    | bool          | 품질 규칙 기반 Algorithm 거래 허용 flag | 실행 제어      | `true` 또는 `false`            |
| `data_status`    | string        | 상태 문자열                             | 실행 제어      | `TRADABLE` 또는 `NOT_TRADABLE` |
| `quality_reason` | string        | 거래 불가·품질 사유                     | 진단           | 정상행은 빈 문자열             |

### OHLCV 계보와 변환

| KRX API 필드 | Processed/Feature 컬럼 | Algorithm v2 컬럼 | v2 생성 단계 처리         |
| ------------ | ---------------------- | ----------------- | ------------------------- |
| `ISU_CD`     | `stock_code`           | `symbol`          | 문자열 변환, 선행 0 보존  |
| `BAS_DD`     | `trade_date`           | `Date`            | timestamp 변환            |
| `TDD_OPNPRC` | `open_price`           | `Open`            | 숫자형 변환, 값 보간 없음 |
| `TDD_HGPRC`  | `high_price`           | `High`            | 숫자형 변환, 값 보간 없음 |
| `TDD_LWPRC`  | `low_price`            | `Low`             | 숫자형 변환, 값 보간 없음 |
| `TDD_CLSPRC` | `close_price`          | `Close`           | 숫자형 변환, 값 보간 없음 |
| `ACC_TRDVOL` | `volume`               | `Volume`          | 숫자형 변환, 값 보간 없음 |

KRX Raw는 `stock_price_rows`에서 canonical Processed로 정규화되고, `compute_stock_features`는 같은 OHLCV 컬럼을 유지한 채 기술지표와 Target을 추가한다. Algorithm Dataset 생성기는 Feature 전체가 아니라 위 7개 직접 입력 컬럼만 선택한다. 상태 3개 컬럼은 이 단계에서 새로 계산하므로 KRX 제공값이 아니다.

`symbol`은 숫자가 아니다. 삼성전자 `005930`처럼 선행 0을 보존해야 한다. Algorithm에는 다음 순서의 6개 컬럼을 전달한다.

```text
Date, Open, High, Low, Close, Volume
```

## 5. 기간과 규모

| 지표                 |                  값 |
| -------------------- | ------------------: |
| 최초 관측일          |          2018-01-02 |
| 최종 관측일          |          2026-08-25 |
| 고유 거래 관측일     |             2,121일 |
| 종목 수              |             3,104개 |
| 직접 입력 Feature 행 |         5,238,800건 |
| 최종 보존 행         |         5,238,800건 |
| 거래 가능 행         | 5,057,576건, 96.54% |
| 거래 불가 상태 행    |    181,224건, 3.46% |
| 품질 검증 탈락 행    |                 0건 |
| 행 보존율            |             100.00% |

### 연도별 최종 행 수

| 연도 |   행 수 |
| ---: | ------: |
| 2018 | 528,603 |
| 2019 | 552,278 |
| 2020 | 575,815 |
| 2021 | 598,678 |
| 2022 | 612,177 |
| 2023 | 631,753 |
| 2024 | 651,573 |
| 2025 | 660,723 |
| 2026 | 427,200 |

2026년은 8월 25일까지의 부분 연도다. 월별 행 수는 거래일 수와 해당 시점의 상장·관측 종목 수에 따라 달라진다.

## 6. 결측치 현황

### 직접 입력 Feature 필수 컬럼 결측

| 컬럼          | 결측 행 |
| ------------- | ------: |
| `stock_code`  |       0 |
| `trade_date`  |       0 |
| `open_price`  |       0 |
| `high_price`  |       0 |
| `low_price`   |       0 |
| `close_price` |       0 |
| `volume`      |       0 |

직접 입력 Feature 5,238,800건에서 Algorithm 필수 필드의 실제 null/NaN은 발견되지 않았다. 최종 Dataset도 생성 규칙상 핵심 컬럼 결측이 없다. 이 수치는 KRX API 원문을 별도로 재집계한 값이 아니라 `model_stock_daily/version=v2` 입력을 감사한 결과다.

셀에 null이 없는 것과 모든 종목이 모든 시장 거래일에 관측되는 것은 다르다. 신규 상장 전, 상장폐지 후, 거래정지, 개별 종목 거래 미발생일과 시장 휴장일은 null이 아니라 시계열 공백 또는 관측 범위 차이로 해석한다.

## 7. 품질 검증 규칙

생성 과정에서 다음 순서로 검증한다.

1. 직접 입력 Feature 필수 컬럼 존재 여부 확인
2. `symbol`을 문자열로 변환해 선행 0 보존
3. `Date`를 timestamp로 변환
4. OHLCV를 숫자형으로 변환
5. `symbol + Date` 중복 발견 시 생성 실패
6. 결측, 비양수 가격, 음수 거래량과 OHLC 범위 불일치를 사유별 분류
7. 정상행은 `is_tradable=true`, 품질 사유가 있는 행은 `false` 설정
8. 모든 직접 입력 Feature 행과 OHLCV 값 보존
9. 종목·날짜 오름차순 정렬

결측이나 비정상 가격을 0, 평균 또는 직전 값으로 대체하지 않는다. 품질 사유가 있는 행도 삭제하지 않고 상태 컬럼과 함께 보존한다.

## 8. 거래 불가 상태 통계

현재 `is_tradable=false`인 181,224건은 모두 `NO_INTRADAY_PRICE`로 분류됐다.

| 상태·사유            |     행 수 | 원천 대비 | 처리                       |
| -------------------- | --------: | --------: | -------------------------- |
| `TRADABLE`           | 5,057,576 |    96.54% | 품질 규칙상 신규 주문 허용 |
| `NO_INTRADAY_PRICE`  |   181,224 |     3.46% | 행 보존, 신규 주문 차단    |
| 필수 컬럼 결측       |         0 |     0.00% | 행 보존, 사유 표시         |
| `Close <= 0`         |         0 |     0.00% | 행 보존, 사유 표시         |
| `Volume < 0`         |         0 |     0.00% | 행 보존, 사유 표시         |
| `symbol + Date` 중복 |         0 |     0.00% | 생성 실패                  |

`NO_INTRADAY_PRICE`는 직접 입력 Feature에서 `Open`, `High`, `Low`가 모두 0인 패턴을 Data 계층이 분류한 품질 코드다. 공식 거래정지 여부를 직접 증명하는 KRX 상태 필드가 아니며 거래정지, 거래 미발생, 단일가·특수 거래 또는 상위 처리 과정의 표현일 수 있다. 이 분류는 가격 패턴만으로 원인을 확정하지 않고 Algorithm의 신규 주문을 보수적으로 차단하기 위한 것이다.

현재 직접 입력 Dataset에는 별도의 공식 거래정지 코드, 거래상태 코드 또는 원천 응답 lineage 컬럼이 포함되지 않는다. 공식 사유 구분이 필요하면 KRX 거래정지·시장조치 원장이나 Raw 응답의 상태 필드를 별도 수집·결합해야 한다.

- 영향 종목: 1,316개
- 종가 양수: 181,224건
- 거래량 0: 181,213건
- 거래량 양수: 11건

### Raw 역추적 표본

대표 행 `symbol=000040`, `Date=2018-01-02`를 KRX canonical Raw까지 역추적했다.

| 계층                            | Open | High | Low | Close | Volume |
| ------------------------------- | ---: | ---: | --: | ----: | -----: |
| KRX Raw (`TDD_*`, `ACC_TRDVOL`) |    0 |    0 |   0 |   325 |      0 |
| Algorithm OHLCV v2              |    0 |    0 |   0 |   325 |      0 |

Raw 경로는 `krx/stock_price/operation=stk_bydd_trd/year=2018/month=01/094f29a7e63eea8d485feefd21f811ce59862b797e454fe4d727bc0661c66659.jsonl.gz`다. 이 표본에서는 0값이 Algorithm 변환 중 생성된 것이 아님을 확인했다. 다만 이는 대표 표본 대조이며 181,224건 전체의 Raw 재감사나 공식 거래정지 사유 확인을 대신하지 않는다.

거래량 양수 예외 11건도 모두 `Open=High=Low=0`, `Close>0` 패턴이다. 이 때문에 `NO_INTRADAY_PRICE`는 `Volume=0`을 조건으로 삼지 않는다. 반대로 OHL이 음수인 비정상 값은 이 코드로 분류하지 않고 `PARTIAL_NON_POSITIVE_OHL`로 구분한다.

v1 생성기는 직접 입력 Feature를 변경하거나 삭제하지 않았다. 다만 `algorithm_ohlcv/version=v1` 출력에서 이 181,224건을 제외해 v1 소비자가 해당 날짜 상태를 볼 수 없었다. 영향 범위는 다음과 같다.

- v1 출력: 5,057,576행만 포함, 181,224행 누락
- 직접 입력 `model_stock_daily/version=v2`: 5,238,800행 그대로 보존
- v2 출력: 5,238,800행 전부 보존
- 저장소 내부 소비자: 현재 Algorithm 실행 구현은 없고 Dataset 생성·문서만 존재하므로 코드상 v1 소비 영향은 확인되지 않음
- 저장소 외부 소비자: 사용 여부를 이 저장소만으로 확인할 수 없으므로 v1을 즉시 삭제하지 않고 deprecated 산출물로 보존

v2는 직접 입력 Feature의 OHLCV 값을 변경하지 않고 모두 계승하며, Algorithm이 파생 flag인 `is_tradable`로 신규 주문 허용 여부를 판단하게 한다.

## 9. 추가 정합성 검사

| 검사                                   |      결과 |
| -------------------------------------- | --------: |
| 최종 행의 OHLCV 결측                   |       0건 |
| 직접 입력 Feature `symbol + Date` 중복 |       0건 |
| 거래 불가행의 거래량 0                 | 181,213건 |
| 거래 불가행의 거래량 양수              |      11건 |
| 최종 행의 음수 거래량                  |       0건 |
| `High < Low`                           |       0건 |
| `High < Open` 또는 `High < Close`      |       0건 |
| `Low > Open` 또는 `Low > Close`        |       0건 |

거래 가능행은 기본적인 일봉 가격 범위 정합성을 만족한다. 거래 불가행에서 직접 입력 Feature로부터 계승한 0값은 삭제하거나 보간하지 않는다.

## 10. 종목별 거래 가능 이력 길이

|   분위 | 종목별 행 수 |
| -----: | -----------: |
|   최소 |            2 |
|    25% |      1,156.5 |
| 중앙값 |        2,103 |
|    75% |        2,121 |
|    90% |        2,121 |
|    95% |        2,121 |
|   최대 |        2,121 |

### 최소 이력 기준 충족 종목 수

| 최소 행 수 | 충족 종목 | 전체 대비 |
| ---------: | --------: | --------: |
|         60 |     3,074 |    99.03% |
|        120 |     3,048 |    98.20% |
|        252 |     2,989 |    96.30% |
|        313 |     2,948 |    94.97% |
|        750 |     2,532 |    81.57% |
|      1,000 |     2,406 |    77.51% |
|      1,500 |     2,087 |    67.24% |

거래 가능행 기준 Algorithm 실행 최소선으로 제시된 313행에 미달하는 종목은 156개다. 신규 상장, 짧은 존속 기간 또는 긴 관측 공백 가능성이 있으므로 기본 Universe에서 제외하거나 별도 처리해야 한다.

```python
counts = dataset.loc[dataset["is_tradable"]].groupby("symbol").size()
eligible_symbols = counts[counts >= 313].index
dataset = dataset[dataset["symbol"].isin(eligible_symbols)]
```

## 11. 사용 예시

```python
from pathlib import Path
import pandas as pd

files = sorted(Path("algorithm_ohlcv/version=v2").glob("year=*/month=*/*.parquet"))
dataset = pd.concat((pd.read_parquet(path) for path in files), ignore_index=True)

stock_calendar = dataset.loc[dataset["symbol"] == "005930"].sort_values("Date")
stock = (
    stock_calendar.loc[stock_calendar["is_tradable"]]
    [["Date", "Open", "High", "Low", "Close", "Volume"]]
    .reset_index(drop=True)
)
```

전체 5백만 행을 매번 한 번에 적재할 필요는 없다. 필요한 월 파티션만 읽고 `symbol`로 필터링하는 방식을 권장한다.

## 12. 알려진 제한사항과 위험

### 기업행동 미조정

현재 `corporate_action_adjusted_price = false`다. 배당, 액면분할, 무상증자, 합병 등으로 인한 가격 단절이 장기 수익률, 모멘텀, 변동성과 백테스트 결과에 영향을 줄 수 있다. 조정주가를 도입할 경우 동일 조정계수를 OHLC 전체에 적용해야 한다.

### 생존편향과 Universe

최신 종목 마스터만 사용해 과거 Universe를 필터링하면 상장폐지 종목이 빠져 생존편향이 생길 수 있다. 과거 백테스트에서는 각 날짜에 실제 관측된 종목을 기준으로 Universe를 구성한다.

### 종목별 관측치 기반 Horizon

행 기반 rolling은 종목별 N번째 관측치를 의미한다. 거래 불가행을 지표 계산에서 제외하면 N행이 시장의 N거래일과 같지 않을 수 있다. 엄밀한 시장 거래일 horizon이 필요하면 KRX Calendar로 reindex한 새 Dataset version이 필요하다.

### 종목 유형

`symbol`만으로 보통주, 우선주, ETF, ETN, 스팩 등을 구분하지 않는다. 보통주 전용 전략은 시점 안전한 security master를 추가해 Universe를 정의해야 한다.

## 13. 재현 방법

저장소 루트에서 실행한다.

```bash
docker compose --profile data run --rm --no-deps data \
  python -m scripts.build_algorithm_dataset \
  --version 2 --overwrite
```

특정 종목 진단은 전체 Dataset과 다른 임시 version을 사용해야 한다. 같은 version에 `--symbol`과 `--overwrite`를 사용하면 해당 월 파티션이 부분 데이터로 교체될 수 있다.

```bash
docker compose --profile data run --rm --no-deps data \
  python -m scripts.build_algorithm_dataset \
  --version diagnostic-005930 --symbol 005930 --overwrite
```

## 14. 버전 정책과 개선 과제

다음 변경은 기존 v2를 조용히 덮어쓰지 않고 새 version으로 만든다.

- 기업행동 조정 OHLCV 도입
- KRX 거래일 Calendar reindex
- 종목 유형 및 시장 Universe 필터 추가
- 거래 불가행 상태·보존 정책 변경
- 컬럼 타입 또는 자연키 변경

후속 개선 권장사항:

1. manifest에 상태 사유별·연도별 통계 저장
2. 종목별 최초일, 최종일, 행 수, 최대 거래일 공백을 담은 품질 파일 생성
3. 기업행동 조정계열 별도 version 구축
4. 보통주·ETF 등 security type을 시점 안전하게 구분
5. 검증 CLI를 정기 workflow에 연결

## 15. 감사 기준

이 보고서의 상세 통계는 2026-08-26 생성된 v2 manifest와 직접 입력 Dataset `model_stock_daily/version=v2/` 104개 월 파티션을 재집계한 결과다. KRX API Raw 원문 전체를 이번 단계에서 다시 대조한 것은 아니다. Dataset을 다시 생성하거나 입력 version이 바뀌면 보고서 수치도 다시 감사해야 한다.
