"""data.go.kr 응답의 JSON/XML 차이와 pagination을 안전하게 처리하는 API client다."""

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
    """공공데이터 API가 오류 header 또는 해석 불가능한 응답을 반환했을 때 사용한다."""


class PublicDataUnavailableError(PublicDataApiError):
    """공급자 연결 또는 응답 timeout으로 현재 수집을 진행할 수 없을 때 사용한다."""


@dataclass(frozen=True)
class ApiPage:
    """한 API page에서 downstream 수집 로직에 필요한 값만 보관한다."""

    items: list[dict[str, Any]]
    page_number: int
    total_count: int


def get_public_data_api_key() -> str:
    """저장소 root의 환경설정에서 API key를 읽고 코드에는 secret을 남기지 않는다."""

    load_dotenv(PROJECT_ROOT / ".env", override=False)
    api_key = os.getenv("DATA_GO_KR_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "DATA_GO_KR_API_KEY is required in the repository root .env file."
        )
    return api_key


def _element_to_value(element: ElementTree.Element) -> Any:
    """XML 응답을 JSON 응답과 유사한 중첩 dict/list 구조로 변환한다."""

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
    """JSON을 우선 해석하고 실패할 때만 XML fallback을 사용한다."""

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
    """API별로 다른 단일 item/list 응답을 항상 list[dict] 형태로 맞춘다."""

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
    """data.go.kr의 공통 header/body 구조를 검증하고 한 page로 정규화한다."""

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
    """공공데이터 API 호출에 timeout과 일시적 오류 retry 정책을 공통 적용한다."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        connect_timeout: float = 10,
        read_timeout: float = 30,
    ) -> None:
        self.api_key = api_key or get_public_data_api_key()
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("public data timeouts must be positive")
        self.timeout = (connect_timeout, read_timeout)
        self.session = requests.Session()
        # 연결 실패는 한 번만 재시도해 공급자 전체 장애 때 52개 endpoint가 각각 장시간
        # 대기하지 않게 한다. 응답을 받은 뒤의 429/5xx는 기존처럼 제한적으로 재시도한다.
        retry = Retry(
            total=3,
            connect=1,
            read=2,
            status=3,
            other=0,
            backoff_factor=0.5,
            backoff_jitter=0.25,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
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
        """operation의 지정 page를 호출하되 secret이 오류 로그에 섞이지 않게 한다."""

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
        except (requests.ConnectionError, requests.Timeout) as error:
            # 같은 host의 모든 operation을 순회해도 회복 가능성이 낮으므로 caller가
            # fail-fast 여부를 결정할 수 있게 별도 예외로 구분한다.
            raise PublicDataUnavailableError(
                f"data.go.kr unavailable for "
                f"{operation.dataset}/{operation.name}: "
                f"{type(error).__name__}"
            ) from None
        except requests.RequestException as error:
            # requests 예외 문자열에는 serviceKey가 포함된 완성 URL이 들어갈 수 있다.
            # 따라서 원문 예외 메시지는 버리고 예외 타입만 운영 로그에 남긴다.
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
        """여러 page를 읽되 API의 totalCount에 도달하면 불필요한 호출을 중단한다."""

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
