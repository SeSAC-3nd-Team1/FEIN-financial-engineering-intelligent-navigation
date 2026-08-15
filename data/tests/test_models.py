from db.models import (
    FinancialStatement,
    RawDataObject,
    RawMigrationManifest,
    StockMaster,
    StockPriceDaily,
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
    return {
        tuple(column.name for column in index.columns)
        for index in model.__table__.indexes
    }


def test_stock_master_uses_raw_schema_and_unique_code() -> None:
    assert StockMaster.__table__.schema == "raw"
    assert "uq_stock_master_stock_code" in _constraint_names(StockMaster)
    assert StockMaster.__table__.c.stock_code.type.length == 12


def test_daily_price_has_point_lookup_and_range_indexes() -> None:
    assert "uq_stock_price_daily_stock_date_type" in _constraint_names(
        StockPriceDaily
    )
    assert ("stock_id", "trade_date") in _index_columns(StockPriceDaily)
    assert ("trade_date", "stock_id") in _index_columns(StockPriceDaily)


def test_financial_statement_is_point_in_time_aware() -> None:
    column_names = set(FinancialStatement.__table__.columns.keys())
    assert {"fiscal_period", "report_date", "disclosure_date", "available_date"} <= (
        column_names
    )
    assert ("stock_id", "available_date") in _index_columns(FinancialStatement)
    assert "ck_financial_statement_available_date_after_report_date" in (
        _constraint_names(FinancialStatement)
    )


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
    assert "uq_user_agreements_user_term_version" in _constraint_names(
        UserAgreement
    )
    assert ("user_id", "agreed_at") in _index_columns(UserAgreement)
    foreign_keys = {
        tuple(element.target_fullname for element in constraint.elements)
        for constraint in UserAgreement.__table__.foreign_key_constraints
    }
    assert ("users.id",) in foreign_keys
    assert ("terms.term_code", "terms.version") in foreign_keys


def test_blob_raw_metadata_does_not_store_payload_json() -> None:
    assert RawDataObject.__table__.schema == "raw"
    assert "payload" not in RawDataObject.__table__.columns
    assert "uq_data_object_blob" in _constraint_names(RawDataObject)
    assert "uq_public_data_migration_source_chunk" in _constraint_names(
        RawMigrationManifest
    )
