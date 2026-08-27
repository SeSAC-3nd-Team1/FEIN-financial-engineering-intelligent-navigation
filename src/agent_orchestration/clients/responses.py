import httpx
from azure.core.credentials_async import AsyncTokenCredential
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_orchestration.contracts import AgentReport, AgentRequest, extract_json_object


class RetryableAgentError(RuntimeError):
    pass


class ResponsesAgentClient:
    def __init__(
        self,
        endpoint: str,
        credential: AsyncTokenCredential,
        http: httpx.AsyncClient,
    ) -> None:
        self._endpoint = endpoint
        self._credential = credential
        self._http = http

    @retry(
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.NetworkError, RetryableAgentError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.25, min=0.25, max=2),
        reraise=True,
    )
    async def invoke(
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
            raise RetryableAgentError(
                f"retryable agent status {response.status_code}"
            )
        response.raise_for_status()
        payload = response.json()
        output_text = payload.get("output_text")
        if not isinstance(output_text, str):
            output_text = "".join(
                content.get("text", "")
                for item in payload.get("output", [])
                for content in item.get("content", [])
                if content.get("type") == "output_text"
            )
        return AgentReport.model_validate(extract_json_object(output_text))
