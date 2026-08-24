"""Investor-profile answer validation and AI analysis orchestration."""

from app.core.errors import ServiceError
from app.domain.investor_profile.questionnaire import (
    QuestionnaireValidationError,
    resolve_investor_answers,
)
from app.integrations.ai.investor_profile_client import InvestorProfileAIClient
from app.schemas.api import InvestorProfileAnalyzeRequest, InvestorProfileResponse


class InvestorProfileService:
    def __init__(self, client: InvestorProfileAIClient) -> None:
        self.client = client

    async def analyze(self, request: InvestorProfileAnalyzeRequest) -> InvestorProfileResponse:
        try:
            answers = resolve_investor_answers(
                request.questionnaire_version,
                ((item.question_id, item.option_id) for item in request.answers),
            )
        except QuestionnaireValidationError as exc:
            raise ServiceError(exc.code, str(exc), 400) from exc

        result = await self.client.analyze(request.questionnaire_version, answers)
        return InvestorProfileResponse(
            questionnaire_version=request.questionnaire_version,
            **result.model_dump(),
        )
