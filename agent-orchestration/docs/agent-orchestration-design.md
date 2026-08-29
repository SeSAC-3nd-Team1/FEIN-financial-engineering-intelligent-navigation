# Agent Orchestration 설계

## 1. 목적

Microsoft Foundry Agent Service의 `MBGCoordinator`와 전문 에이전트 5개를 Python에서 오케스트레이션한다. 시스템은 분석 전용으로 동작하며 실제 주문 실행과 명확히 분리한다.

## 2. 배치 위치

최종 프로젝트 경로는 다음과 같다.

```text
C:\Users\EL022\Documents\ChatGPT\Agent Orchestration
```

기존 저장소와 기존 사용자 파일은 변경하지 않는다.

## 3. 시스템 구성

```text
사용자 요청
  ↓
MBGCoordinator: 요청 분석 및 작업 계획
  ↓
Python Orchestrator
  ├─ FinancialReport ─┐
  ├─ News             │
  ├─ MarketResearch   ├─ 비동기 병렬 호출 및 오류 격리
  ├─ Macro            │
  └─ AssetManager   ──┘
          ↓
구조화 출력 검증 + 금융 가드레일
          ↓
MBGCoordinator: 최종 종합
          ↓
사용자 응답
```

Python 내부 논리 역할과 실제 Foundry 배포 이름을 분리하고 환경변수로 매핑한다.

## 4. 프로젝트 구조

```text
Agent Orchestration/
├─ pyproject.toml
├─ .env.example
├─ .gitignore
├─ README.md
├─ src/agent_orchestration/
│  ├─ config.py
│  ├─ contracts.py
│  ├─ clients/
│  │  ├─ base.py
│  │  ├─ responses.py
│  │  └─ a2a.py
│  ├─ coordinator.py
│  ├─ guardrails.py
│  ├─ universe.py
│  ├─ telemetry.py
│  └─ cli.py
└─ tests/
   ├─ unit/
   └─ integration/
```

## 5. 인증과 비밀정보

- 로컬 개발은 `DefaultAzureCredential`과 Azure CLI 로그인을 사용한다.
- Azure 배포는 Managed Identity와 최소권한 RBAC를 사용한다.
- API 키와 리소스 키는 사용하지 않는다.
- identity ID, blueprint ID, access token, connection string, 전체 운영 endpoint를 코드·문서·테스트 fixture·로그에 기록하지 않는다.
- `.env.example`에는 빈 placeholder와 비민감 기본값만 둔다.
- `.env`는 `.gitignore`에 포함한다.
- 제공된 identity ID와 blueprint ID는 구현에 사용하지 않는다.
- 대화에 공개된 리소스 키는 사용하지 않으며 회전 대상으로 취급한다.

## 6. 프로토콜과 SDK

- 설치 가능한 최신 GA `azure-ai-projects`와 `azure-identity`를 공식 문서로 확인한 후 고정한다.
- 기본 경로는 OpenAI Responses 프로토콜이다.
- A2A endpoint와 연결이 검증되고 `ALLOW_PREVIEW_A2A=true`인 경우에만 A2A를 사용한다.
- Preview 사용 시 사용 이유, 위치, GA 대체 경로, 비활성화 방법을 README에 기록한다.
- classic Connected Agents API는 사용하지 않는다.

공통 클라이언트 인터페이스:

```python
class AgentClient(Protocol):
    async def invoke(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> AgentReport:
        ...
```

## 7. 오케스트레이션 데이터 흐름

1. CLI 또는 Python API가 사용자 요청과 선택적 포트폴리오·위험설정을 받는다.
2. MBGCoordinator가 구조화된 실행 계획을 반환한다.
3. 실행 계획과 요청 유형에 따라 필요한 전문 에이전트를 선택한다.
4. 선택된 전문 에이전트를 `asyncio.gather` 기반으로 병렬 호출한다.
5. 각 호출은 독립 timeout, retry, idempotency key, 오류 결과를 가진다.
6. Pydantic 모델로 전문 보고서를 검증한다.
7. UniverseProvider와 금융 가드레일을 적용한다.
8. 검증된 보고서와 오류·누락 정보를 MBGCoordinator에 전달한다.
9. MBGCoordinator가 최종 구조화 보고서를 생성한다.
10. 최종 결과를 다시 검증하고 사용자에게 반환한다.

## 8. 오류 격리와 재시도

- 한 전문 에이전트의 실패가 다른 에이전트 호출을 취소하지 않는다.
- timeout, 인증 오류, 비활성 에이전트, 형식 오류를 서로 다른 오류 코드로 정규화한다.
- 일시적 네트워크 오류와 제한 응답만 제한적으로 재시도한다.
- 인증·권한·스키마 오류는 자동 재시도하지 않는다.
- 핵심 보고서 누락 시 결과 상태를 `PARTIAL` 또는 `INSUFFICIENT_DATA`로 내리고 거래 후보를 차단한다.
- 도구 응답과 예외에 access token, endpoint 전체값, 개인정보가 기록되지 않도록 로그를 정제한다.

## 9. 구조화 출력

- 모든 입력·중간보고서·최종보고서는 Pydantic v2 모델로 검증한다.
- 공통 필드는 agent, request_id, ticker, company_name, as_of, data_freshness, status, summary, facts, estimates, assumptions, risks, sources, confidence, limitations, requires_human_review를 포함한다.
- 전문 에이전트별 필드는 해당 역할의 보고서 계약에 추가한다.
- MBGCoordinator의 action은 사전에 정의된 열거형만 허용한다.
- 알 수 없는 값은 생성하지 않고 `null`을 사용한다.

## 10. 투자 유니버스와 금융 가드레일

- UniverseProvider 인터페이스와 설정 기반 provider를 제공한다.
- KOSPI 200 구성 종목, 허용 ETF, 현금, RP, 국내 단기채를 지원한다.
- 해외주식, 가상자산, 파생상품, 레버리지·인버스 ETF, 장외상품은 기본 차단한다.
- 유니버스 데이터는 기준일, 갱신시각, stale 상태를 가진다.
- 갱신 실패 시 마지막 검증 데이터 사용 정책을 설정으로 제어한다.
- 최신 유니버스를 검증할 수 없으면 fail-closed로 거래 후보 선정을 차단한다.
- `ANALYSIS_MODE=analysis_only`가 기본값이며 실제 주문 실행 코드는 포함하지 않는다.
- 모든 proposed order는 `execution_allowed=false`를 유지한다.

## 11. 로깅과 추적

- 구조화 logging을 사용한다.
- request ID, idempotency key, agent role, latency, attempt, status를 기록한다.
- 프롬프트·응답 전문은 기본 로그에 기록하지 않는다.
- Application Insights/OpenTelemetry는 선택 기능으로 둔다.
- connection string은 코드나 예제 파일에 저장하지 않는다.

## 12. 테스트

### 단위 테스트

- 환경설정 검증
- Pydantic 계약 검증
- 에이전트 역할과 배포 이름 매핑
- 전문 에이전트 병렬 호출
- timeout 및 부분 실패 격리
- retry 분류
- UniverseProvider stale/fail-closed 정책
- 금융 가드레일
- 로그 비밀정보 정제
- 주문 실행 차단

### mock 통합 테스트

- MBG 계획 → 전문 에이전트 병렬 호출 → MBG 종합 전체 흐름
- 일부 전문 에이전트 실패 흐름
- 잘못된 JSON과 불완전 보고서 흐름

### 실제 Foundry 통합 테스트

- 명시적 환경변수 플래그가 있을 때만 실행한다.
- Azure CLI 로그인 자격증명과 Entra RBAC를 사용한다.
- endpoint와 agent name은 실행 환경에서만 주입한다.
- 각 에이전트의 연결성, 출력 상태, 전체 오케스트레이션을 검증한다.
- 실제 주문은 호출하지 않는다.

## 13. 완료 기준

- Python 3.11 이상에서 설치 및 import가 성공한다.
- 단위 테스트와 mock 통합 테스트가 통과한다.
- endpoint·identity·blueprint·키 실값이 생성 파일과 로그에 존재하지 않는다.
- Azure 로그인과 RBAC가 유효할 경우 실제 6개 에이전트 연결 테스트를 실행할 수 있다.
- 실제 통합 테스트 결과와 실패 원인을 문서화한다.
- README에 로컬 설치, `az login`, 환경변수 설정, mock 테스트, live 테스트 명령이 포함된다.

## 14. 비목표

- 실제 증권사 주문 API 연동
- 실거래 승인
- 위험한도 자동 변경
- secrets를 코드 또는 평문 설정에 저장
- Foundry 에이전트 자체의 재배포나 instruction 변경
