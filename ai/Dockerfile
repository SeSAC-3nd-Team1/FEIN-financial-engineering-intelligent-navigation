FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# DefaultAzureCredential uses this CLI in local development. The persisted
# Compose volume keeps login state outside the image and source tree.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
    && curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sleep", "infinity"]
