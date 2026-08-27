import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


MAX_UNIVERSE_AGE_DAYS = 365


class AssetType(StrEnum):
    KOSPI200_STOCK = "KOSPI200_STOCK"
    ETF = "ETF"
    ALLOWED_ETF = "ALLOWED_ETF"
    CASH = "CASH"
    RP = "RP"
    DOMESTIC_SHORT_TERM_BOND = "DOMESTIC_SHORT_TERM_BOND"
    FOREIGN_STOCK = "FOREIGN_STOCK"
    CRYPTO = "CRYPTO"
    DERIVATIVE = "DERIVATIVE"
    LEVERAGED_INVERSE_ETF = "LEVERAGED_INVERSE_ETF"
    OTC = "OTC"
    UNKNOWN = "UNKNOWN"


ASSET_TYPE_POLICY: Mapping[AssetType, bool] = MappingProxyType(
    {
        AssetType.KOSPI200_STOCK: True,
        AssetType.ETF: True,
        AssetType.ALLOWED_ETF: True,
        AssetType.CASH: True,
        AssetType.RP: True,
        AssetType.DOMESTIC_SHORT_TERM_BOND: True,
        AssetType.FOREIGN_STOCK: False,
        AssetType.CRYPTO: False,
        AssetType.DERIVATIVE: False,
        AssetType.LEVERAGED_INVERSE_ETF: False,
        AssetType.OTC: False,
        AssetType.UNKNOWN: False,
    }
)

_SECURITY_ASSET_TYPES = frozenset(
    {AssetType.KOSPI200_STOCK, AssetType.ETF, AssetType.ALLOWED_ETF}
)
_SYMBOL_ASSET_TYPES = frozenset(
    {AssetType.CASH, AssetType.RP, AssetType.DOMESTIC_SHORT_TERM_BOND}
)


def coerce_asset_type(value: AssetType | str | Any) -> AssetType:
    if isinstance(value, AssetType):
        return value
    try:
        return AssetType(str(value).strip().upper())
    except ValueError:
        return AssetType.UNKNOWN


def canonicalize_ticker(
    ticker: str,
    asset_type: AssetType | str | None = None,
) -> str:
    if not isinstance(ticker, str):
        raise ValueError("ticker must be a string")
    canonical = ticker.strip().upper()
    if not canonical:
        raise ValueError("ticker must not be empty")

    kind = coerce_asset_type(asset_type) if asset_type is not None else None
    if kind in _SECURITY_ASSET_TYPES:
        if canonical.endswith(".KS"):
            canonical = canonical[:-3]
    elif kind is None and canonical.endswith(".KS"):
        possible_code = canonical[:-3]
        if re.fullmatch(r"\d{6}", possible_code):
            canonical = possible_code
    return canonical


def is_valid_identifier(ticker: str, asset_type: AssetType | str) -> bool:
    kind = coerce_asset_type(asset_type)
    try:
        canonical = canonicalize_ticker(ticker, kind)
    except ValueError:
        return False
    if kind in _SECURITY_ASSET_TYPES:
        return re.fullmatch(r"\d{6}", canonical) is not None
    if kind in _SYMBOL_ASSET_TYPES:
        return re.fullmatch(r"[A-Z][A-Z0-9_-]{0,31}", canonical) is not None
    return bool(canonical)


class UniverseTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    asset_type: AssetType

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return canonicalize_ticker(value)

    @field_validator("asset_type", mode="before")
    @classmethod
    def normalize_asset_type(cls, value: AssetType | str) -> AssetType:
        return coerce_asset_type(value)

    @model_validator(mode="after")
    def validate_identifier(self) -> "UniverseTarget":
        if not is_valid_identifier(self.ticker, self.asset_type):
            raise ValueError("ticker is invalid for its asset type")
        return self


class UniverseProviderError(RuntimeError):
    block_reason = "UNIVERSE_UNAVAILABLE"


class UniverseSnapshot(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    as_of: datetime
    max_age_days: int = Field(
        gt=0,
        le=MAX_UNIVERSE_AGE_DAYS,
        description="Maximum permitted snapshot age in days.",
    )
    instruments: Mapping[str, AssetType]

    @field_validator("as_of")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("instruments", mode="before")
    @classmethod
    def normalize_instruments(cls, value: Any) -> dict[str, AssetType]:
        if not isinstance(value, Mapping):
            raise ValueError("instruments must be an object")
        normalized: dict[str, AssetType] = {}
        for ticker, raw_asset_type in value.items():
            asset_type = coerce_asset_type(raw_asset_type)
            canonical_ticker = canonicalize_ticker(ticker, asset_type)
            if canonical_ticker in normalized:
                raise ValueError("instruments contain ambiguous duplicate tickers")
            normalized[canonical_ticker] = asset_type
        return normalized

    @field_validator("instruments")
    @classmethod
    def freeze_instruments(cls, value: Mapping[str, AssetType]) -> Mapping[str, AssetType]:
        return MappingProxyType(dict(value))

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False):
        payload = {
            "as_of": self.as_of,
            "max_age_days": self.max_age_days,
            "instruments": dict(self.instruments),
        }
        if update:
            payload.update(update)
        return type(self).model_validate(payload)

    @property
    def stale(self) -> bool:
        elapsed = datetime.now(UTC) - self.as_of
        return elapsed < timedelta(0) or elapsed > timedelta(days=self.max_age_days)


class UniverseProvider(Protocol):
    async def get_snapshot(self) -> UniverseSnapshot:
        ...


class FileUniverseProvider:
    def __init__(self, path: Path):
        self._path = Path(path)

    async def get_snapshot(self) -> UniverseSnapshot:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            return UniverseSnapshot.model_validate(payload)
        except (OSError, UnicodeError, TypeError, ValueError, ValidationError) as error:
            raise UniverseProviderError("universe snapshot unavailable") from error
