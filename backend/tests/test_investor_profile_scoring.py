import pytest

from app.domain.investor_profile.questionnaire import resolve_investor_answers
from app.domain.investor_profile.scoring import profile_type_for_score, score_investor_profile


def score(answers: list[tuple[str, str]]):
    return score_investor_profile(resolve_investor_answers("v1", answers))


BASE_ANSWERS = [
    ("investment_experience", "1_to_3_years"),
    ("product_knowledge", "basic"),
    ("investment_horizon", "3_to_5_years"),
    ("investment_goal", "retirement"),
    ("loss_tolerance", "loss_20_percent"),
    ("risk_return_preference", "balanced"),
    ("investable_asset_ratio", "10_to_30_percent"),
    ("annual_income", "30m_to_50m"),
]


@pytest.mark.parametrize(
    ("risk_score", "expected"),
    [
        (0, "안정추구형"),
        (19, "안정추구형"),
        (20, "안정투자형"),
        (39, "안정투자형"),
        (40, "중립투자형"),
        (59, "중립투자형"),
        (60, "성장추구형"),
        (79, "성장추구형"),
        (80, "공격투자형"),
        (100, "공격투자형"),
    ],
)
def test_profile_type_boundaries(risk_score, expected) -> None:
    assert profile_type_for_score(risk_score) == expected


def test_profile_type_rejects_out_of_range_score() -> None:
    with pytest.raises(ValueError):
        profile_type_for_score(101)


def test_scores_balanced_answers_as_neutral() -> None:
    result = score(BASE_ANSWERS)

    assert result.raw_score == 51
    assert result.risk_score == 51
    assert result.profile_type == "중립투자형"
    assert (result.stability, result.return_seeking, result.horizon) == (3, 3, 4)


def test_scores_maximum_risk_answers_as_aggressive() -> None:
    result = score([
        ("investment_experience", "over_5_years"),
        ("product_knowledge", "advanced"),
        ("investment_horizon", "over_5_years"),
        ("investment_goal", "long_term_growth"),
        ("loss_tolerance", "loss_over_30_percent"),
        ("risk_return_preference", "high_return"),
        ("investable_asset_ratio", "under_10_percent"),
        ("annual_income", "over_80m"),
    ])

    assert result.raw_score == 100
    assert result.risk_score == 100
    assert result.profile_type == "공격투자형"


def test_principal_preservation_caps_otherwise_high_score() -> None:
    result = score([
        ("investment_experience", "over_5_years"),
        ("product_knowledge", "advanced"),
        ("investment_horizon", "over_5_years"),
        ("investment_goal", "long_term_growth"),
        ("loss_tolerance", "no_loss"),
        ("risk_return_preference", "high_return"),
        ("investable_asset_ratio", "under_10_percent"),
        ("annual_income", "over_80m"),
    ])

    assert result.raw_score == 76
    assert result.risk_score == 19
    assert result.profile_type == "안정추구형"


def test_aggressive_type_requires_loss_capacity_and_high_return_preference() -> None:
    result = score([
        ("investment_experience", "over_5_years"),
        ("product_knowledge", "advanced"),
        ("investment_horizon", "over_5_years"),
        ("investment_goal", "long_term_growth"),
        ("loss_tolerance", "loss_over_30_percent"),
        ("risk_return_preference", "return"),
        ("investable_asset_ratio", "under_10_percent"),
        ("annual_income", "over_80m"),
    ])

    assert result.raw_score == 94
    assert result.risk_score == 79
    assert result.profile_type == "성장추구형"


def test_living_expenses_downgrades_result_by_one_level() -> None:
    result = score([
        ("investment_experience", "over_5_years"),
        ("product_knowledge", "advanced"),
        ("investment_horizon", "over_5_years"),
        ("investment_goal", "living_expenses"),
        ("loss_tolerance", "loss_over_30_percent"),
        ("risk_return_preference", "high_return"),
        ("investable_asset_ratio", "under_10_percent"),
        ("annual_income", "over_80m"),
    ])

    assert result.raw_score == 92
    assert result.risk_score == 79
    assert result.profile_type == "성장추구형"
