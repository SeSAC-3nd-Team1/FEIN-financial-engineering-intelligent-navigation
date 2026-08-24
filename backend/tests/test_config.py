"""필수 애플리케이션 환경변수의 fail-fast 계약을 검증한다."""

import os
from pathlib import Path
import subprocess
import sys


def test_missing_database_url_fails_before_application_start() -> None:
    """DATABASE_URL 누락·공백 시 로컬 PostgreSQL로 fallback하지 않는다."""

    for value in (None, "   "):
        environment = os.environ.copy()
        if value is None:
            environment.pop("DATABASE_URL", None)
        else:
            environment["DATABASE_URL"] = value
        result = subprocess.run(
            [sys.executable, "-c", "import app.core.config"],
            cwd=Path(__file__).resolve().parents[1],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "DATABASE_URL is required" in result.stderr
