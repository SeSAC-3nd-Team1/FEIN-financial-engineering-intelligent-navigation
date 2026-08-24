from sqlalchemy.dialects import postgresql

from app.repositories.recommendation import RecommendationRepository


class CapturingSession:
    def __init__(self, scalar_result) -> None:
        self.scalar_result = scalar_result
        self.statements = []

    def scalar(self, statement):
        self.statements.append(statement)
        return self.scalar_result


def _compiled_sql(statement) -> str:
    compiled = statement.compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return " ".join(str(compiled).split())


def test_ai_consent_requires_agreement_to_latest_effective_term() -> None:
    session = CapturingSession(scalar_result=None)
    repository = RecommendationRepository(session)

    assert repository.has_ai_personalization_consent(user_id=7) is False

    sql = _compiled_sql(session.statements[0])
    assert "user_agreements.user_id = 7" in sql
    assert "user_agreements.is_agreed IS true" in sql
    assert "user_agreements.term_id = (SELECT terms.id" in sql
    assert "terms.term_code = 'AI_PERSONALIZATION'" in sql
    assert "terms.effective_at <=" in sql
    assert "ORDER BY terms.effective_at DESC, terms.id DESC" in sql


def test_ai_consent_accepts_agreement_to_latest_effective_term() -> None:
    session = CapturingSession(scalar_result=101)
    repository = RecommendationRepository(session)

    assert repository.has_ai_personalization_consent(user_id=7) is True
