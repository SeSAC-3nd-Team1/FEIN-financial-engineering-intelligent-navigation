from db.models import InvestorProfileAssessment, StrategyRecommendation, StrategyRecommendationItem


def _constraint_names(model: type) -> set[str]:
    return {constraint.name for constraint in model.__table__.constraints if constraint.name}


def _foreign_key_targets(model: type) -> set[str]:
    return {foreign_key.target_fullname for foreign_key in model.__table__.foreign_keys}


def _constraint_columns(model: type, constraint_name: str) -> tuple[str, ...]:
    constraint = next(
        item for item in model.__table__.constraints if item.name == constraint_name
    )
    return tuple(column.name for column in constraint.columns)


def test_assessment_stores_derived_profile_without_raw_answers() -> None:
    columns = set(InvestorProfileAssessment.__table__.columns.keys())
    assert {
        "risk_score",
        "profile_type",
        "stability",
        "return_seeking",
        "horizon",
        "model_version",
        "prompt_version",
    } <= columns
    assert InvestorProfileAssessment.__table__.c.risk_score.nullable is True
    assert "ck_investor_profile_assessments_risk_score_range" in _constraint_names(
        InvestorProfileAssessment
    )
    assert {"answers", "raw_answers", "question_answers"}.isdisjoint(columns)
    assert _foreign_key_targets(InvestorProfileAssessment) == {"users.id"}


def test_recommendation_is_versioned_and_idempotent_per_input() -> None:
    assert "uq_strategy_recommendations_reproducible_input" in _constraint_names(StrategyRecommendation)
    assert _constraint_columns(
        StrategyRecommendation,
        "uq_strategy_recommendations_reproducible_input",
    ) == (
        "assessment_id",
        "model_version",
        "prompt_version",
        "strategy_catalog_version",
        "dataset_version",
    )
    assert _foreign_key_targets(StrategyRecommendation) == {"investor_profile_assessments.id"}


def test_recommendation_items_restrict_rank_score_and_strategy() -> None:
    assert {
        "uq_strategy_recommendation_items_rank",
        "ck_strategy_recommendation_items_rank_range",
        "ck_strategy_recommendation_items_score_range",
        "ck_strategy_recommendation_items_match_level_values",
    } <= _constraint_names(StrategyRecommendationItem)
    assert _foreign_key_targets(StrategyRecommendationItem) == {"strategy_recommendations.id", "strategies.id"}
