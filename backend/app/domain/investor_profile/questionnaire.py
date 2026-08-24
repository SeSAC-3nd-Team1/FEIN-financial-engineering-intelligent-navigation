"""Versioned investor-profile questionnaire catalog and answer validation."""

from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True)
class QuestionnaireOption:
    id: str
    label: str


@dataclass(frozen=True)
class QuestionnaireQuestion:
    id: str
    prompt: str
    options: tuple[QuestionnaireOption, ...]


@dataclass(frozen=True)
class ResolvedInvestorAnswer:
    question_id: str
    question: str
    option_id: str
    answer: str


class QuestionnaireValidationError(ValueError):
    """Raised when submitted answers do not match the server questionnaire."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


QUESTIONNAIRE_V1 = (
    QuestionnaireQuestion(
        id="investment_experience",
        prompt="투자를 해본 경험이 얼마나 있나요?",
        options=(
            QuestionnaireOption("none", "처음이에요"),
            QuestionnaireOption("under_1_year", "1년 미만"),
            QuestionnaireOption("1_to_3_years", "1~3년"),
            QuestionnaireOption("3_to_5_years", "3~5년"),
            QuestionnaireOption("over_5_years", "5년 이상"),
        ),
    ),
    QuestionnaireQuestion(
        id="product_knowledge",
        prompt="주식이나 펀드 같은 투자상품을 얼마나 이해하고 있나요?",
        options=(
            QuestionnaireOption("very_low", "거의 몰라요"),
            QuestionnaireOption("basic", "기본적인 내용은 알아요"),
            QuestionnaireOption("intermediate", "어느 정도 이해하고 있어요"),
            QuestionnaireOption("advanced", "다양한 투자상품을 잘 이해하고 있어요"),
        ),
    ),
    QuestionnaireQuestion(
        id="investment_horizon",
        prompt="이번 투자는 얼마나 오래 이어갈 생각인가요?",
        options=(
            QuestionnaireOption("under_1_year", "1년 미만"),
            QuestionnaireOption("1_to_3_years", "1~3년"),
            QuestionnaireOption("3_to_5_years", "3~5년"),
            QuestionnaireOption("over_5_years", "5년 이상"),
        ),
    ),
    QuestionnaireQuestion(
        id="investment_goal",
        prompt="이번 투자의 가장 큰 목적은 무엇인가요?",
        options=(
            QuestionnaireOption("living_expenses", "생활에 필요한 자금 마련"),
            QuestionnaireOption("major_purchase", "주택·결혼 등 목돈 마련"),
            QuestionnaireOption("retirement", "노후 준비"),
            QuestionnaireOption("surplus_management", "여유자금 운용"),
            QuestionnaireOption("long_term_growth", "장기적인 자산 증식"),
        ),
    ),
    QuestionnaireQuestion(
        id="loss_tolerance",
        prompt="투자할 돈이 줄어들더라도 어느 정도까지 감당할 수 있나요?",
        options=(
            QuestionnaireOption("no_loss", "원금 손실을 원하지 않아요"),
            QuestionnaireOption("loss_10_percent", "10% 정도의 손실까지 괜찮아요"),
            QuestionnaireOption("loss_20_percent", "20% 정도의 손실까지 괜찮아요"),
            QuestionnaireOption("loss_30_percent", "30% 정도의 손실까지 괜찮아요"),
            QuestionnaireOption("loss_over_30_percent", "더 큰 손실도 감수할 수 있어요"),
        ),
    ),
    QuestionnaireQuestion(
        id="risk_return_preference",
        prompt="수익과 안정성 중 어디에 더 가까운 투자를 원하나요?",
        options=(
            QuestionnaireOption("principal_preservation", "원금 보존이 가장 중요해요"),
            QuestionnaireOption("stability", "안정성을 더 중요하게 생각해요"),
            QuestionnaireOption("balanced", "안정성과 수익을 비슷하게 생각해요"),
            QuestionnaireOption("return", "수익을 더 중요하게 생각해요"),
            QuestionnaireOption("high_return", "높은 수익을 위해 큰 변동도 감수할 수 있어요"),
        ),
    ),
    QuestionnaireQuestion(
        id="investable_asset_ratio",
        prompt="현재 가진 금융자산 중 이번 투자에 사용할 금액은 어느 정도인가요?",
        options=(
            QuestionnaireOption("under_10_percent", "10% 미만"),
            QuestionnaireOption("10_to_30_percent", "10~30%"),
            QuestionnaireOption("30_to_50_percent", "30~50%"),
            QuestionnaireOption("50_to_70_percent", "50~70%"),
            QuestionnaireOption("over_70_percent", "70% 이상"),
        ),
    ),
    QuestionnaireQuestion(
        id="annual_income",
        prompt="연간 소득은 어느 정도인가요?",
        options=(
            QuestionnaireOption("under_10m", "1천만원 미만"),
            QuestionnaireOption("10m_to_30m", "1천만원 이상 ~ 3천만원 미만"),
            QuestionnaireOption("30m_to_50m", "3천만원 이상 ~ 5천만원 미만"),
            QuestionnaireOption("50m_to_80m", "5천만원 이상 ~ 8천만원 미만"),
            QuestionnaireOption("over_80m", "8천만원 이상"),
        ),
    ),
)

QUESTIONNAIRES = {"v1": QUESTIONNAIRE_V1}


def resolve_investor_answers(
    questionnaire_version: str,
    answers: Iterable[tuple[str, str]],
) -> list[ResolvedInvestorAnswer]:
    questionnaire = QUESTIONNAIRES.get(questionnaire_version)
    if questionnaire is None:
        raise QuestionnaireValidationError(
            "INVALID_QUESTIONNAIRE_VERSION",
            "지원하지 않는 설문 버전입니다.",
        )

    submitted = list(answers)
    answer_by_question: dict[str, str] = {}
    for question_id, option_id in submitted:
        if question_id in answer_by_question:
            raise QuestionnaireValidationError(
                "INVALID_INVESTOR_ANSWERS",
                "같은 문항에 중복으로 답변할 수 없습니다.",
            )
        answer_by_question[question_id] = option_id

    expected_ids = {question.id for question in questionnaire}
    submitted_ids = set(answer_by_question)
    if submitted_ids != expected_ids:
        raise QuestionnaireValidationError(
            "INVALID_INVESTOR_ANSWERS",
            "모든 설문 문항에 정확히 한 번씩 답변해야 합니다.",
        )

    resolved: list[ResolvedInvestorAnswer] = []
    for question in questionnaire:
        option_id = answer_by_question[question.id]
        option = next((item for item in question.options if item.id == option_id), None)
        if option is None:
            raise QuestionnaireValidationError(
                "INVALID_INVESTOR_ANSWERS",
                f"'{question.id}' 문항의 선택지가 올바르지 않습니다.",
            )
        resolved.append(ResolvedInvestorAnswer(
            question_id=question.id,
            question=question.prompt,
            option_id=option.id,
            answer=option.label,
        ))
    return resolved
