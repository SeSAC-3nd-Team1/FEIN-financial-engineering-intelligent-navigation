# FINCON-inspired Algorithm v2.3 통합 매매 엔진

모델 코어는 `output/fincon_ver23_model.py`에 구현한다. 이 엔진은 FINCON의 manager–analyst 계층과 risk-first synthesis 패턴을 현재
가상투자 서버에 맞게 적용한다. FINCON 원본 코드를 런타임에 포함하지 않으며,
외부 에이전트가 주문을 직접 생성하지 못하게 구조화된 계약만 허용한다.

참고 프로젝트: <https://github.com/lindd-zju/FinCON> (MIT License)

## 결정 순서

1. 로그인 사용자와 가상계좌 소유권을 검증한다.
2. Algorithm(ver2.3)의 목표비중과 권장 stop 가격을 검증한다.
3. stop 가격을 침범한 보유종목을 최우선 전량 매도한다.
4. 선택적인 MBGCoordinator 조언으로 신규 노출을 차단할 수 있다.
5. 목표비중과 현재비중 차이를 회전율·현금 버퍼·최소 주문금액으로 제한한다.
6. 매도 후 매수 순서로 기존 `TradingService`에서 가상 체결한다.

MBGCoordinator는 종목을 차단할 수 있지만 목표비중을 새로 만들거나 높일 수 없고,
손절을 거부할 수도 없다. `execute`의 기본값은 `false`이므로 호출 시 주문 계획만
반환한다.

## API

`POST /api/v1/trading-engine/runs`

```json
{
  "account_id": "00000000-0000-0000-0000-000000000000",
  "signal": {
    "algorithm_version": "2.3",
    "generated_at": "2026-08-28T09:00:00+09:00",
    "target_weights": {"005930": "0.30", "000660": "0.25"},
    "stop_prices": {"005930": "68000"},
    "confidence": "0.82"
  },
  "coordinator_advice": {
    "request_id": "mbg-request-id",
    "confidence": "0.75",
    "blocked_symbols": [],
    "risk_flags": [],
    "summary": "분석 종합 결과"
  },
  "execute": false,
  "max_turnover": "0.30",
  "min_order_amount": "1000",
  "cash_buffer": "0.05"
}
```

Algorithm v2.3 실행부는 실험 파일을 웹 프로세스에서 직접 import하지 않고
`AlgorithmSignal`로 결과를 전달해야 한다. 이렇게 하면 TensorFlow 모델 실행과
FastAPI 주문 처리를 별도 프로세스나 예약 작업으로 분리할 수 있다.

서버는 `FINCON_VER23_MODEL_PATH`에서 모델을 동적으로 로드한다. compose 환경은
`./output`을 `/models`에 읽기 전용으로 마운트하고 기본 경로를
`/models/fincon_ver23_model.py`로 지정한다.

추후 MBGCoordinator 연결 시 `OrchestrationResult.final_report.details`를 검증한 뒤
`CoordinatorAdvice`로 변환하는 adapter만 추가한다. 기존 `analysis_only` 정책을
유지하려면 coordinator가 이 API를 직접 호출하지 않고 서버 측 예약 작업이 결과를
수집하도록 구성한다.

## MBGCoordinator `_fix` gate

`POST /api/v1/trading-engine-fix/runs`는 Entra ID `DefaultAzureCredential`로
MBGCoordinator Responses endpoint를 호출한다. Agent는 Algorithm v2.3이 제시한
종목 집합 안에서만 비중을 수정할 수 있고, 종목별 변경폭은 기본 ±10%p로 제한된다.
승인 비중 합계는 현금 버퍼 5%를 남기도록 정규화된다. Agent 장애·낮은 confidence·
종목 집합 또는 기준비중 불일치 시 Algorithm 기준 비중으로 복귀한다. 1시간보다
오래된 신호는 차단한다.

기존 TradingService가 주문마다 commit하므로 `_fix` endpoint는 다중 주문의 실제
모의체결을 `ATOMIC_BATCH_EXECUTION_REQUIRED`로 차단한다. 다중 리밸런싱은 DRY_RUN
계획으로 확인할 수 있으며, 실제 실행 허용은 원자적 batch transaction 구현 후
확장한다.
