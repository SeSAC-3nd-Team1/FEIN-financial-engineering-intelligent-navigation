#!/bin/sh
set -eu

ARTIFACT_PATH=/model-artifacts/model_recommendation_snapshot.json

docker compose --profile ai run --rm --no-deps ai \
  python -m inference.export_recommendation_snapshot \
  --input /app/tests/fixtures/recommendation_features.csv \
  --output "$ARTIFACT_PATH" \
  --data-version algorithm-ohlcv-v2 \
  --top-n 4

docker compose run --rm --no-deps backend python -c \
  'from app.services.model_recommendation import ModelRecommendationService; snapshot = ModelRecommendationService().latest(); assert len(snapshot.recommendations) == 4; assert abs(sum(item.target_weight for item in snapshot.recommendations) - 0.95) < 1e-8; print(f"verified {snapshot.model_version} for {snapshot.as_of}")'
