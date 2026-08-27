import pytest
from pydantic import ValidationError

from agent_orchestration.contracts import AgentReport, extract_json_object


def test_extract_json_object_from_fenced_response():
    raw = '결과입니다.\n```json\n{"agent":"News","status":"OK","confidence":0.8}\n```'

    assert extract_json_object(raw)["agent"] == "News"


def test_extract_json_object_from_surrounding_prose():
    raw = '다음 결과를 확인하세요: {"status":"OK","facts":["verified"]} 감사합니다.'

    assert extract_json_object(raw)["facts"] == ["verified"]


def test_extract_json_object_rejects_missing_object():
    with pytest.raises(ValueError, match="valid JSON object"):
        extract_json_object("응답에 JSON이 없습니다.")


def test_agent_report_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        AgentReport(agent="News", status="OK", confidence=1.2)
