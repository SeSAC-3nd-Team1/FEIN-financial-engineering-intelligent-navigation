from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


Role = Literal[
    "MBGCoordinator",
    "FinancialReport",
    "News",
    "MarketResearch",
    "Macro",
    "AssetManager",
]


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
