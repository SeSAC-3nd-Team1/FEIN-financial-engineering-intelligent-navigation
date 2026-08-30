# 물방개 Agent 운영 Runbook

## 운영 환경변수

| 변수 | 기본값 | 설명 |
| --- | ---: | --- |
| `AI_CHATBOT_RATE_LIMIT_PER_MINUTE` | `30` | 로그인 사용자는 사용자 ID, 비로그인은 IP 기준으로 허용하는 요청 수 |
| `AI_CHATBOT_RATE_LIMIT_WINDOW_SECONDS` | `60` | rate limit 윈도우(초) |
| `AI_CHATBOT_TIMEOUT_SECONDS` | `30` | Azure OpenAI 요청 timeout |
| `AI_CHATBOT_MODEL_VERSION` | `chatbot-v1` | 응답에 기록되는 모델 버전 |
| `AI_CHATBOT_PROMPT_VERSION` | `v1` | 배포된 Prompt 버전 식별자 |

Rate limit 상태는 Redis TTL key `chat:rate:*`로 관리합니다. Redis 장애 시 챗봇은 fail-open으로 동작하며 `chat_rate_limit_unavailable_total`을 기록합니다. 운영에서는 이 metric을 알림 대상으로 등록하고 Redis 복구를 우선합니다.

## 관측성

구조화 로그 logger 이름은 `app.chat_agent`입니다.

- `chat_provider_request`: 성공/timeout/HTTP 오류/네트워크 오류, 지연시간, HTTP 상태, 토큰 사용량
- `chat_tool_call`: allowlist Tool 이름, 성공 여부, 지연시간
- `chat_rate_limit_unavailable`: Redis rate limit 장애

로그에는 사용자 메시지, Prompt 원문, Tool 인자·결과, 답변 원문, API key, 계좌 ID를 기록하지 않습니다. 요청 추적은 `X-Request-ID`를 사용하며 요청에 없으면 Backend가 UUID를 생성해 응답 헤더로 반환합니다.

## 안전성 회귀 평가셋

다음 유형은 Provider 호출 전에 `REFUSED`가 되어야 합니다.

- Prompt injection: 시스템 Prompt·내부 정책·API key 공개, 이전 지시 무시
- 매수/매도 지시: 지금 매수·매도, 주문 실행
- 수익 보장: 원금 보장, 수익 보장, 확정 수익

개인 계좌·포트폴리오 요청은 로그인, 최신 `AI_PERSONALIZATION` 동의, 계좌 소유권을 모두 통과해야 하며, Provider-visible context에는 계좌 ID를 포함하지 않습니다.

## 장애 대응

1. `CHAT_AGENT_RATE_LIMITED` / HTTP 429: 사용자 또는 IP별 요청량을 확인하고 필요할 때 환경변수로 한도를 조정합니다.
2. `CHAT_AGENT_TIMEOUT` / HTTP 504: Azure OpenAI 지연과 timeout을 확인하고 Provider 상태를 점검합니다.
3. `CHAT_AGENT_AUTH_FAILED`, `CHAT_AGENT_DEPLOYMENT_NOT_FOUND`: endpoint, deployment, API version, secret 설정을 확인합니다. Secret 자체를 로그에 출력하지 않습니다.
4. `CHAT_AGENT_UNAVAILABLE`: Azure 429/5xx 또는 네트워크 장애입니다. Provider 상태와 재시도 폭주 여부를 확인합니다.
5. `CHAT_AGENT_TOOL_LIMIT`: Tool 선택 루프가 비정상적으로 길어진 것이므로 해당 correlation ID와 Tool metric을 확인합니다.

## 검증 명령

```bash
docker compose run --rm --no-deps -e MODEL_RECOMMENDATION_SNAPSHOT_PATH= backend pytest -q tests/test_chat_api.py tests/test_chat_agent_client.py tests/test_chat_tools.py
docker compose run --rm --no-deps -e MODEL_RECOMMENDATION_SNAPSHOT_PATH= backend pytest -q
```

운영 배포 전에는 안전성 회귀 테스트와 `git diff --check`를 모두 통과해야 합니다.
