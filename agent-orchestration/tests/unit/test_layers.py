from agent_orchestration.layers import LayerController


def test_non_system_layers_are_role_scoped_and_fail_closed():
    layers = LayerController()
    financial = layers.profile_for("FinancialReport")
    asset = layers.profile_for("AssetManager")

    assert "financial_data_read" in financial.tools.allowed_tools
    assert "portfolio_read" not in financial.tools.allowed_tools
    assert "portfolio_read" in asset.tools.allowed_tools
    assert financial.guardrails.execution_allowed is False
    assert financial.tools.timeout_seconds == 120
    assert asset.memory.store_sensitive_financial_data is False
    assert "instructions" not in layers.request_context("Macro")["runtime_layers"]
