import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.errors import ServiceError
from app.schemas.api import InvestorProfileAnalyzeRequest
from app.services.investor_profile import InvestorProfileService


VALID_ANSWERS = [
    ("investment_experience", "1_to_3_years"),
    ("product_knowledge", "basic"),
    ("investment_horizon", "3_to_5_years"),
    ("investment_goal", "retirement"),
    ("loss_tolerance", "loss_20_percent"),
    ("risk_return_preference", "balanced"),
    ("investable_asset_ratio", "10_to_30_percent"),
    ("annual_income", "30m_to_50m"),
]


def make_request(
    answers: list[tuple[str, str]] | None = None,
    *,
    version: str = "v1",
) -> InvestorProfileAnalyzeRequest:
    return InvestorProfileAnalyzeRequest(
        questionnaire_version=version,
        answers=[{"question_id": question_id, "option_id": option_id} for question_id, option_id in (answers or VALID_ANSWERS)],
    )


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


class FakeRepo:
    def __init__(self, consent: bool = True) -> None:
        self.consent = consent

    def has_ai_personalization_consent(self, _user_id):
        return self.consent


def make_service(*, consent: bool = True):
    session = FakeSession()
    service = InvestorProfileService(session)
    service.repo = FakeRepo(consent)
    return service, session


def test_analyze_resolves_server_catalog_and_returns_versioned_result() -> None:
    service, session = make_service()
    result = asyncio.run(service.analyze(7, make_request()))

    assert isinstance(result.assessment_id, UUID)
    assert result.profile_type == "중립투자형"
    assert result.risk_score == 51
    assert result.questionnaire_version == "v1"
    assert result.analysis_version == "v2"
    assert result.traits.stability == 3
    assert result.traits.return_seeking == 3
    assert result.traits.horizon == 4
    assert result.model_version == "risk-score-v1"
    assert session.committed is True
    assert session.added[0].user_id == 7
    assert session.added[0].risk_score == 51


@pytest.mark.parametrize(
    ("payload", "expected_code"),
    [
        (make_request(version="v2"), "INVALID_QUESTIONNAIRE_VERSION"),
        (make_request(VALID_ANSWERS[:-1]), "INVALID_INVESTOR_ANSWERS"),
        (make_request(VALID_ANSWERS[:-1] + [VALID_ANSWERS[0]]), "INVALID_INVESTOR_ANSWERS"),
        (
            make_request([
                *((question_id, option_id) for question_id, option_id in VALID_ANSWERS[:-1]),
                ("annual_income", "not-an-option"),
            ]),
            "INVALID_INVESTOR_ANSWERS",
        ),
    ],
)
def test_analyze_rejects_invalid_questionnaire_answers(payload, expected_code) -> None:
    service, session = make_service()
    with pytest.raises(ServiceError) as raised:
        asyncio.run(service.analyze(7, payload))

    assert raised.value.code == expected_code
    assert session.added == []


def test_analyze_requires_ai_personalization_consent() -> None:
    service, session = make_service(consent=False)

    with pytest.raises(ServiceError) as raised:
        asyncio.run(service.analyze(7, make_request()))

    assert raised.value.code == "AI_PERSONALIZATION_CONSENT_REQUIRED"
    assert raised.value.status_code == 403
    assert session.added == []
