"""Investor-profile answer validation, AI analysis, and persistence."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.errors import ServiceError
from app.domain.investor_profile.questionnaire import (
    QuestionnaireValidationError,
    resolve_investor_answers,
)
from app.integrations.ai.investor_profile_client import InvestorProfileAIClient
from app.models import InvestorProfileAssessment
from app.repositories import RecommendationRepository
from app.schemas.api import InvestorProfileAnalyzeRequest, InvestorProfileResponse


class InvestorProfileService:
    def __init__(
        self,
        session: Session,
        client: InvestorProfileAIClient,
        *,
        model_version: str,
        prompt_version: str,
    ) -> None:
        self.session = session
        self.client = client
        self.model_version = model_version
        self.prompt_version = prompt_version
        self.repo = RecommendationRepository(session)

    @staticmethod
    def _response(assessment: InvestorProfileAssessment) -> InvestorProfileResponse:
        return InvestorProfileResponse(
            assessment_id=assessment.id,
            questionnaire_version=assessment.questionnaire_version,
            analysis_version=assessment.analysis_version,
            profile_type=assessment.profile_type,
            tendency_line=assessment.tendency_line,
            description=assessment.description,
            traits={
                "stability": assessment.stability,
                "return_seeking": assessment.return_seeking,
                "horizon": assessment.horizon,
            },
            analysis_summary=assessment.analysis_summary,
            model_version=assessment.model_version,
            created_at=assessment.created_at,
        )

    def _require_ai_consent(self, user_id: int) -> None:
        if not self.repo.has_ai_personalization_consent(user_id):
            raise ServiceError(
                "AI_PERSONALIZATION_CONSENT_REQUIRED",
                "AI 기반 맞춤형 서비스 이용 동의가 필요합니다.",
                403,
            )

    async def analyze(self, user_id: int, request: InvestorProfileAnalyzeRequest) -> InvestorProfileResponse:
        self._require_ai_consent(user_id)
        try:
            answers = resolve_investor_answers(
                request.questionnaire_version,
                ((item.question_id, item.option_id) for item in request.answers),
            )
        except QuestionnaireValidationError as exc:
            raise ServiceError(exc.code, str(exc), 400) from exc

        result = await self.client.analyze(request.questionnaire_version, answers)
        assessment = InvestorProfileAssessment(
            id=uuid4(),
            user_id=user_id,
            questionnaire_version=request.questionnaire_version,
            analysis_version="v1",
            profile_type=result.profile_type,
            stability=result.traits.stability,
            return_seeking=result.traits.return_seeking,
            horizon=result.traits.horizon,
            tendency_line=result.tendency_line,
            description=result.description,
            analysis_summary=result.analysis_summary,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            created_at=datetime.now(UTC),
        )
        try:
            self.session.add(assessment)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._response(assessment)

    def latest(self, user_id: int) -> InvestorProfileResponse:
        assessment = self.repo.latest_assessment(user_id)
        if not assessment:
            raise ServiceError("INVESTOR_PROFILE_NOT_FOUND", "저장된 투자성향을 찾을 수 없습니다.", 404)
        return self._response(assessment)
