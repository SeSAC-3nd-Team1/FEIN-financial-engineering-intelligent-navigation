import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.api.deps import current_user
from app.api.routes.model_recommendations import get_model_recommendation_service
from app.core.errors import ServiceError
from app.main import app
from app.services.model_recommendation import (
    DEFAULT_SNAPSHOT_PATH,
    ModelRecommendationService,
)


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
    assert response.json()["source"] == "fallback"
    assert response.json()["recommendations"][0]["symbol"] == "005930"
    assert sum(
        item["target_weight"] for item in response.json()["recommendations"]
    ) == pytest.approx(0.95)


def test_latest_model_recommendation_requires_authentication() -> None:
    response = TestClient(app).get("/api/v1/model-recommendations/latest")
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_service_prefers_generated_artifact_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = json.loads(DEFAULT_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    generated["as_of"] = "2026-08-27"
    path = tmp_path / "generated.json"
    path.write_text(json.dumps(generated), encoding="utf-8")
    monkeypatch.setenv("MODEL_RECOMMENDATION_SNAPSHOT_PATH", str(path))

    snapshot = ModelRecommendationService().latest()

    assert snapshot.as_of.isoformat() == "2026-08-27"
    assert snapshot.source == "generated"
    assert not snapshot.is_stale
    assert ModelRecommendationService().snapshot_paths[0] == path


def test_service_uses_packaged_fallback_when_generated_artifact_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "MODEL_RECOMMENDATION_SNAPSHOT_PATH", str(tmp_path / "missing.json")
    )

    snapshot = ModelRecommendationService().latest()

    assert snapshot.as_of.isoformat() == "2026-08-26"
    assert snapshot.source == "fallback"


def test_service_can_disable_packaged_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "MODEL_RECOMMENDATION_SNAPSHOT_PATH", str(tmp_path / "missing.json")
    )
    monkeypatch.setenv("MODEL_RECOMMENDATION_ALLOW_FALLBACK", "false")

    with pytest.raises(ServiceError) as error:
        ModelRecommendationService().latest()

    assert error.value.code == "MODEL_RECOMMENDATION_UNAVAILABLE"
    assert error.value.status_code == 503


def test_service_marks_old_generated_snapshot_as_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = json.loads(DEFAULT_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    generated["as_of"] = "2020-01-02"
    path = tmp_path / "generated.json"
    path.write_text(json.dumps(generated), encoding="utf-8")
    monkeypatch.setenv("MODEL_RECOMMENDATION_STALE_AFTER_DAYS", "3")

    snapshot = ModelRecommendationService(path).latest()

    assert snapshot.source == "generated"
    assert snapshot.is_stale


def test_invalid_snapshot_fails_safely(tmp_path: Path) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps({"status": "ready"}), encoding="utf-8")

    with pytest.raises(ServiceError) as error:
        ModelRecommendationService(path).latest()

    assert error.value.code == "MODEL_RECOMMENDATION_UNAVAILABLE"
    assert error.value.status_code == 503
