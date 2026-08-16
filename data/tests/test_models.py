from db.models import Term, User, UserAgreement


def _constraint_names(model: type) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.name is not None
    }


def _index_columns(model: type) -> set[tuple[str, ...]]:
    return {tuple(column.name for column in index.columns) for index in model.__table__.indexes}


def test_user_has_signup_constraints_and_lookup_indexes() -> None:
    assert {
        "uq_users_user_id",
        "uq_users_email",
        "uq_users_ci_lookup_hash",
        "ck_users_user_id_format",
        "ck_users_phone_number_format",
        "ck_users_member_type_values",
        "ck_users_account_status_values",
    } <= _constraint_names(User)
    assert ("phone_number",) in _index_columns(User)


def test_terms_are_versioned_and_agreements_reference_catalog() -> None:
    assert "uq_terms_code_version" in _constraint_names(Term)
    assert "uq_user_agreements_user_term_version" in _constraint_names(UserAgreement)
    assert ("user_id", "agreed_at") in _index_columns(UserAgreement)
    foreign_keys = {
        tuple(element.target_fullname for element in constraint.elements)
        for constraint in UserAgreement.__table__.foreign_key_constraints
    }
    assert ("users.id",) in foreign_keys
    assert ("terms.term_code", "terms.version") in foreign_keys


def test_model_registry_contains_only_persistent_membership_models() -> None:
    assert User.__table__.schema is None
    assert Term.__table__.schema is None
    assert UserAgreement.__table__.schema is None
