import os

import psycopg
import redis
from fastapi import FastAPI, HTTPException

app = FastAPI(title="SeSAC Team 1 API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/dependencies")
def dependency_health() -> dict[str, str]:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as connection:
            connection.execute("SELECT 1")

        cache = redis.from_url(
            os.environ["REDIS_URL"], socket_connect_timeout=3, decode_responses=True
        )
        cache.ping()
    except (KeyError, psycopg.Error, redis.RedisError) as error:
        raise HTTPException(status_code=503, detail="Dependency unavailable") from error

    return {"postgres": "ok", "redis": "ok"}
