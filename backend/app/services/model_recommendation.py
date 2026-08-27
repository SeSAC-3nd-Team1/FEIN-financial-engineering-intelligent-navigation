"""Serve the validated price-model snapshot used by the working MVP."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from app.core.errors import ServiceError
from app.schemas.api import ModelRecommendationSnapshotResponse

DEFAULT_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "model_recommendation_snapshot.json"
)


class ModelRecommendationService:
    def __init__(self, snapshot_path: Path | None = None) -> None:
        configured_path = os.getenv("MODEL_RECOMMENDATION_SNAPSHOT_PATH", "").strip()
        if snapshot_path is not None:
            self.snapshot_paths = (snapshot_path,)
        elif configured_path:
            configured = Path(configured_path)
            self.snapshot_paths = (
                (configured, DEFAULT_SNAPSHOT_PATH)
                if configured != DEFAULT_SNAPSHOT_PATH
                else (configured,)
            )
        else:
            self.snapshot_paths = (DEFAULT_SNAPSHOT_PATH,)

    def latest(self) -> ModelRecommendationSnapshotResponse:
        snapshot: ModelRecommendationSnapshotResponse | None = None
        last_error: Exception | None = None
        for snapshot_path in self.snapshot_paths:
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                snapshot = ModelRecommendationSnapshotResponse.model_validate(payload)
                break
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
        if snapshot is None:
            raise ServiceError(
                "MODEL_RECOMMENDATION_UNAVAILABLE",
                "가격 기반 모델 추천을 불러올 수 없습니다.",
                503,
            ) from last_error
        if snapshot.status != "ready" or not snapshot.recommendations:
            raise ServiceError(
                "MODEL_RECOMMENDATION_UNAVAILABLE",
                "가격 기반 모델 추천이 아직 준비되지 않았습니다.",
                503,
            )
        return snapshot
