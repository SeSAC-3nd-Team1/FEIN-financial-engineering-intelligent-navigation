import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.api.deps import current_user
from app.api.routes.model_recommendations import get_model_recommendation_service
from app.core.errors import ServiceError
from app.main import app
from app.services.model_recommendation import ModelRecommendationService


class FakeService:
    def latest(self):
        return ModelRecommendationService().latest()


def test_latest_model_recommendation_returns_snapshot_for_authenticated_user() -> None:
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[get_model_recommendation_service] = FakeService
    try:
        response = TestClient(app).get("/api/v1/model-recommendations/latest")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["model_version"] == "price-momentum-v1"
    assert response.json()["recommendations"][0]["symbol"] == "005930"


def test_latest_model_recommendation_requires_authentication() -> None:
    response = TestClient(app).get("/api/v1/model-recommendations/latest")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_invalid_snapshot_fails_safely(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"status": "ready"}), encoding="utf-8")

    with pytest.raises(ServiceError) as error:
        ModelRecommendationService(path).latest()

    assert error.value.code == "MODEL_RECOMMENDATION_UNAVAILABLE"
    assert error.value.status_code == 503
