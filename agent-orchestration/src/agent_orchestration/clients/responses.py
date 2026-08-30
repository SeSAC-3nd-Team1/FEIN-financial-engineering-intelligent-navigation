import httpx
from azure.core.exceptions import ClientAuthenticationError
from azure.core.credentials_async import AsyncTokenCredential
from pydantic import ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_orchestration.contracts import AgentReport, AgentRequest, extract_json_object


class AgentClientError(RuntimeError):
    pass


class AgentEndpointError(AgentClientError):
    pass


class AgentRequestError(AgentClientError):
    def __init__(self, status_code: int | None = None) -> None:
        message = "agent request failed"
        if status_code is not None:
            message = f"{message} (status={status_code})"
        super().__init__(message)


class AgentAuthenticationError(AgentClientError):
    pass


class AgentResponseError(AgentClientError):
    pass


class RetryableAgentError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"retryable agent status {status_code}")


class ResponsesAgentClient:
    def __init__(
        self,
        endpoint: str,
        credential: AsyncTokenCredential,
        http: httpx.AsyncClient,
    ) -> None:
        try:
            endpoint_url = httpx.URL(endpoint)
        except httpx.InvalidURL:
            raise AgentEndpointError("agent endpoint is invalid") from None
        if endpoint_url.scheme != "https":
            raise AgentEndpointError("agent endpoint must use HTTPS")

        self._endpoint = endpoint_url.copy_set_param("api-version", "v1")
        self._credential = credential
        self._http = http

    async def invoke(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> AgentReport:
        try:
            return await self._invoke_with_retry(
                request,
                timeout_seconds=timeout_seconds,
                idempotency_key=idempotency_key,
            )
        except ClientAuthenticationError:
            pass
        except RetryableAgentError as error:
            raise AgentRequestError(error.status_code) from None
        except httpx.HTTPStatusError as error:
            raise AgentRequestError(error.response.status_code) from None
        except httpx.HTTPError:
            raise AgentRequestError() from None
        except AgentClientError:
            raise
        except (AttributeError, TypeError, ValidationError, ValueError):
            raise AgentResponseError("agent response was invalid") from None

        raise AgentAuthenticationError("agent authentication failed")

    async def invoke_text(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> str:
        """Invoke the agent and return output text without JSON validation."""
        try:
            return await self._invoke_text_with_retry(
                request,
                timeout_seconds=timeout_seconds,
                idempotency_key=idempotency_key,
            )
        except ClientAuthenticationError:
            raise AgentAuthenticationError("agent authentication failed") from None
        except RetryableAgentError as error:
            raise AgentRequestError(error.status_code) from None
        except httpx.HTTPStatusError as error:
            raise AgentRequestError(error.response.status_code) from None
        except httpx.HTTPError:
            raise AgentRequestError() from None
        except AgentClientError:
            raise
        except (AttributeError, TypeError, ValueError):
            raise AgentResponseError("agent response was invalid") from None

    @retry(
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.NetworkError, RetryableAgentError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.25, min=0.25, max=2),
        reraise=True,
    )
    async def _invoke_text_with_retry(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> str:
        token = await self._credential.get_token("https://ai.azure.com/.default")
        response = await self._http.post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            json={
                "input": request.user_query,
                "metadata": {"request_id": request.request_id},
            },
            timeout=timeout_seconds,
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableAgentError(response.status_code)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response payload must be an object")
        output_text = payload.get("output_text")
        if not isinstance(output_text, str):
            output_text = "".join(
                content.get("text", "")
                for item in payload.get("output", [])
                if isinstance(item, dict)
                for content in item.get("content", [])
                if isinstance(content, dict) and content.get("type") == "output_text"
            )
        if not output_text.strip():
            raise ValueError("response output was empty")
        return output_text

    @retry(
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.NetworkError, RetryableAgentError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.25, min=0.25, max=2),
        reraise=True,
    )
    async def _invoke_with_retry(
        self,
        request: AgentRequest,
        *,
        timeout_seconds: float,
        idempotency_key: str,
    ) -> AgentReport:
        token = await self._credential.get_token("https://ai.azure.com/.default")
        response = await self._http.post(
            self._endpoint,
            headers={
                "Authorization": f"Bearer {token.token}",
                "Content-Type": "application/json",
                "Idempotency-Key": idempotency_key,
            },
            json={
                "input": request.user_query,
                "metadata": {"request_id": request.request_id},
            },
            timeout=timeout_seconds,
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            raise RetryableAgentError(response.status_code)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response payload must be an object")
        output_text = payload.get("output_text")
        if not isinstance(output_text, str):
            output_text = "".join(
                content.get("text", "")
                for item in payload.get("output", [])
                if isinstance(item, dict)
                for content in item.get("content", [])
                if isinstance(content, dict) and content.get("type") == "output_text"
            )
        report = AgentReport.model_validate(extract_json_object(output_text))
        if report.agent != request.role or (
            report.request_id is not None and report.request_id != request.request_id
        ):
            raise AgentResponseError("agent response identity did not match the request")
        return report
