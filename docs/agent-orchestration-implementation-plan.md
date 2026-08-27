# Agent Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Microsoft Foundry의 MBGCoordinator와 전문 에이전트 5개를 Entra ID로 호출하고, 병렬 실행·오류 격리·구조화 검증·금융 가드레일·실제 통합 테스트를 제공하는 분석 전용 Python 프로젝트를 구축한다.

**Architecture:** CLI가 MBGCoordinator에서 실행계획을 받은 뒤 선택된 전문 에이전트를 비동기 병렬 호출하고, 검증된 보고서와 오류를 다시 MBGCoordinator에 전달해 최종 보고서를 생성한다. 에이전트 호출은 `AgentClient` 프로토콜 뒤에 격리하며, 현재 제공된 GA Responses endpoint는 Entra bearer token과 비동기 HTTP 어댑터로 호출한다. A2A는 endpoint와 운영 승인이 모두 있을 때만 선택 가능한 별도 어댑터로 둔다.

**Tech Stack:** Python 3.11+, azure-ai-projects 2.5.0, azure-identity, pydantic v2, pydantic-settings, httpx, tenacity, structlog, pytest, pytest-asyncio, respx

## Global Constraints

- 최종 경로는 `C:\Users\EL022\Documents\ChatGPT\Agent Orchestration`이다.
- 기존 프로젝트와 사용자 파일은 수정하지 않는다.
- 인증은 `DefaultAzureCredential`과 Microsoft Entra ID만 사용한다.
- identity ID, blueprint ID, 리소스 키, access token, connection string, 실제 endpoint를 생성 파일·테스트 fixture·로그에 기록하지 않는다.
- `.env.example`에는 빈 endpoint placeholder와 비민감 에이전트 기본 이름만 둔다.
- 논리 역할과 실제 Foundry 배포 이름을 환경변수로 분리한다.
- 전문 에이전트는 비동기 병렬 호출하며 한 호출의 실패가 다른 호출을 취소하지 않는다.
- 기본 모드는 `analysis_only`이며 주문 실행 코드를 포함하지 않는다.
- 최신 유니버스를 검증할 수 없으면 거래 후보 선정을 fail-closed로 차단한다.
- 실제 Foundry 테스트는 명시적 opt-in 환경변수가 있을 때만 실행한다.

---

## File Map

- `pyproject.toml`: 패키지, Python 버전, 런타임·테스트 의존성, pytest 설정
- `.env.example`: 값 없는 endpoint placeholder와 비민감 기본 설정
- `.gitignore`: `.env`, 가상환경, 캐시, 테스트 산출물 차단
- `src/agent_orchestration/config.py`: 환경변수 검증과 역할별 endpoint/name 매핑
- `src/agent_orchestration/contracts.py`: 요청, 계획, 보고서, 오류, 최종 결과 Pydantic 계약
- `src/agent_orchestration/clients/base.py`: `AgentClient` 프로토콜
- `src/agent_orchestration/clients/responses.py`: Responses endpoint용 Entra 비동기 클라이언트
- `src/agent_orchestration/clients/a2a.py`: 명시적 활성화 전에는 fail-closed하는 A2A 선택 어댑터
- `src/agent_orchestration/universe.py`: 기준일·stale·fail-closed를 지원하는 UniverseProvider
- `src/agent_orchestration/guardrails.py`: 허용 유니버스와 주문 차단 규칙
- `src/agent_orchestration/telemetry.py`: 구조화 로그와 비밀정보 정제
- `src/agent_orchestration/coordinator.py`: 계획, 병렬 fan-out, 검증, 최종 fan-in
- `src/agent_orchestration/cli.py`: 로컬 실행 진입점
- `tests/unit/`: 구성요소 단위 테스트
- `tests/integration/test_mock_orchestration.py`: 네트워크 없는 전체 흐름 테스트
- `tests/integration/test_live_foundry.py`: opt-in 실제 Foundry 연결 테스트
- `README.md`: 설치, 인증, 환경변수, 테스트, Preview 정책, 보안 지침

### Task 1: Package scaffold and secure configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `src/agent_orchestration/__init__.py`
- Create: `src/agent_orchestration/config.py`
- Test: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `Settings`, `Settings.endpoint_for(role)`, `Settings.agent_name_for(role)`
- Consumes: process environment only

- [ ] **Step 1: Write failing configuration tests**

```python
from pydantic import ValidationError
import pytest

from agent_orchestration.config import Settings


def test_settings_map_logical_role_to_deployment_name(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/test")
    monkeypatch.setenv("NEWS_AGENT_NAME", "aiNewsAgent")
    settings = Settings()
    assert settings.agent_name_for("News") == "aiNewsAgent"


def test_settings_reject_non_analysis_mode(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example.invalid/api/projects/test")
    monkeypatch.setenv("ANALYSIS_MODE", "live_trading")
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_config.py -q`

Expected: collection fails because `agent_orchestration.config` does not exist.

- [ ] **Step 3: Create package metadata and secure examples**

```toml
[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = "agent-orchestration"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "azure-ai-projects==2.5.0",
  "azure-identity>=1.25,<2",
  "pydantic>=2.11,<3",
  "pydantic-settings>=2.10,<3",
  "httpx>=0.28,<1",
  "tenacity>=9.1,<10",
  "structlog>=25.4,<26",
]

[project.optional-dependencies]
test = [
  "pytest>=8.4,<9",
  "pytest-asyncio>=1.1,<2",
  "respx>=0.22,<1",
]

[project.scripts]
agent-orchestrator = "agent_orchestration.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["src/agent_orchestration"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = ["live: calls real Microsoft Foundry endpoints"]
```

`.env.example` content:

```dotenv
FOUNDRY_PROJECT_ENDPOINT=
FOUNDRY_MODEL_DEPLOYMENT_NAME=
MBG_COORDINATOR_AGENT_NAME=MBGCoordinator
FINANCIAL_REPORT_AGENT_NAME=FinancialReport
NEWS_AGENT_NAME=News
MARKET_RESEARCH_AGENT_NAME=MarketResearch
MACRO_AGENT_NAME=Macro
ASSET_MANAGER_AGENT_NAME=AssetManager
MBG_COORDINATOR_ENDPOINT=
FINANCIAL_REPORT_ENDPOINT=
NEWS_ENDPOINT=
MARKET_RESEARCH_ENDPOINT=
MACRO_ENDPOINT=
ASSET_MANAGER_ENDPOINT=
AGENT_PROTOCOL=responses
ALLOW_PREVIEW_A2A=false
ANALYSIS_MODE=analysis_only
APPLICATIONINSIGHTS_CONNECTION_STRING=
RUN_LIVE_FOUNDRY_TESTS=false
```

`.gitignore` content:

```gitignore
.env
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
```

- [ ] **Step 4: Implement validated settings**

```python
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


Role = Literal["MBGCoordinator", "FinancialReport", "News", "MarketResearch", "Macro", "AssetManager"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    foundry_project_endpoint: AnyHttpUrl
    foundry_model_deployment_name: str | None = None
    mbg_coordinator_agent_name: str = "MBGCoordinator"
    financial_report_agent_name: str = "FinancialReport"
    news_agent_name: str = "News"
    market_research_agent_name: str = "MarketResearch"
    macro_agent_name: str = "Macro"
    asset_manager_agent_name: str = "AssetManager"
    mbg_coordinator_endpoint: AnyHttpUrl | None = None
    financial_report_endpoint: AnyHttpUrl | None = None
    news_endpoint: AnyHttpUrl | None = None
    market_research_endpoint: AnyHttpUrl | None = None
    macro_endpoint: AnyHttpUrl | None = None
    asset_manager_endpoint: AnyHttpUrl | None = None
    agent_protocol: Literal["responses", "a2a", "auto"] = "responses"
    allow_preview_a2a: bool = False
    analysis_mode: Literal["analysis_only", "paper_trading"] = "analysis_only"
    applicationinsights_connection_string: str | None = Field(default=None, repr=False)
    run_live_foundry_tests: bool = False

    def agent_name_for(self, role: Role) -> str:
        return {
            "MBGCoordinator": self.mbg_coordinator_agent_name,
            "FinancialReport": self.financial_report_agent_name,
            "News": self.news_agent_name,
            "MarketResearch": self.market_research_agent_name,
            "Macro": self.macro_agent_name,
            "AssetManager": self.asset_manager_agent_name,
        }[role]

    def endpoint_for(self, role: Role) -> str:
        explicit = {
            "MBGCoordinator": self.mbg_coordinator_endpoint,
            "FinancialReport": self.financial_report_endpoint,
            "News": self.news_endpoint,
            "MarketResearch": self.market_research_endpoint,
            "Macro": self.macro_endpoint,
            "AssetManager": self.asset_manager_endpoint,
        }[role]
        if explicit is not None:
            return str(explicit)
        project = str(self.foundry_project_endpoint).rstrip("/")
        name = self.agent_name_for(role)
        return f"{project}/agents/{name}/endpoint/protocols/openai/responses"


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_config.py -q`

Expected: `2 passed`.

### Task 2: Typed contracts and structured output parser

**Files:**
- Create: `src/agent_orchestration/contracts.py`
- Test: `tests/unit/test_contracts.py`

**Interfaces:**
- Produces: `AgentRequest`, `CoordinatorPlan`, `AgentReport`, `SpecialistOutcome`, `OrchestrationResult`, `extract_json_object`
- Consumes: Pydantic v2

- [ ] **Step 1: Write failing contract tests**

```python
import pytest
from pydantic import ValidationError

from agent_orchestration.contracts import AgentReport, extract_json_object


def test_extract_json_object_from_fenced_response():
    raw = '결과입니다.\n```json\n{"agent":"News","status":"OK","confidence":0.8}\n```'
    assert extract_json_object(raw)["agent"] == "News"


def test_agent_report_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        AgentReport(agent="News", status="OK", confidence=1.2)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_contracts.py -q`

Expected: import failure for missing contracts module.

- [ ] **Step 3: Implement contracts and parser**

```python
import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ReportStatus(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    TOOL_ERROR = "TOOL_ERROR"


class Source(BaseModel):
    title: str
    publisher: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    data_as_of: datetime | None = None
    primary_source: bool = False


class AgentRequest(BaseModel):
    request_id: str
    role: str
    user_query: str
    ticker: str | None = None
    company_name: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class CoordinatorPlan(BaseModel):
    request_id: str
    ticker: str | None = None
    company_name: str | None = None
    selected_roles: list[str]
    tasks: dict[str, str]


class AgentReport(BaseModel):
    agent: str
    request_id: str | None = None
    ticker: str | None = None
    company_name: str | None = None
    as_of: datetime | None = None
    data_freshness: str = "UNKNOWN"
    status: ReportStatus
    summary: str = ""
    facts: list[Any] = Field(default_factory=list)
    estimates: list[Any] = Field(default_factory=list)
    assumptions: list[Any] = Field(default_factory=list)
    risks: list[Any] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    limitations: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class SpecialistOutcome(BaseModel):
    role: str
    report: AgentReport | None = None
    error_code: str | None = None
    error_message: str | None = None


class OrchestrationResult(BaseModel):
    request_id: str
    plan: CoordinatorPlan
    specialists: list[SpecialistOutcome]
    final_report: AgentReport
    trade_blocked: bool = True
    block_reasons: list[str] = Field(default_factory=list)


def extract_json_object(text: str) -> dict[str, Any]:
    candidates = [text]
    candidates.extend(re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL))
    decoder = json.JSONDecoder()
    for candidate in candidates:
        stripped = candidate.strip()
        try:
            value = json.loads(stripped)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            for index, character in enumerate(stripped):
                if character != "{":
                    continue
                try:
                    value, _ = decoder.raw_decode(stripped[index:])
                    if isinstance(value, dict):
                        return value
                except json.JSONDecodeError:
                    continue
    raise ValueError("response does not contain a valid JSON object")
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_contracts.py -q`

Expected: `2 passed`.

### Task 3: AgentClient protocol and Entra-authenticated Responses adapter

**Files:**
- Create: `src/agent_orchestration/clients/__init__.py`
- Create: `src/agent_orchestration/clients/base.py`
- Create: `src/agent_orchestration/clients/responses.py`
- Create: `src/agent_orchestration/clients/a2a.py`
- Test: `tests/unit/test_responses_client.py`

**Interfaces:**
- Consumes: `AgentRequest`, `AgentReport`, endpoint resolver, `azure.core.credentials_async.AsyncTokenCredential`
- Produces: `AgentClient.invoke(request, timeout_seconds, idempotency_key) -> AgentReport`

- [ ] **Step 1: Write failing HTTP adapter tests**

```python
from types import SimpleNamespace

import httpx
import pytest
import respx

from agent_orchestration.clients.responses import ResponsesAgentClient
from agent_orchestration.contracts import AgentRequest


class FakeCredential:
    async def get_token(self, *scopes, **kwargs):
        return SimpleNamespace(token="test-token")


@pytest.mark.asyncio
@respx.mock
async def test_responses_client_uses_entra_bearer_and_parses_report():
    endpoint = "https://example.invalid/agents/News/endpoint/protocols/openai/responses"
    route = respx.post(endpoint).mock(
        return_value=httpx.Response(200, json={"output_text": '{"agent":"News","status":"OK","confidence":0.9}'})
    )
    async with httpx.AsyncClient() as http:
        client = ResponsesAgentClient(endpoint, FakeCredential(), http)
        report = await client.invoke(
            AgentRequest(request_id="req-1", role="News", user_query="삼성전자 뉴스"),
            timeout_seconds=5,
            idempotency_key="idem-1",
        )
    assert report.agent == "News"
    assert route.calls[0].request.headers["Authorization"] == "Bearer test-token"
    assert route.calls[0].request.headers["Idempotency-Key"] == "idem-1"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_responses_client.py -q`

Expected: import failure for missing client module.

- [ ] **Step 3: Define protocol and Responses implementation**

```python
# clients/base.py
from typing import Protocol
from agent_orchestration.contracts import AgentReport, AgentRequest


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

```python
# clients/responses.py
import httpx
from azure.core.credentials_async import AsyncTokenCredential
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_orchestration.contracts import AgentReport, AgentRequest, extract_json_object


class RetryableAgentError(RuntimeError):
    pass


class ResponsesAgentClient:
    def __init__(self, endpoint: str, credential: AsyncTokenCredential, http: httpx.AsyncClient):
        self._endpoint = endpoint
        self._credential = credential
        self._http = http

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, RetryableAgentError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.25, min=0.25, max=2),
        reraise=True,
    )
    async def invoke(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> AgentReport:
        token = await self._credential.get_token("https://ai.azure.com/.default")
        response = await self._http.post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            json={"input": request.user_query, "metadata": {"request_id": request.request_id}},
            timeout=timeout_seconds,
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableAgentError(f"retryable agent status {response.status_code}")
        response.raise_for_status()
        payload = response.json()
        output_text = payload.get("output_text")
        if not isinstance(output_text, str):
            output_text = "".join(
                content.get("text", "")
                for item in payload.get("output", [])
                for content in item.get("content", [])
                if content.get("type") == "output_text"
            )
        return AgentReport.model_validate(extract_json_object(output_text))
```

```python
# clients/a2a.py
from agent_orchestration.contracts import AgentReport, AgentRequest


class A2AAgentClient:
    def __init__(self, enabled: bool):
        if not enabled:
            raise RuntimeError("A2A is disabled; set ALLOW_PREVIEW_A2A=true only after endpoint validation")

    async def invoke(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> AgentReport:
        raise RuntimeError("No A2A endpoint was supplied; use the GA Responses adapter")
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_responses_client.py -q`

Expected: `1 passed`.

### Task 4: Universe provider and fail-closed financial guardrails

**Files:**
- Create: `src/agent_orchestration/universe.py`
- Create: `src/agent_orchestration/guardrails.py`
- Create: `config/universe.example.json`
- Test: `tests/unit/test_guardrails.py`

**Interfaces:**
- Produces: `UniverseProvider`, `FileUniverseProvider`, `GuardrailResult`, `evaluate_guardrails`
- Consumes: ticker, asset type, data timestamp, risk settings

- [ ] **Step 1: Write failing fail-closed tests**

```python
from datetime import UTC, datetime, timedelta

from agent_orchestration.guardrails import evaluate_guardrails
from agent_orchestration.universe import UniverseSnapshot


def test_stale_universe_blocks_trade_candidate():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC) - timedelta(days=40),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )
    result = evaluate_guardrails("005930", snapshot, analysis_mode="analysis_only")
    assert result.trade_blocked is True
    assert "STALE_UNIVERSE" in result.block_reasons


def test_analysis_only_always_disables_execution():
    snapshot = UniverseSnapshot(
        as_of=datetime.now(UTC),
        max_age_days=7,
        instruments={"005930": "KOSPI200_STOCK"},
    )
    result = evaluate_guardrails("005930", snapshot, analysis_mode="analysis_only")
    assert result.execution_allowed is False
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_guardrails.py -q`

Expected: import failure for missing modules.

- [ ] **Step 3: Implement universe and guardrails**

```python
# universe.py
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class UniverseSnapshot(BaseModel):
    as_of: datetime
    max_age_days: int
    instruments: dict[str, str]

    @property
    def stale(self) -> bool:
        return (datetime.now(UTC) - self.as_of).days > self.max_age_days


class UniverseProvider(Protocol):
    async def get_snapshot(self) -> UniverseSnapshot:
        ...


class FileUniverseProvider:
    def __init__(self, path: Path):
        self._path = path

    async def get_snapshot(self) -> UniverseSnapshot:
        return UniverseSnapshot.model_validate(json.loads(self._path.read_text(encoding="utf-8")))
```

```python
# guardrails.py
from typing import Literal
from pydantic import BaseModel, Field
from agent_orchestration.universe import UniverseSnapshot


class GuardrailResult(BaseModel):
    trade_blocked: bool = True
    execution_allowed: bool = False
    block_reasons: list[str] = Field(default_factory=list)


def evaluate_guardrails(
    ticker: str | None,
    snapshot: UniverseSnapshot,
    *,
    analysis_mode: Literal["analysis_only", "paper_trading"],
) -> GuardrailResult:
    reasons: list[str] = []
    if snapshot.stale:
        reasons.append("STALE_UNIVERSE")
    if ticker is None or ticker not in snapshot.instruments:
        reasons.append("OUTSIDE_OR_UNKNOWN_UNIVERSE")
    if analysis_mode == "analysis_only":
        reasons.append("ANALYSIS_ONLY")
    return GuardrailResult(trade_blocked=True, execution_allowed=False, block_reasons=reasons)
```

`config/universe.example.json` content:

```json
{
  "as_of": "2000-01-01T00:00:00Z",
  "max_age_days": 7,
  "instruments": {}
}
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_guardrails.py -q`

Expected: `2 passed`.

### Task 5: Coordinator fan-out/fan-in with error isolation

**Files:**
- Create: `src/agent_orchestration/coordinator.py`
- Test: `tests/unit/test_coordinator.py`

**Interfaces:**
- Consumes: role-indexed `AgentClient`, `CoordinatorPlan`, `UniverseProvider`, `Settings`
- Produces: `AgentOrchestrator.run(query, ticker, company_name) -> OrchestrationResult`

- [ ] **Step 1: Write failing concurrency and isolation tests**

```python
import asyncio

import pytest

from agent_orchestration.contracts import AgentReport, AgentRequest
from agent_orchestration.coordinator import AgentOrchestrator


class FakeClient:
    def __init__(self, role: str, started: set[str], fail: bool = False):
        self.role = role
        self.started = started
        self.fail = fail

    async def invoke(self, request: AgentRequest, *, timeout_seconds: float, idempotency_key: str):
        self.started.add(self.role)
        await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("unavailable")
        if self.role == "MBGCoordinator" and "계획" in request.user_query:
            return AgentReport(
                agent=self.role,
                status="OK",
                confidence=1,
                details={
                    "request_id": request.request_id,
                    "selected_roles": ["FinancialReport", "News"],
                    "tasks": {"FinancialReport": "재무 분석", "News": "뉴스 분석"},
                },
            )
        return AgentReport(agent=self.role, status="OK", confidence=0.8, summary=self.role)


@pytest.mark.asyncio
async def test_specialists_run_concurrently_and_failure_is_isolated():
    started: set[str] = set()
    clients = {
        "MBGCoordinator": FakeClient("MBGCoordinator", started),
        "FinancialReport": FakeClient("FinancialReport", started, fail=True),
        "News": FakeClient("News", started),
    }
    result = await AgentOrchestrator(clients).run("삼성전자를 분석해줘", ticker="005930", company_name="삼성전자")
    outcomes = {item.role: item for item in result.specialists}
    assert outcomes["FinancialReport"].error_code == "AGENT_CALL_FAILED"
    assert outcomes["News"].report is not None
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_coordinator.py -q`

Expected: import failure for missing coordinator module.

- [ ] **Step 3: Implement coordinator**

```python
import asyncio
import json
from uuid import uuid4

from agent_orchestration.clients.base import AgentClient
from agent_orchestration.contracts import (
    AgentRequest,
    CoordinatorPlan,
    OrchestrationResult,
    SpecialistOutcome,
)


class AgentOrchestrator:
    def __init__(self, clients: dict[str, AgentClient], timeout_seconds: float = 120):
        self._clients = clients
        self._timeout = timeout_seconds

    async def _call_specialist(self, role: str, request: AgentRequest) -> SpecialistOutcome:
        try:
            report = await self._clients[role].invoke(
                request,
                timeout_seconds=self._timeout,
                idempotency_key=f"{request.request_id}:{role}",
            )
            return SpecialistOutcome(role=role, report=report)
        except Exception as exc:
            return SpecialistOutcome(role=role, error_code="AGENT_CALL_FAILED", error_message=type(exc).__name__)

    async def run(self, query: str, *, ticker: str | None = None, company_name: str | None = None) -> OrchestrationResult:
        request_id = str(uuid4())
        planner_request = AgentRequest(
            request_id=request_id,
            role="MBGCoordinator",
            user_query=f"계획 JSON을 details에 반환하라. 사용자 요청: {query}",
            ticker=ticker,
            company_name=company_name,
        )
        planning_report = await self._clients["MBGCoordinator"].invoke(
            planner_request,
            timeout_seconds=self._timeout,
            idempotency_key=f"{request_id}:plan",
        )
        plan = CoordinatorPlan.model_validate(planning_report.details)
        selected = [role for role in plan.selected_roles if role in self._clients and role != "MBGCoordinator"]
        outcomes = await asyncio.gather(
            *[
                self._call_specialist(
                    role,
                    AgentRequest(
                        request_id=request_id,
                        role=role,
                        user_query=plan.tasks.get(role, query),
                        ticker=ticker,
                        company_name=company_name,
                    ),
                )
                for role in selected
            ]
        )
        synthesis_request = AgentRequest(
            request_id=request_id,
            role="MBGCoordinator",
            user_query=(
                "전문 보고서를 검증·종합해 최종 JSON 보고서를 반환하라.\n"
                + json.dumps([item.model_dump(mode="json") for item in outcomes], ensure_ascii=False)
            ),
            ticker=ticker,
            company_name=company_name,
        )
        final_report = await self._clients["MBGCoordinator"].invoke(
            synthesis_request,
            timeout_seconds=self._timeout,
            idempotency_key=f"{request_id}:final",
        )
        failures = [item.role for item in outcomes if item.report is None]
        return OrchestrationResult(
            request_id=request_id,
            plan=plan,
            specialists=outcomes,
            final_report=final_report,
            trade_blocked=True,
            block_reasons=["ANALYSIS_ONLY"] + [f"MISSING_{role}" for role in failures],
        )
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_coordinator.py -q`

Expected: `1 passed`.

### Task 6: Secret-safe logging and CLI assembly

**Files:**
- Create: `src/agent_orchestration/telemetry.py`
- Create: `src/agent_orchestration/cli.py`
- Test: `tests/unit/test_telemetry.py`

**Interfaces:**
- Consumes: `Settings`, `DefaultAzureCredential`, `ResponsesAgentClient`, `AgentOrchestrator`
- Produces: `redact_event`, `async_main`, `main`

- [ ] **Step 1: Write failing redaction test**

```python
from agent_orchestration.telemetry import redact_event


def test_redaction_removes_tokens_and_endpoint_values():
    event = redact_event(None, None, {"access_token": "secret", "endpoint": "https://internal.invalid/path", "request_id": "r1"})
    assert event["access_token"] == "[REDACTED]"
    assert event["endpoint"] == "[REDACTED]"
    assert event["request_id"] == "r1"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_telemetry.py -q`

Expected: import failure for missing telemetry module.

- [ ] **Step 3: Implement logging and CLI lifecycle**

```python
# telemetry.py
import structlog


SENSITIVE_KEYS = {"access_token", "authorization", "api_key", "resource_key", "connection_string", "endpoint"}


def redact_event(logger, method_name, event_dict):
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging():
    structlog.configure(
        processors=[redact_event, structlog.processors.TimeStamper(fmt="iso"), structlog.processors.JSONRenderer()]
    )
```

```python
# cli.py
import argparse
import asyncio
import json

import httpx
from azure.identity.aio import DefaultAzureCredential

from agent_orchestration.clients.responses import ResponsesAgentClient
from agent_orchestration.config import Role, get_settings
from agent_orchestration.coordinator import AgentOrchestrator
from agent_orchestration.telemetry import configure_logging


ROLES: tuple[Role, ...] = (
    "MBGCoordinator",
    "FinancialReport",
    "News",
    "MarketResearch",
    "Macro",
    "AssetManager",
)


async def async_main(query: str, ticker: str | None, company_name: str | None) -> int:
    settings = get_settings()
    configure_logging()
    async with DefaultAzureCredential() as credential, httpx.AsyncClient() as http:
        clients = {
            role: ResponsesAgentClient(settings.endpoint_for(role), credential, http)
            for role in ROLES
        }
        result = await AgentOrchestrator(clients).run(query, ticker=ticker, company_name=company_name)
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--ticker")
    parser.add_argument("--company-name")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(async_main(args.query, args.ticker, args.company_name)))
```

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_telemetry.py -q`

Expected: `1 passed`.

### Task 7: Mock end-to-end integration and live Foundry smoke tests

**Files:**
- Create: `tests/integration/test_mock_orchestration.py`
- Create: `tests/integration/test_live_foundry.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: public CLI/coordinator/client interfaces
- Produces: offline end-to-end evidence and opt-in live connectivity evidence

- [ ] **Step 1: Add mock end-to-end integration test**

```python
import pytest

from agent_orchestration.contracts import AgentReport, AgentRequest
from agent_orchestration.coordinator import AgentOrchestrator


class IntegrationClient:
    def __init__(self, role: str):
        self.role = role

    async def invoke(self, request: AgentRequest, *, timeout_seconds: float, idempotency_key: str):
        if self.role == "MBGCoordinator" and "계획" in request.user_query:
            return AgentReport(
                agent=self.role,
                status="OK",
                confidence=1,
                details={
                    "request_id": request.request_id,
                    "ticker": request.ticker,
                    "company_name": request.company_name,
                    "selected_roles": ["FinancialReport", "News", "MarketResearch", "Macro", "AssetManager"],
                    "tasks": {
                        "FinancialReport": "재무 분석",
                        "News": "뉴스 분석",
                        "MarketResearch": "산업 분석",
                        "Macro": "거시 분석",
                        "AssetManager": "포트폴리오 분석",
                    },
                },
            )
        return AgentReport(agent=self.role, status="OK", confidence=0.8, summary=f"{self.role} 결과")


@pytest.mark.asyncio
async def test_complete_six_agent_flow_without_network():
    roles = ["MBGCoordinator", "FinancialReport", "News", "MarketResearch", "Macro", "AssetManager"]
    result = await AgentOrchestrator({role: IntegrationClient(role) for role in roles}).run(
        "삼성전자를 분석해줘", ticker="005930", company_name="삼성전자"
    )
    assert len(result.specialists) == 5
    assert result.final_report.agent == "MBGCoordinator"
    assert result.trade_blocked is True
```

- [ ] **Step 2: Add opt-in live connectivity test**

```python
import os

import httpx
import pytest
from azure.identity.aio import DefaultAzureCredential

from agent_orchestration.clients.responses import ResponsesAgentClient
from agent_orchestration.config import Settings
from agent_orchestration.contracts import AgentRequest


ROLES = ["MBGCoordinator", "FinancialReport", "News", "MarketResearch", "Macro", "AssetManager"]


@pytest.mark.live
@pytest.mark.asyncio
async def test_all_configured_foundry_agents_are_reachable():
    if os.getenv("RUN_LIVE_FOUNDRY_TESTS", "false").lower() != "true":
        pytest.skip("set RUN_LIVE_FOUNDRY_TESTS=true to run live Foundry tests")
    settings = Settings()
    async with DefaultAzureCredential() as credential, httpx.AsyncClient() as http:
        for role in ROLES:
            report = await ResponsesAgentClient(settings.endpoint_for(role), credential, http).invoke(
                AgentRequest(
                    request_id=f"live-{role}",
                    role=role,
                    user_query="연결 점검이다. 외부 도구나 주문을 실행하지 말고, status와 summary를 포함한 JSON만 반환하라.",
                ),
                timeout_seconds=120,
                idempotency_key=f"live-{role}",
            )
            assert report.agent in {role, settings.agent_name_for(role)}
```

- [ ] **Step 3: Run offline integration test**

Run: `python -m pytest tests/integration/test_mock_orchestration.py -q`

Expected: `1 passed`.

- [ ] **Step 4: Verify live test is skipped by default**

Run: `python -m pytest tests/integration/test_live_foundry.py -q`

Expected: `1 skipped`.

- [ ] **Step 5: Run live test with terminal-only environment values**

Run in the authenticated local terminal after setting endpoint values without saving them to files:

```powershell
$env:RUN_LIVE_FOUNDRY_TESTS = "true"
python -m pytest tests/integration/test_live_foundry.py -m live -v
```

Expected: six role checks pass, or each failure reports only status category and exception type without exposing token or endpoint.

### Task 8: Documentation, import verification, secret scan, and final validation

**Files:**
- Create: `README.md`
- Modify only if verification requires: files created in Tasks 1-7

**Interfaces:**
- Consumes: all project commands and environment variables
- Produces: reproducible operator instructions and verification evidence

- [ ] **Step 1: Write README with exact operator workflow**

README must include these commands:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
az login
$env:FOUNDRY_PROJECT_ENDPOINT = Read-Host "Foundry project endpoint"
agent-orchestrator "삼성전자를 분석해줘" --ticker 005930 --company-name 삼성전자
python -m pytest -m "not live" -q
$env:RUN_LIVE_FOUNDRY_TESTS = "true"
python -m pytest -m live -v
```

README must state:

- resource key, identity ID, blueprint ID and tokens are not used.
- Responses is the GA default path.
- A2A remains disabled until endpoint support and operational approval are verified.
- `ANALYSIS_MODE=analysis_only` prevents execution and proposed orders remain disabled.
- `.env.example` contains no real endpoint and `.env` is ignored.
- RBAC and Running/Enabled agent state are live-test prerequisites.

- [ ] **Step 2: Install in a clean virtual environment and verify imports**

Run:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
python -c "import azure.ai.projects; import azure.identity; import pydantic; import httpx; import agent_orchestration"
```

Expected: all commands exit 0 without import errors.

- [ ] **Step 3: Run complete offline verification**

Run: `python -m pytest -m "not live" -q`

Expected: all unit and mock integration tests pass, with live tests deselected.

- [ ] **Step 4: Scan generated files for forbidden secret patterns and supplied identifiers**

Run from project root:

```powershell
rg -n -i "api[_ -]?key|resource[_ -]?key|access[_ -]?token|client[_ -]?secret|<SUPPLIED_AGENT_IDENTIFIER>|<OPERATING_ENDPOINT_HOST>" . -g "!*.md" -g "!.venv/**"
```

Expected: no matches in source, configuration examples, tests, or logs. Replace the two angle-bracket placeholders only in a terminal command when performing a local manual scan; never store supplied identifiers or operating endpoints in this repository. Documentation may mention forbidden field names as policy text but must not contain real values.

- [ ] **Step 5: Run actual Foundry connectivity test**

Run only after `az login`, RBAC confirmation, and terminal-only endpoint setup:

```powershell
$env:RUN_LIVE_FOUNDRY_TESTS = "true"
python -m pytest tests/integration/test_live_foundry.py -m live -v
```

Expected: all six agents return schema-valid reports. If an agent is stopped, disabled, unauthorized, or returns invalid JSON, record the sanitized failure and do not weaken validation.

- [ ] **Step 6: Run the analysis-only CLI smoke test**

Run:

```powershell
agent-orchestrator "삼성전자를 분석해줘" --ticker 005930 --company-name 삼성전자
```

Expected: final JSON has `trade_blocked: true`; no order endpoint is called.

- [ ] **Step 7: Record final evidence**

Create `docs/verification-report.md` containing:

```markdown
# Verification Report

## Environment

- Python version: command output recorded without user or machine identifiers
- azure-ai-projects version: command output recorded
- Authentication: Entra ID through DefaultAzureCredential
- Analysis mode: analysis_only

## Offline verification

- Import verification: PASS or FAIL
- Unit tests: pass/fail counts
- Mock integration: pass/fail counts
- Secret scan: PASS or FAIL

## Live Foundry verification

- MBGCoordinator: PASS, FAIL, or NOT_RUN
- FinancialReport: PASS, FAIL, or NOT_RUN
- News: PASS, FAIL, or NOT_RUN
- MarketResearch: PASS, FAIL, or NOT_RUN
- Macro: PASS, FAIL, or NOT_RUN
- AssetManager: PASS, FAIL, or NOT_RUN

## Safety verification

- Real order execution path present: NO
- execution_allowed: false
- trade_blocked: true
```

Replace each status with observed results; do not include endpoint, identity, blueprint, token, account, tenant, subscription, or request payload values.

---

## Official references to verify during execution

- Microsoft Learn: Azure AI Projects Python SDK 2.4+ authentication and `get_openai_client`
- PyPI: `azure-ai-projects` 2.5.0 GA release history
- Microsoft Learn: stable agent Responses endpoint and Entra authorization
- Microsoft Learn: A2A protocol support and activation requirements

## Execution notes

- The destination is not currently a Git repository, so per-task commit steps are omitted. If the user initializes Git before execution, commit after each task with `test`, `feat`, or `docs` prefixes.
- The supplied agent identity and blueprint values are not required by the runtime design.
- The supplied resource key is treated as compromised, must be rotated, and is never used.
