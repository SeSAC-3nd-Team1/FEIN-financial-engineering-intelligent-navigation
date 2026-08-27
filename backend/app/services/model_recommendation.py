"""Serve the validated price-model snapshot used by the working MVP."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import ServiceError
from app.schemas.api import ModelRecommendationSnapshotResponse


DEFAULT_SNAPSHOT_PATH = Path(__file__).resolve().parents[1] / "data" / "model_recommendation_snapshot.json"


class ModelRecommendationService:
    def __init__(self, snapshot_path: Path = DEFAULT_SNAPSHOT_PATH) -> None:
        self.snapshot_path = snapshot_path

    def latest(self) -> ModelRecommendationSnapshotResponse:
        try:
            payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            snapshot = ModelRecommendationSnapshotResponse.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise ServiceError(
                "MODEL_RECOMMENDATION_UNAVAILABLE",
                "가격 기반 모델 추천을 불러올 수 없습니다.",
                503,
            ) from exc
        if snapshot.status != "ready" or not snapshot.recommendations:
            raise ServiceError(
                "MODEL_RECOMMENDATION_UNAVAILABLE",
                "가격 기반 모델 추천이 아직 준비되지 않았습니다.",
                503,
            )
        return snapshot
