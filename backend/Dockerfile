FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt ./
COPY agent-orchestration /agent-orchestration
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir /agent-orchestration

COPY backend /app
# Do not copy the v2 formula into Backend: expose the AI package as the shared
# source of truth for service backtests as well.
COPY ai /ai
COPY shared /workspace/shared
COPY .deploy-artifacts /model-artifacts
COPY output/fincon_ver23_model.py output/fincon_ver23_model_fix1.py /models/
ENV PYTHONPATH=/app:/ai:/workspace \
    FINCON_VER23_MODEL_PATH=/models/fincon_ver23_model_fix1.py

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
