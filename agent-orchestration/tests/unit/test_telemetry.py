from agent_orchestration.telemetry import redact_event


def test_redaction_removes_tokens_and_endpoint_values():
    event = redact_event(
        None,
        None,
        {
            "access_token": "secret",
            "endpoint": "https://internal.invalid/path",
            "request_id": "r1",
        },
    )

    assert event["access_token"] == "[REDACTED]"
    assert event["endpoint"] == "[REDACTED]"
    assert event["request_id"] == "r1"


def test_redaction_handles_nested_sensitive_fields_without_mutating_input():
    event = {"credentials": {"Authorization": "Bearer secret", "role": "News"}}

    redacted = redact_event(None, None, event)

    assert redacted == {
        "credentials": {"Authorization": "[REDACTED]", "role": "News"}
    }
    assert event["credentials"]["Authorization"] == "Bearer secret"
