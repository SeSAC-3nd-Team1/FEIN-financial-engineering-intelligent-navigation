import pytest
from pydantic import ValidationError

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
