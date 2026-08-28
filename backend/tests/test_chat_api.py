from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import optional_current_user
from app.api.routes.chat import get_chat_agent_client
from app.main import app
from app.schemas.chat import ChatAgentResult


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    async def answer(self, message, history, context):
        self.calls.append((message, history, context))
        return ChatAgentResult(
            status="COMPLETED",
            text="화면 맥락을 확인했어요.",
            caution=None,
            suggested_questions=[],
        )


def test_chat_accepts_public_question_without_login() -> None:
    client = FakeClient()
    app.dependency_overrides[get_chat_agent_client] = lambda: client
    try:
        response = TestClient(app).post(
            "/api/v1/chat/messages",
            json={
                "message": "이 화면을 설명해줘",
                "history": [],
                "context": {"screen": "stock", "stock_code": "005930"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert client.calls[0][0] == "이 화면을 설명해줘"


def test_chat_passes_context_for_authenticated_user() -> None:
    client = FakeClient()
    app.dependency_overrides[get_chat_agent_client] = lambda: client
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(id=7)
    try:
        response = TestClient(app).post(
            "/api/v1/chat/messages",
            json={
                "message": "이 화면을 설명해줘",
                "history": [],
                "context": {"screen": "stock", "stock_code": "005930"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
    assert client.calls[0][2].stock_code == "005930"


def test_chat_accepts_authenticated_request_without_exposing_user_to_client() -> None:
    client = FakeClient()
    app.dependency_overrides[get_chat_agent_client] = lambda: client
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(id=7)
    try:
        response = TestClient(app).post(
            "/api/v1/chat/messages",
            json={
                "message": "PER이 뭐야?",
                "history": [{"role": "user", "content": "주식 공부 중이야"}],
                "context": {"screen": "home"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(client.calls[0]) == 3
    assert client.calls[0][1][0].content == "주식 공부 중이야"


def test_chat_requires_login_for_account_context() -> None:
    client = FakeClient()
    app.dependency_overrides[get_chat_agent_client] = lambda: client
    try:
        response = TestClient(app).post(
            "/api/v1/chat/messages",
            json={
                "message": "내 계좌를 보여줘",
                "history": [],
                "context": {
                    "screen": "dashboard",
                    "account_id": "00000000-0000-4000-8000-000000000001",
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert client.calls == []


def test_chat_rejects_unknown_context_fields() -> None:
    client = FakeClient()
    app.dependency_overrides[get_chat_agent_client] = lambda: client
    app.dependency_overrides[optional_current_user] = lambda: SimpleNamespace(id=7)

    try:
        response = TestClient(app).post(
            "/api/v1/chat/messages",
            json={
                "message": "질문",
                "history": [],
                "context": {"screen": "home", "private_value": "secret"},
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert client.calls == []
