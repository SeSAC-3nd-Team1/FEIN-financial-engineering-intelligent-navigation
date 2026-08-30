"""Investor profile questionnaire and deterministic scoring domain."""

from app.domain.investor_profile.questionnaire import ResolvedInvestorAnswer, resolve_investor_answers
from app.domain.investor_profile.scoring import (
    SCORING_RULE_VERSION,
    SCORING_VERSION,
    InvestorProfileScoreResult,
    profile_type_for_score,
    score_investor_profile,
)

__all__ = [
    "SCORING_RULE_VERSION",
    "SCORING_VERSION",
    "InvestorProfileScoreResult",
    "ResolvedInvestorAnswer",
    "profile_type_for_score",
    "resolve_investor_answers",
    "score_investor_profile",
]
