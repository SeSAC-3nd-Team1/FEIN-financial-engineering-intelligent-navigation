"""Runtime controls for the four non-System-Instruction agent layers.

These profiles do not overwrite Foundry System Instructions. They constrain
caller-side tools, knowledge freshness, conversation memory, and guardrails.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_orchestration.config import Role


class ToolLayer(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed_tools: tuple[str, ...]
    read_only: bool = True
    timeout_seconds: float = Field(ge=1, le=180)
    max_retries: int = Field(ge=0, le=3)
    max_parallel_calls: int = Field(ge=1, le=8)
    max_output_tokens: int = Field(ge=256, le=32768)
    news_lookback_days: int = Field(default=30, ge=1, le=365)
    financial_years: int = Field(default=8, ge=1, le=20)
    financial_quarters: int = Field(default=12, ge=1, le=40)
    market_data_max_age_seconds: int = Field(default=5, ge=1, le=300)


class KnowledgeLayer(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_priority: tuple[str, ...]
    point_in_time_only: bool = True
    require_source_attribution: bool = True
    minimum_independent_sources: int = Field(default=2, ge=1, le=5)
    conflict_policy: Literal["ABSTAIN", "PARTIAL", "NO_TRADE"] = "NO_TRADE"
    stale_policy: Literal["ABSTAIN", "PARTIAL", "NO_TRADE"] = "NO_TRADE"


class MemoryLayer(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    retention_days: int = Field(default=180, ge=0, le=365)
    conversation_scope: Literal["REQUEST", "SESSION"] = "REQUEST"
    persist_analysis_results: bool = False
    store_sensitive_financial_data: bool = False
    store_credentials: bool = False
    user_delete_enabled: bool = True


class GuardrailLayer(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_allowed: Literal[False] = False
    allowed_universe: tuple[str, ...] = ("KOSPI200", "APPROVED_KR_ETF", "CASH")
    max_single_position_pct: float = Field(default=0.10, ge=0, le=1)
    max_sector_exposure_pct: float = Field(default=0.25, ge=0, le=1)
    min_cash_pct: float = Field(default=0.10, ge=0, le=1)
    max_turnover_pct: float = Field(default=0.25, ge=0, le=1)
    rebalance_threshold_pct: float = Field(default=0.05, ge=0, le=1)
    max_daily_loss_pct: float = Field(default=0.10, ge=0, le=1)
    max_portfolio_drawdown_pct: float = Field(default=0.20, ge=0, le=1)
    fixed_loss_review_pct: float = Field(default=-0.15, ge=-1, le=0)
    trailing_drawdown_review_pct: float = Field(default=-0.30, ge=-1, le=0)
    atr_review_multiplier: float = Field(default=3.0, gt=0, le=10)
    max_daily_order_amount_krw: int = Field(default=100_000_000, ge=0)
    max_single_order_amount_krw: int = Field(default=20_000_000, ge=0)
    max_daily_order_count: int = Field(default=10, ge=0)
    approval_ttl_minutes: int = Field(default=5, ge=1, le=60)
    fail_closed: bool = True


class AgentLayerProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    tools: ToolLayer
    knowledge: KnowledgeLayer
    memory: MemoryLayer = MemoryLayer()
    guardrails: GuardrailLayer = GuardrailLayer()

    def runtime_context(self) -> dict:
        return self.model_dump(mode="json", exclude={"role"})


def _profile(role: Role, tools: tuple[str, ...], timeout: float, retries: int,
             sources: tuple[str, ...], max_output_tokens: int = 4096) -> AgentLayerProfile:
    return AgentLayerProfile(
        role=role,
        tools=ToolLayer(
            allowed_tools=tools,
            timeout_seconds=timeout,
            max_retries=retries,
            max_parallel_calls=4 if role == "MBGCoordinator" else 2,
            max_output_tokens=max_output_tokens,
        ),
        knowledge=KnowledgeLayer(source_priority=sources),
    )


DEFAULT_LAYER_PROFILES: dict[Role, AgentLayerProfile] = {
    "MBGCoordinator": _profile(
        "MBGCoordinator", ("agent_reports", "portfolio_read", "market_read"), 120, 1,
        ("BROKER_OMS", "KRX", "DART", "BOK_GOV", "CORPORATE_IR"), 8192,
    ),
    "FinancialReport": _profile(
        "FinancialReport", ("financial_data_read", "dart_read"), 120, 2,
        ("DART", "AUDIT_REPORT", "KRX", "CORPORATE_IR", "CONSENSUS"),
    ),
    "News": _profile(
        "News", ("web_search_read", "news_read", "disclosure_read"), 120, 2,
        ("DART", "KRX", "CORPORATE_IR", "NEWS_PRIMARY", "NEWS_SECONDARY"),
        16384,
    ),
    "MarketResearch": _profile(
        "MarketResearch", ("web_search_read", "industry_data_read"), 120, 2,
        ("GOV_INDUSTRY", "KRX", "CORPORATE_IR", "MARKET_RESEARCH"),
        16384,
    ),
    "Macro": _profile(
        "Macro", ("macro_data_read", "web_search_read"), 120, 2,
        ("BOK_ECOS", "KOSTAT", "MOEF", "CUSTOMS", "CENTRAL_BANKS"),
        8192,
    ),
    "AssetManager": _profile(
        "AssetManager", ("portfolio_read", "market_read", "agent_reports"), 120, 1,
        ("BROKER_OMS", "APPROVED_TARGETS", "AGENT_REPORTS"),
    ),
}


class LayerController:
    def __init__(self, profiles: dict[Role, AgentLayerProfile] | None = None) -> None:
        self._profiles = profiles or DEFAULT_LAYER_PROFILES

    def profile_for(self, role: Role) -> AgentLayerProfile:
        return self._profiles[role]

    def request_context(self, role: Role) -> dict:
        return {"runtime_layers": self.profile_for(role).runtime_context()}
