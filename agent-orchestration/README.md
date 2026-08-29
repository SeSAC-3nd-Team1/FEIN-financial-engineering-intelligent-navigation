# Agent Orchestration

Microsoft Foundry의 `MBGCoordinator`와 5개 전문 에이전트를 Entra ID로 호출하는 Python 오케스트레이터입니다. 기본 호출은 `azure-ai-projects`의 비동기 `AIProjectClient`와 OpenAI Responses/Conversations SDK를 사용합니다.

## 안전 정책

- 기본 모드는 `ANALYSIS_MODE=analysis_only`입니다.
- 실제 주문 실행 경로는 포함하지 않으며, 결과의 `trade_blocked`는 항상 `true`입니다.
- 인증은 Microsoft Entra ID의 `DefaultAzureCredential`만 사용합니다.
- resource key, API key, access token, identity ID, blueprint ID, connection string을 사용하거나 저장하지 않습니다.
- GA Responses protocol을 기본 경로로 사용합니다.
- A2A Preview는 호환 endpoint와 운영 승인이 확인되기 전까지 비활성화합니다.
- 최신 투자 유니버스를 검증할 수 없으면 guardrail이 거래 후보를 fail-closed로 차단합니다.
- Foundry System Instruction은 SDK에서 변경하지 않습니다. Tools, Knowledge, Memory, Guardrails 네 레이어만 `layers.py`의 런타임 프로파일로 제어합니다.
- 종가 trigger는 주문을 직접 실행하지 않고 `PAPER_ENGINE_HANDOFF`, `L3_REVIEW`, `PROPOSAL_ONLY`, `NO_TRADE` 중 하나를 결정합니다.

## 설치

PowerShell에서 프로젝트 루트에서 실행합니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

`.env.example`을 참고해 환경변수를 설정합니다. 프로젝트 endpoint는 기본값으로 설정되어 있으며 자격증명 같은 비밀값은 운영 환경의 보안된 환경변수 주입 방식을 사용합니다. `.env`는 Git에서 무시됩니다.

## Entra 인증

```powershell
az login
```

Foundry 프로젝트 endpoint 환경변수와 역할별 agent name 또는 endpoint를 설정한 뒤 실행합니다. RBAC 권한과 Foundry agent의 Running/Enabled 상태가 필요합니다.

## 분석 실행

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = "https://fein-agent.services.ai.azure.com/api/projects/proj-default"
agent-orchestrator "삼성전자를 분석해줘" --ticker 005930 --company-name 삼성전자
```

당일 종가 trigger와 planning을 함께 평가하려면 검증된 서버 데이터로 JSON을 만든 뒤 전달합니다.

```powershell
agent-orchestrator "삼성전자를 분석하고 종가 실행 후보를 계획해줘" `
  --ticker 005930 `
  --company-name 삼성전자 `
  --planning-context-json config/close-planning.example.json
```

`execution_plan.execution_allowed`는 항상 `false`입니다. `PAPER_ENGINE_HANDOFF`는 기존 결정론적 Risk/Policy Engine과 paper trading engine에 재검증 요청을 전달할 수 있다는 뜻이며 체결 완료를 뜻하지 않습니다.

출력은 구조화된 JSON이며, 분석 결과와 specialist 오류를 포함합니다. CLI는 주문 endpoint를 호출하지 않습니다.

Coordinator에게만 자연어 질문을 보내고 자연어 답변을 그대로 출력하려면 다음 옵션을 사용합니다.

```powershell
python -m agent_orchestration.cli "삼성전자의 최근 실적과 투자 위험을 설명해줘" --coordinator-only
```

`--coordinator-only`는 specialist 5개를 호출하지 않습니다. 이 모드에서는 agent 응답의 JSON 스키마 검증을 생략하고 Responses API의 `output_text`를 그대로 출력합니다. 요청·응답 네트워크 호출은 여전히 Entra ID 인증을 사용하며 주문 기능은 없습니다.

## 외부 챗봇 연결

외부 챗봇은 코드에 이름이나 endpoint를 추가하지 않고 registry로 등록합니다. 샘플인 `config/chatbots.example.json`을 복사해 다음 비밀정보가 아닌 연결 메타데이터를 입력합니다.

- `chatbot_id`: 서비스 내부에서 사용할 고유 채널 ID
- `display_name`: 표시 이름
- `provider`: `internal`, `foundry`, `http` 중 하나
- `source_agent_name`: Foundry 챗봇인 경우의 agent name
- `source_endpoint`: HTTP 챗봇인 경우의 HTTPS endpoint
- `allowed_context_keys`: MBGCoordinator에 전달할 수 있는 context 키
- `max_input_chars`, `max_response_chars`, `timeout_seconds`: 채널별 실행 제한

registry 파일과 inline JSON을 동시에 설정할 수는 없습니다.

```powershell
$env:CHATBOT_REGISTRY_PATH = "config/chatbots.json"
python -m agent_orchestration.cli "삼성전자를 분석해줘" `
  --chatbot-id new-service-chatbot `
  --conversation-id conversation-123 `
  --ticker 005930 `
  --company-name 삼성전자
```

서버의 webhook 또는 API route에서는 수신 payload를 `ChatbotMessage`로 정규화한 뒤 `MBGChatbotBridge.handle()`을 호출하면 됩니다. transport 인증과 webhook 서명 검증은 API gateway 또는 route에서 먼저 수행해야 합니다. Bridge는 미등록·비활성 채널, 허용되지 않은 context, 중첩된 credential 키, 과도한 입력을 차단하며 MBGCoordinator 응답의 `execution_allowed`를 항상 `false`로 반환합니다.

## 테스트

외부 네트워크가 필요 없는 테스트:

```powershell
python -m pytest -m "not live" -q
```

Live Foundry smoke test는 기본적으로 skip됩니다. 명시적으로 opt-in하고, 인증 및 환경변수를 준비한 경우에만 실행합니다.

```powershell
$env:RUN_LIVE_FOUNDRY_TESTS = "true"
python -m pytest tests/integration/test_live_foundry.py -m live -v
```

실패 시 endpoint, token, tenant, subscription, request payload를 로그나 보고서에 기록하지 않습니다.

## 구성 요소

- `config.py`: 역할별 설정과 endpoint 매핑
- `contracts.py`: 요청, 계획, 보고서, 결과의 Pydantic 계약
- `clients/responses.py`: Entra bearer token 기반 Responses adapter
- `clients/foundry_sdk.py`: `AIProjectClient` 기반 Responses/Conversations agent adapter
- `layers.py`: Tools, Knowledge, Memory, Guardrails 하이퍼파라미터와 역할별 프로파일
- `planning.py`: 종가·리밸런싱·손절 trigger와 fail-closed 실행 handoff 계획
- `clients/a2a.py`: 기본 비활성화된 Preview adapter
- `coordinator.py`: 계획, 병렬 fan-out, 오류 격리, 최종 fan-in
- `chatbot_bridge.py`: registry 기반 외부 챗봇 ingress와 MBGCoordinator 연결
- `universe.py`, `guardrails.py`: stale/unknown universe fail-closed 정책
- `telemetry.py`: 민감정보 redaction과 구조화 로그
- `cli.py`: 분석 전용 실행 진입점

## 보안 주의

공유된 credential이나 resource key는 사용하지 않습니다. 노출된 credential이 있다면 폐기·교체하고, 이후에는 Entra ID와 최소 권한 RBAC만 사용합니다. 실제 운영 endpoint와 식별자는 소스, fixture, 문서, 로그, 커밋에 기록하지 않습니다.
