import pytest

from app.core.errors import ServiceError
from app.services.auth import AuthService


class EmptyCatalogSession:
    def scalars(self, _statement):
        return []


def test_terms_catalog_fails_closed_without_required_terms() -> None:
    with pytest.raises(ServiceError) as error:
        AuthService(EmptyCatalogSession()).signup_terms()

    assert error.value.code == "TERMS_CATALOG_UNAVAILABLE"
    assert error.value.status_code == 503
