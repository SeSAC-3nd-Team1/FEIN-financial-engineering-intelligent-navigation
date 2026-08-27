# Agent Orchestration

Microsoft Foundry의 `MBGCoordinator`와 5개 전문 에이전트를 Entra ID로 호출하는 분석 전용 Python 오케스트레이터입니다.

## 안전 정책

- 기본 모드는 `ANALYSIS_MODE=analysis_only`입니다.
- 실제 주문 실행 경로는 포함하지 않으며, 결과의 `trade_blocked`는 항상 `true`입니다.
- 인증은 Microsoft Entra ID의 `DefaultAzureCredential`만 사용합니다.
- resource key, API key, access token, identity ID, blueprint ID, connection string을 사용하거나 저장하지 않습니다.
- GA Responses protocol을 기본 경로로 사용합니다.
- A2A Preview는 호환 endpoint와 운영 승인이 확인되기 전까지 비활성화합니다.
- 최신 투자 유니버스를 검증할 수 없으면 guardrail이 거래 후보를 fail-closed로 차단합니다.

## 설치

PowerShell에서 프로젝트 루트에서 실행합니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

`.env.example`을 참고해 환경변수를 설정합니다. 실제 endpoint 값은 파일이나 로그에 저장하지 말고, 운영 환경의 보안된 환경변수 주입 방식을 사용합니다. `.env`는 Git에서 무시됩니다.

## Entra 인증

```powershell
az login
```

Foundry 프로젝트 endpoint 환경변수와 역할별 agent name 또는 endpoint를 설정한 뒤 실행합니다. RBAC 권한과 Foundry agent의 Running/Enabled 상태가 필요합니다.

## 분석 실행

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = Read-Host "Foundry project endpoint"
agent-orchestrator "삼성전자를 분석해줘" --ticker 005930 --company-name 삼성전자
```

출력은 구조화된 JSON이며, 분석 결과와 specialist 오류를 포함합니다. CLI는 주문 endpoint를 호출하지 않습니다.

Coordinator에게만 자연어 질문을 보내고 자연어 답변을 그대로 출력하려면 다음 옵션을 사용합니다.

```powershell
python -m agent_orchestration.cli "삼성전자의 최근 실적과 투자 위험을 설명해줘" --coordinator-only
```

`--coordinator-only`는 specialist 5개를 호출하지 않습니다. 이 모드에서는 agent 응답의 JSON 스키마 검증을 생략하고 Responses API의 `output_text`를 그대로 출력합니다. 요청·응답 네트워크 호출은 여전히 Entra ID 인증을 사용하며 주문 기능은 없습니다.

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
- `clients/a2a.py`: 기본 비활성화된 Preview adapter
- `coordinator.py`: 계획, 병렬 fan-out, 오류 격리, 최종 fan-in
- `universe.py`, `guardrails.py`: stale/unknown universe fail-closed 정책
- `telemetry.py`: 민감정보 redaction과 구조화 로그
- `cli.py`: 분석 전용 실행 진입점

## 보안 주의

공유된 credential이나 resource key는 사용하지 않습니다. 노출된 credential이 있다면 폐기·교체하고, 이후에는 Entra ID와 최소 권한 RBAC만 사용합니다. 실제 운영 endpoint와 식별자는 소스, fixture, 문서, 로그, 커밋에 기록하지 않습니다.
