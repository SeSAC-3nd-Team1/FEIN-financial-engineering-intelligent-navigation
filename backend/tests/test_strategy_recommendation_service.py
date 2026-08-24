import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.errors import ServiceError
from app.models import InvestorProfileAssessment, Strategy, StrategyRecommendation, StrategyRecommendationItem
from app.schemas.api import StrategyRecommendationAnalysisResult
from app.services.strategy_recommendation import StrategyRecommendationService


VALID_RESULT = StrategyRecommendationAnalysisResult(recommendations=[
    {"strategy_id": "value", "rank": 1, "score": 0.84, "match_level": "BEST", "reason": "균형 성향과 맞습니다.", "caution": "회복에 시간이 필요합니다."},
    {"strategy_id": "low", "rank": 2, "score": 0.73, "match_level": "GOOD", "reason": "안정성 선호와 맞습니다.", "caution": "상승장에서 뒤처질 수 있습니다."},
    {"strategy_id": "momentum", "rank": 3, "score": 0.51, "match_level": "CAUTION", "reason": "수익 성향과 일부 맞습니다.", "caution": "변동성이 높을 수 있습니다."},
])


def profile() -> InvestorProfileAssessment:
    return InvestorProfileAssessment(
        id=uuid4(), user_id=7, questionnaire_version="v1", analysis_version="v1",
        profile_type="중립투자형", stability=3, return_seeking=3, horizon=4,
        tendency_line="균형 성향", description="균형 성향입니다.", analysis_summary=["중장기"],
        model_version="profile-v1", prompt_version="v1", created_at=datetime.now(UTC),
    )


def catalog() -> list[Strategy]:
    return [
        Strategy(id="low", name="저변동성", description="저변동성", risk_level="MEDIUM", rebalance_cycle="MONTHLY", rule_config={}, is_active=True),
        Strategy(id="value", name="가치", description="가치", risk_level="MEDIUM", rebalance_cycle="QUARTERLY", rule_config={}, is_active=True),
        Strategy(id="momentum", name="모멘텀", description="모멘텀", risk_level="HIGH", rebalance_cycle="MONTHLY", rule_config={}, is_active=True),
    ]


class FakeClient:
    def __init__(self, result=VALID_RESULT) -> None:
        self.result = result
        self.calls = 0

    async def recommend(self, _assessment, _strategies):
        self.calls += 1
        return self.result


class FakeSession:
    def __init__(self, commit_error=None) -> None:
        self.added = []
        self.commits = 0
        self.commit_error = commit_error
        self.rollbacks = 0

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollbacks += 1


class FakeRepo:
    def __init__(
        self,
        session,
        assessment,
        *,
        consent=True,
        existing=None,
        strategies=None,
        existing_items=None,
        recommendation_lookup_results=None,
    ) -> None:
        self.session = session
        self.assessment = assessment
        self.consent = consent
        self.existing = existing
        self.strategies = catalog() if strategies is None else strategies
        self.existing_items = existing_items
        self.recommendation_lookup_results = recommendation_lookup_results
        self.recommendation_lookup_inputs = []

    def has_ai_personalization_consent(self, _user_id): return self.consent
    def assessment_for_user(self, assessment_id, user_id):
        return self.assessment if self.assessment and self.assessment.id == assessment_id and self.assessment.user_id == user_id else None
    def recommendation_for_input(
        self,
        assessment_id,
        model_version,
        prompt_version,
        strategy_catalog_version,
        dataset_version,
    ):
        lookup_input = (
            assessment_id,
            model_version,
            prompt_version,
            strategy_catalog_version,
            dataset_version,
        )
        self.recommendation_lookup_inputs.append(lookup_input)
        if self.recommendation_lookup_results is not None:
            return self.recommendation_lookup_results.pop(0)
        if self.existing is None:
            return None
        existing_input = (
            self.existing.assessment_id,
            self.existing.model_version,
            self.existing.prompt_version,
            self.existing.strategy_catalog_version,
            self.existing.dataset_version,
        )
        return self.existing if existing_input == lookup_input else None
    def active_strategies(self): return self.strategies
    def latest_recommendation(self, _user_id): return self.existing
    def recommendation_items(self, recommendation_id):
        if self.existing_items is not None:
            return self.existing_items
        return sorted(
            [item for item in self.session.added if isinstance(item, StrategyRecommendationItem) and item.recommendation_id == recommendation_id],
            key=lambda item: item.rank,
        )


def make_service(
    client,
    assessment,
    *,
    dataset_version="financial-8y-v1",
    commit_error=None,
    **repo_kwargs,
):
    session = FakeSession(commit_error=commit_error)
    service = StrategyRecommendationService(
        session, client, model_version="recommendation-v1", prompt_version="v1",
        strategy_catalog_version="v1", dataset_version=dataset_version,
    )
    service.repo = FakeRepo(session, assessment, **repo_kwargs)
    return service, session


def test_recommend_persists_ranked_result_and_versions() -> None:
    assessment = profile()
    client = FakeClient()
    service, session = make_service(client, assessment)

    response = asyncio.run(service.recommend(7, assessment.id))

    assert response.primary.strategy_id == "value"
    assert [item.strategy_id for item in response.alternatives] == ["low", "momentum"]
    assert response.dataset_version == "financial-8y-v1"
    assert client.calls == 1
    assert session.commits == 1
    assert len([item for item in session.added if isinstance(item, StrategyRecommendationItem)]) == 3


def test_recommend_returns_existing_result_without_ai_call() -> None:
    assessment = profile()
    recommendation = StrategyRecommendation(
        id=uuid4(), assessment_id=assessment.id, model_version="recommendation-v1",
        prompt_version="v1", strategy_catalog_version="v1", dataset_version="financial-8y-v1",
        created_at=datetime.now(UTC),
    )
    items = [
        StrategyRecommendationItem(
            recommendation_id=recommendation.id, strategy_id=item.strategy_id, rank=item.rank,
            score=Decimal(str(item.score)), match_level=item.match_level, reason=item.reason, caution=item.caution,
        )
        for item in VALID_RESULT.recommendations
    ]
    client = FakeClient()
    service, session = make_service(client, assessment, existing=recommendation, existing_items=items)

    response = asyncio.run(service.recommend(7, assessment.id))

    assert response.recommendation_id == recommendation.id
    assert client.calls == 0
    assert session.commits == 0


def test_recommend_does_not_reuse_result_from_previous_dataset_version() -> None:
    assessment = profile()
    previous = StrategyRecommendation(
        id=uuid4(), assessment_id=assessment.id, model_version="recommendation-v1",
        prompt_version="v1", strategy_catalog_version="v1", dataset_version="financial-8y-v1",
        created_at=datetime.now(UTC),
    )
    client = FakeClient()
    service, session = make_service(
        client,
        assessment,
        dataset_version="financial-8y-v2",
        existing=previous,
    )

    response = asyncio.run(service.recommend(7, assessment.id))

    assert response.recommendation_id != previous.id
    assert response.dataset_version == "financial-8y-v2"
    assert client.calls == 1
    assert session.commits == 1
    assert service.repo.recommendation_lookup_inputs[0][-1] == "financial-8y-v2"


def test_integrity_error_requery_uses_dataset_version() -> None:
    assessment = profile()
    concurrent = StrategyRecommendation(
        id=uuid4(), assessment_id=assessment.id, model_version="recommendation-v1",
        prompt_version="v1", strategy_catalog_version="v1", dataset_version="financial-8y-v2",
        created_at=datetime.now(UTC),
    )
    items = [
        StrategyRecommendationItem(
            recommendation_id=concurrent.id, strategy_id=item.strategy_id, rank=item.rank,
            score=Decimal(str(item.score)), match_level=item.match_level,
            reason=item.reason, caution=item.caution,
        )
        for item in VALID_RESULT.recommendations
    ]
    service, session = make_service(
        FakeClient(),
        assessment,
        dataset_version="financial-8y-v2",
        commit_error=IntegrityError("insert", {}, Exception("duplicate")),
        existing_items=items,
        recommendation_lookup_results=[None, concurrent],
    )

    response = asyncio.run(service.recommend(7, assessment.id))

    assert response.recommendation_id == concurrent.id
    assert session.rollbacks == 1
    assert [lookup[-1] for lookup in service.repo.recommendation_lookup_inputs] == [
        "financial-8y-v2",
        "financial-8y-v2",
    ]


@pytest.mark.parametrize("result", [
    StrategyRecommendationAnalysisResult(recommendations=[
        {"strategy_id": "unknown", "rank": 1, "score": 0.9, "match_level": "BEST", "reason": "잘 맞음", "caution": "주의"},
        {"strategy_id": "low", "rank": 2, "score": 0.8, "match_level": "GOOD", "reason": "잘 맞음", "caution": "주의"},
        {"strategy_id": "value", "rank": 3, "score": 0.7, "match_level": "CAUTION", "reason": "잘 맞음", "caution": "주의"},
    ]),
    StrategyRecommendationAnalysisResult(recommendations=[
        {"strategy_id": "low", "rank": 1, "score": 0.7, "match_level": "BEST", "reason": "잘 맞음", "caution": "주의"},
        {"strategy_id": "value", "rank": 2, "score": 0.8, "match_level": "GOOD", "reason": "잘 맞음", "caution": "주의"},
        {"strategy_id": "momentum", "rank": 3, "score": 0.6, "match_level": "CAUTION", "reason": "잘 맞음", "caution": "주의"},
    ]),
])
def test_recommend_rejects_invalid_model_semantics(result) -> None:
    assessment = profile()
    service, session = make_service(FakeClient(result), assessment)

    with pytest.raises(ServiceError) as raised:
        asyncio.run(service.recommend(7, assessment.id))

    assert raised.value.code == "AI_INVALID_RECOMMENDATION"
    assert session.added == []


def test_recommend_rejects_profile_owned_by_another_user() -> None:
    assessment = profile()
    client = FakeClient()
    service, _ = make_service(client, assessment)

    with pytest.raises(ServiceError) as raised:
        asyncio.run(service.recommend(8, assessment.id))

    assert raised.value.code == "INVESTOR_PROFILE_NOT_FOUND"
    assert client.calls == 0
