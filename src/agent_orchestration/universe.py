import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel


class UniverseSnapshot(BaseModel):
    as_of: datetime
    max_age_days: int
    instruments: dict[str, str]

    @property
    def stale(self) -> bool:
        return (datetime.now(UTC) - self.as_of).days > self.max_age_days


class UniverseProvider(Protocol):
    async def get_snapshot(self) -> UniverseSnapshot:
        ...


class FileUniverseProvider:
    def __init__(self, path: Path):
        self._path = path

    async def get_snapshot(self) -> UniverseSnapshot:
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return UniverseSnapshot.model_validate(payload)
