# 전략 카탈로그와 물림방지 실행 구조

## 카탈로그

| UI 그룹 | 전략 ID | 상태 | 실행 엔진 |
| --- | --- | --- | --- |
| 물 | `low` | 이용 가능 | `algorithm_v2_4_fix2` |
| 방 | `momentum` | 이용 가능 | `price_momentum_v1` |
| 방 | `value` | 테스트 중 | `value_factor_v1` |
| 방 | `stat_arb` | 테스트 중 | `stat_arb_v1` |
| 방 | `event_driven` | 테스트 중 | `event_driven_v1` |
| 개 | DB 전략이 아닌 제품 Preview | 테스트 중 | 미정 |

기존 계좌와 온보딩이 `low`를 외래키로 참조하므로 식별자는 유지하고 이름과 엔진 계약만 물림방지 전략으로 전환했다. 테스트 중 전략은 조회 API에는 노출하지만 계좌 전략 선택과 투자 온보딩에서는 거부한다.

## 물림방지 투자 흐름

1. `loss-avoidance-generator`가 Azure `algorithm_ohlcv/version=v2`를 읽는다.
2. 거래 가능한 종목 중 최근 60일 중위 거래대금 상위 종목으로 실행 가능 유니버스를 정한다.
3. 각 종목의 OHLCV를 팀 원본 `output/Algorithm(ver.2.4)_fix2.py`에 그대로 전달한다.
4. 알고리즘의 `target_weight`, 예측 분포, 레짐, 위험 승인 결과만으로 종목 순위와 총 주식 노출을 만든다.
5. `/model-artifacts/loss_avoidance_snapshot.json`을 원자적으로 발행한다.
6. 사용자가 `low`를 선택해 투자를 확정하면 Backend가 해당 스냅샷의 버전·신선도·비중을 검증하고 목표 비중을 저장한다.
7. AUTO 계좌의 최초 빈 포트폴리오만 멱등 시장가 주문으로 체결한다. 기존 보유 종목이 있거나 SEMI_AUTO 계좌이면 제안만 발행한다.

유동성 정렬은 여러 종목 중 실행 대상을 정하기 위한 운영 규칙이며 투자 신호에는 사용하지 않는다. 매수 노출, 레짐 판단, 위험 축소는 모두 `Algorithm(ver.2.4)_fix2`의 출력에서 가져온다.

## 로컬 실행

마이그레이션을 적용한 뒤 알고리즘 산출물을 먼저 생성한다.

```bash
docker compose --profile migration run --rm db-init
docker compose --profile ai run --rm loss-avoidance-generator
docker compose up backend frontend
```

주요 환경변수는 다음과 같다.

- `ALGORITHM_FEATURE_VERSION`: `algorithm_ohlcv` 버전, 기본값 `2`
- `LOSS_AVOIDANCE_TOP_N`: 최종 목표 종목 수, 기본값 `5`
- `LOSS_AVOIDANCE_UNIVERSE_SIZE`: 알고리즘 평가 전 유동성 유니버스 크기, 기본값 `20`
- `LOSS_AVOIDANCE_SNAPSHOT_PATH`: AI와 Backend가 공유하는 JSON 경로

운영 환경에서는 generator를 장 마감 데이터 적재 후 실행하고, Backend의 기본 3일 신선도 제한보다 짧은 주기로 산출물을 갱신해야 한다.
