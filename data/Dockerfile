FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Local Docker data jobs authenticate to Azure through Azure CLI.
# The Compose azure_cli_data volume persists the login cache across ephemeral runs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*

COPY data/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY data .
COPY shared /workspace/shared
ENV PYTHONPATH=/app:/workspace

CMD ["sleep", "infinity"]
