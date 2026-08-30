# FE!N Chatbot Foundry Orchestration 통합

## 구조

기존 `POST /api/v1/chat/messages` route의 rate limit, 선택 사용자 인증, 개인화 동의, 계좌 ownership 검증은 유지됩니다. 검증을 통과한 요청만 Backend adapter가 `ChatbotMessage`로 변환하고 `MBGChatbotBridge`에 전달합니다. Bridge는 `fein-web-chatbot` 채널을 확인하고 허용된 화면 context만 `AgentOrchestrator`/`MBGCoordinator`에 전달합니다. 전문 Agent 호출과 최종 합성은 기존 agent-orchestration 구현이 담당합니다.

Frontend contract (`status`, `text`, `caution`, `suggested_questions`, `message_id`, `model_version`, `generated_at`)은 변경하지 않습니다. 기존 Azure OpenAI provider는 `AI_CHATBOT_PROVIDER=azure_openai`로 남아 있으며 production 기본값은 `foundry_orchestration`입니다. Provider 장애를 자동으로 조용히 fallback하지 않습니다.

## Docker / 인증

`backend/Dockerfile`은 `pip install /agent-orchestration`로 정상 package 설치를 수행합니다. Backend adapter는 CLI subprocess를 사용하지 않고 `DefaultAzureCredential`과 `azure.ai.projects.aio.AIProjectClient`를 직접 사용합니다. 로컬에서는 Azure CLI credential, Container App에서는 system-assigned Managed Identity가 선택됩니다. 사용자 브라우저에는 Azure credential을 요구하지 않습니다.

## 운영 환경변수

필수 값은 GitHub production Environment variables에서 Container App 환경변수로 주입합니다.

- `AI_CHATBOT_PROVIDER=foundry_orchestration`
- `FOUNDRY_PROJECT_ENDPOINT`
- `FOUNDRY_MODEL_DEPLOYMENT_NAME` (Foundry 프로젝트 정책에 따라 필요할 때)
- `MBG_COORDINATOR_AGENT_NAME`
- `FINANCIAL_REPORT_AGENT_NAME`
- `NEWS_AGENT_NAME`
- `MARKET_RESEARCH_AGENT_NAME`
- `MACRO_AGENT_NAME`
- `ASSET_MANAGER_AGENT_NAME`
- `FEIN_CHATBOT_ID=fein-web-chatbot`
- `CHATBOT_REGISTRY_JSON` (민감정보가 아닌 registry JSON)
- `AGENT_PROTOCOL=responses`
- `AGENT_CLIENT_BACKEND=foundry_sdk`
- `ALLOW_PREVIEW_A2A=false`
- `ANALYSIS_MODE=analysis_only`

`.env` 또는 API key는 production 이미지에 포함하지 않습니다.

## Managed Identity / Foundry RBAC one-time setup

배포 workflow가 Backend Container App의 system-assigned identity를 재사용합니다. 조직 정책상 workflow service principal이 role assignment를 만들 수 없으면 Azure 관리자 환경에서 다음 절차를 수행합니다.

1. Backend Container App에 system-assigned identity를 활성화합니다.
2. `az containerapp show`로 `identity.principalId`를 확인합니다.
3. Microsoft Foundry 프로젝트 범위에서 해당 principal에 프로젝트의 agent invoke/contributor 권한(조직에서 승인한 최소 역할)을 부여합니다.
4. workflow를 다시 실행하고 Backend revision 로그에 credential/token 값이 아닌 성공 여부만 확인합니다.

실제 project ID, principal ID, token은 저장소·문서·로그에 기록하지 않습니다. 정확한 역할 이름은 Foundry 리소스의 현재 RBAC 제공 역할 목록을 확인해 조직 표준 최소 역할로 선택해야 합니다.

## 검증

- `python -m compileall -q backend/app agent-orchestration/src`
- agent-orchestration live 테스트는 `RUN_LIVE_FOUNDRY_TESTS=true`일 때만 실행합니다.
- 운영 배포 후 Azure 로그인하지 않은 일반 브라우저에서 Frontend → Backend → Managed Identity → Foundry 흐름을 확인합니다.
- API key 없이 호출되고, account number/token/credential이 provider context·response·로그에 나타나지 않는지 확인합니다.

현재 작업 환경에서는 실제 Azure Container App 배포 및 Azure 계정 없는 production E2E를 실행할 수 없으므로, 해당 결과는 배포 workflow 실행 기록과 운영 점검 항목으로 확인해야 합니다.
