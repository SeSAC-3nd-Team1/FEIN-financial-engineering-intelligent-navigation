import pytest
from pydantic import ValidationError

from agent_orchestration.config import Settings


def test_settings_use_fein_agent_project_endpoint_by_default(monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)

    settings = Settings()

    assert str(settings.foundry_project_endpoint).rstrip("/") == (
        "https://fein-agent.services.ai.azure.com/api/projects/proj-default"
    )


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


def test_empty_chatbot_registry_environment_values_are_unset(monkeypatch):
    monkeypatch.setenv("CHATBOT_REGISTRY_PATH", "")
    monkeypatch.setenv("CHATBOT_REGISTRY_JSON", "")

    settings = Settings()

    assert settings.chatbot_registry_path is None
    assert settings.chatbot_registry_json is None
