from db.models import (
    RegistrationAgreement,
    RegistrationSession,
    Term,
    User,
    UserAgreement,
)


def _constraint_names(model: type) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.name is not None
    }


def _index_columns(model: type) -> set[tuple[str, ...]]:
    return {tuple(column.name for column in index.columns) for index in model.__table__.indexes}


def _foreign_key_targets(model: type) -> set[tuple[str, ...]]:
    return {
        tuple(element.target_fullname for element in constraint.elements)
        for constraint in model.__table__.foreign_key_constraints
    }


def test_user_has_3nf_signup_constraints_and_no_duplicate_verification_flags() -> None:
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
    assert "phone_verified" not in User.__table__.columns
    assert "email_verified" not in User.__table__.columns
    assert not User.__table__.columns.phone_verified_at.nullable
    assert not User.__table__.columns.email_verified_at.nullable


def test_terms_are_versioned_and_user_agreements_reference_term_id_only() -> None:
    assert "uq_terms_code_version" in _constraint_names(Term)
    assert "uq_user_agreements_user_term_id" in _constraint_names(UserAgreement)
    assert ("user_id", "agreed_at") in _index_columns(UserAgreement)
    assert _foreign_key_targets(UserAgreement) == {("users.id",), ("terms.id",)}
    assert {
        "term_code",
        "term_version",
        "is_required",
    }.isdisjoint(UserAgreement.__table__.columns.keys())
    user_fk = next(iter(UserAgreement.__table__.columns.user_id.foreign_keys))
    term_fk = next(iter(UserAgreement.__table__.columns.term_id.foreign_keys))
    assert user_fk.ondelete == "RESTRICT"
    assert term_fk.ondelete == "RESTRICT"


def test_registration_session_keeps_only_pre_signup_relational_state() -> None:
    assert RegistrationSession.__table__.schema is None
    assert RegistrationSession.__table__.columns.id.primary_key
    assert ("phone_number",) in _index_columns(RegistrationSession)
    assert {
        "ck_registration_sessions_birthdate_format",
        "ck_registration_sessions_phone_number_format",
        "ck_registration_sessions_email_verification_has_target",
        "ck_registration_sessions_expires_after_created",
    } <= _constraint_names(RegistrationSession)
    assert {
        "password",
        "password_hash",
        "otp",
        "otp_code",
        "verification_token",
    }.isdisjoint(RegistrationSession.__table__.columns.keys())


def test_registration_agreement_has_composite_key_and_restricts_term_delete() -> None:
    assert tuple(column.name for column in RegistrationAgreement.__table__.primary_key) == (
        "registration_id",
        "term_id",
    )
    assert _foreign_key_targets(RegistrationAgreement) == {
        ("registration_sessions.id",),
        ("terms.id",),
    }
    ondelete_by_target = {
        fk.target_fullname: fk.ondelete
        for fk in RegistrationAgreement.__table__.foreign_keys
    }
    assert ondelete_by_target["registration_sessions.id"] == "CASCADE"
    assert ondelete_by_target["terms.id"] == "RESTRICT"


def test_model_registry_contains_only_membership_and_registration_models() -> None:
    for model in (
        User,
        Term,
        UserAgreement,
        RegistrationSession,
        RegistrationAgreement,
    ):
        assert model.__table__.schema is None
