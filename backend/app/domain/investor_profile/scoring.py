"""투자성향 설문을 고정 점수표와 보수적 제한 규칙으로 분류한다."""

from dataclasses import dataclass
from typing import Literal

from app.domain.investor_profile.questionnaire import ResolvedInvestorAnswer


InvestorProfileType = Literal[
    "안정추구형",
    "안정투자형",
    "중립투자형",
    "성장추구형",
    "공격투자형",
]


SCORING_VERSION = "risk-score-v1"
SCORING_RULE_VERSION = "v1"


SCORE_TABLE: dict[str, dict[str, int]] = {
    "investment_experience": {
        "none": 0,
        "under_1_year": 2,
        "1_to_3_years": 5,
        "3_to_5_years": 7,
        "over_5_years": 10,
    },
    "product_knowledge": {
        "very_low": 0,
        "basic": 3,
        "intermediate": 7,
        "advanced": 10,
    },
    "investment_horizon": {
        "under_1_year": 0,
        "1_to_3_years": 4,
        "3_to_5_years": 8,
        "over_5_years": 12,
    },
    "investment_goal": {
        "living_expenses": 0,
        "major_purchase": 2,
        "retirement": 4,
        "surplus_management": 6,
        "long_term_growth": 8,
    },
    "loss_tolerance": {
        "no_loss": 0,
        "loss_10_percent": 6,
        "loss_20_percent": 12,
        "loss_30_percent": 18,
        "loss_over_30_percent": 24,
    },
    "risk_return_preference": {
        "principal_preservation": 0,
        "stability": 6,
        "balanced": 12,
        "return": 18,
        "high_return": 24,
    },
    # 투자 비중이 높을수록 손실 시 금융자산 전체에 미치는 충격이 커지므로 역방향으로 반영한다.
    "investable_asset_ratio": {
        "under_10_percent": 7,
        "10_to_30_percent": 5,
        "30_to_50_percent": 3,
        "50_to_70_percent": 1,
        "over_70_percent": 0,
    },
    "annual_income": {
        "under_10m": 0,
        "10m_to_30m": 1,
        "30m_to_50m": 2,
        "50m_to_80m": 3,
        "over_80m": 5,
    },
}


PROFILE_TYPES: tuple[InvestorProfileType, ...] = (
    "안정추구형",
    "안정투자형",
    "중립투자형",
    "성장추구형",
    "공격투자형",
)


PROFILE_CONTENT: dict[InvestorProfileType, tuple[str, str]] = {
    "안정추구형": (
        "원금 보존과 손실 최소화를 가장 중요하게 생각하는 투자자예요.",
        "투자수익보다 자산의 안정적인 보존을 우선하며, 가격 변동과 원금 손실에 매우 신중한 성향입니다.",
    ),
    "안정투자형": (
        "제한적인 손실은 감수하지만 안정성을 더 중요하게 생각하는 투자자예요.",
        "일정 수준의 수익을 기대하면서도 큰 가격 변동은 피하고 안정적인 운용을 선호하는 성향입니다.",
    ),
    "중립투자형": (
        "안정성과 수익의 균형을 중요하게 생각하는 투자자예요.",
        "일정 수준의 변동은 감수하지만 과도한 위험은 피하며 안정성과 수익을 함께 고려하는 성향입니다.",
    ),
    "성장추구형": (
        "의미 있는 변동을 감수하며 안정성보다 수익을 중시하는 투자자예요.",
        "중장기적인 자산 성장을 위해 비교적 큰 가격 변동과 일부 원금 손실 가능성을 감수하는 성향입니다.",
    ),
    "공격투자형": (
        "큰 변동 가능성을 인지하면서 높은 수익 가능성을 우선하는 투자자예요.",
        "높은 수익을 추구하며 투자 과정에서 발생할 수 있는 큰 가격 변동과 원금 손실을 감수하는 성향입니다.",
    ),
}


STABILITY_TRAITS = {
    "principal_preservation": 5,
    "stability": 4,
    "balanced": 3,
    "return": 2,
    "high_return": 1,
}
RETURN_SEEKING_TRAITS = {
    "principal_preservation": 1,
    "stability": 2,
    "balanced": 3,
    "return": 4,
    "high_return": 5,
}
HORIZON_TRAITS = {
    "under_1_year": 1,
    "1_to_3_years": 2,
    "3_to_5_years": 4,
    "over_5_years": 5,
}


@dataclass(frozen=True)
class InvestorProfileScoreResult:
    """저장 및 API 응답에 사용할 결정론적 투자성향 결과다."""

    risk_score: int
    raw_score: int
    profile_type: InvestorProfileType
    tendency_line: str
    description: str
    stability: int
    return_seeking: int
    horizon: int
    analysis_summary: list[str]


def profile_type_for_score(score: int) -> InvestorProfileType:
    """0~100 점수를 20점 단위의 다섯 투자성향으로 변환한다."""

    if not 0 <= score <= 100:
        raise ValueError("투자성향 점수는 0점 이상 100점 이하여야 합니다.")
    return PROFILE_TYPES[min(score // 20, len(PROFILE_TYPES) - 1)]


def _apply_conservative_caps(raw_score: int, options: dict[str, str]) -> tuple[int, list[str]]:
    """상충하거나 손실 여력이 낮은 답변이 공격적인 합산 결과를 만들지 않도록 제한한다."""

    score = raw_score
    reasons: list[str] = []
    loss_tolerance = options["loss_tolerance"]
    preference = options["risk_return_preference"]

    if loss_tolerance == "no_loss" or preference == "principal_preservation":
        if score > 19:
            reasons.append("원금 보존 응답을 반영해 안정추구형 범위로 제한했습니다.")
        score = min(score, 19)
    elif loss_tolerance == "loss_10_percent" or preference == "stability":
        if score > 39:
            reasons.append("낮은 손실 감내도 또는 안정성 우선 응답을 반영해 안정투자형 범위로 제한했습니다.")
        score = min(score, 39)

    aggressive_answers = (
        loss_tolerance in {"loss_30_percent", "loss_over_30_percent"}
        and preference == "high_return"
    )
    if score >= 80 and not aggressive_answers:
        score = 79
        reasons.append("공격투자형의 손실 감내도와 고수익 선호 조건을 모두 충족하지 않아 성장추구형으로 제한했습니다.")

    if options["product_knowledge"] == "very_low" and score >= 80:
        score = 79
        reasons.append("금융상품 이해도를 반영해 공격투자형보다 보수적으로 분류했습니다.")

    if (
        options["investment_goal"] == "living_expenses"
        or options["investable_asset_ratio"] == "over_70_percent"
    ):
        current_level = min(score // 20, len(PROFILE_TYPES) - 1)
        if current_level > 0:
            score = min(score, current_level * 20 - 1)
            reasons.append("생활자금 목적 또는 높은 투자자산 비중을 반영해 한 단계 보수적으로 분류했습니다.")

    return score, reasons


def score_investor_profile(answers: list[ResolvedInvestorAnswer]) -> InvestorProfileScoreResult:
    """검증·정규화된 8개 답변을 점수화하고 5단계 투자성향 결과를 만든다."""

    options = {answer.question_id: answer.option_id for answer in answers}
    expected_questions = set(SCORE_TABLE)
    if set(options) != expected_questions:
        raise ValueError("점수 계산에는 검증된 전체 투자성향 답변이 필요합니다.")

    raw_score = sum(SCORE_TABLE[question_id][option_id] for question_id, option_id in options.items())
    risk_score, cap_reasons = _apply_conservative_caps(raw_score, options)
    profile_type = profile_type_for_score(risk_score)
    tendency_line, description = PROFILE_CONTENT[profile_type]
    labels = {answer.question_id: answer.answer for answer in answers}
    analysis_summary = [
        f"투자성향 점수는 100점 만점에 {risk_score}점입니다.",
        f"감당 가능한 손실은 '{labels['loss_tolerance']}'로 응답했습니다.",
        f"수익과 안정성 선호는 '{labels['risk_return_preference']}'로 응답했습니다.",
        f"예상 투자 기간은 '{labels['investment_horizon']}'입니다.",
        *cap_reasons[:1],
    ]

    return InvestorProfileScoreResult(
        risk_score=risk_score,
        raw_score=raw_score,
        profile_type=profile_type,
        tendency_line=tendency_line,
        description=description,
        stability=STABILITY_TRAITS[options["risk_return_preference"]],
        return_seeking=RETURN_SEEKING_TRAITS[options["risk_return_preference"]],
        horizon=HORIZON_TRAITS[options["investment_horizon"]],
        analysis_summary=analysis_summary,
    )
