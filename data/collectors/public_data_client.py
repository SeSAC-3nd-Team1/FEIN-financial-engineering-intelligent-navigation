"""Resilient client for data.go.kr JSON/XML pagination."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from requests.exceptions import JSONDecodeError
from urllib3.util.retry import Retry

from collectors.public_data_config import ApiOperation
from db.connection.session import PROJECT_ROOT


SUCCESS_CODES = {"00", "0", "NORMAL_SERVICE"}


class PublicDataApiError(RuntimeError):
    """The public API returned an error header or unreadable response."""


@dataclass(frozen=True)
class ApiPage:
    items: list[dict[str, Any]]
    page_number: int
    total_count: int


def get_public_data_api_key() -> str:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key = os.getenv("DATA_GO_KR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "DATA_GO_KR_API_KEY is required in the repository root .env file."
        )
    return api_key


def _element_to_value(element: ElementTree.Element) -> Any:
    children = list(element)
    if not children:
        return element.text or ""
    values: dict[str, Any] = {}
    for child in children:
        value = _element_to_value(child)
        if child.tag in values:
            current = values[child.tag]
            values[child.tag] = (
                current + [value] if isinstance(current, list) else [current, value]
            )
        else:
            values[child.tag] = value
    return values


def _parse_response(response: requests.Response) -> dict[str, Any]:
    try:
        parsed = response.json()
        if not isinstance(parsed, dict):
            raise PublicDataApiError("API response root must be an object")
        return parsed
    except JSONDecodeError:
        try:
            return _element_to_value(ElementTree.fromstring(response.text))
        except ElementTree.ParseError as error:
            raise PublicDataApiError(
                f"API returned neither JSON nor XML (HTTP {response.status_code})"
            ) from error


def _as_items(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if isinstance(value, dict):
        item = value.get("item", value)
    else:
        item = value
    if isinstance(item, dict):
        return [item]
    if isinstance(item, list):
        return [entry for entry in item if isinstance(entry, dict)]
    return []


def decode_page(payload: dict[str, Any], requested_page: int) -> ApiPage:
    response = payload.get("response", payload)
    if not isinstance(response, dict):
        raise PublicDataApiError("API response field is not an object")
    header = response.get("header", {})
    if not isinstance(header, dict):
        header = {}
    code = str(header.get("resultCode", response.get("resultCode", "00")))
    message = str(header.get("resultMsg", response.get("resultMsg", "")))
    if code not in SUCCESS_CODES:
        raise PublicDataApiError(f"data.go.kr error {code}: {message}")

    body = response.get("body", response)
    if not isinstance(body, dict):
        body = {}
    items = _as_items(body.get("items", body.get("item")))
    page_number = int(body.get("pageNo") or response.get("pageNo") or requested_page)
    total_count = int(body.get("totalCount") or response.get("totalCount") or len(items))
    return ApiPage(items=items, page_number=page_number, total_count=total_count)


class PublicDataClient:
    def __init__(self, api_key: str | None = None, *, timeout: int = 30) -> None:
        self.api_key = api_key or get_public_data_api_key()
        self.timeout = timeout
        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def fetch_page(
        self,
        operation: ApiOperation,
        *,
        page_number: int,
        rows_per_page: int,
        filters: dict[str, str] | None = None,
    ) -> ApiPage:
        params = {
            "serviceKey": self.api_key,
            "resultType": "json",
            "pageNo": page_number,
            "numOfRows": rows_per_page,
            **(filters or {}),
        }
        try:
            response = self.session.get(
                operation.url, params=params, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.RequestException as error:
            # requests exception strings may contain the fully rendered URL,
            # including serviceKey. Never propagate that text to logs.
            raise PublicDataApiError(
                f"data.go.kr request failed for "
                f"{operation.dataset}/{operation.name}: "
                f"{type(error).__name__}"
            ) from None
        return decode_page(_parse_response(response), page_number)

    def fetch_items(
        self,
        operation: ApiOperation,
        *,
        rows_per_page: int = 100,
        max_pages: int = 1,
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        collected: list[dict[str, Any]] = []
        for page_number in range(1, max_pages + 1):
            page = self.fetch_page(
                operation,
                page_number=page_number,
                rows_per_page=rows_per_page,
                filters=filters,
            )
            collected.extend(page.items)
            if not page.items or len(collected) >= page.total_count:
                break
        return collected
