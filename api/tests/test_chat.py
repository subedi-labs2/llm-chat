import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
from pydantic_ai import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.chat.router import get_chat_model, get_recall_client
from src.core.config import Settings, get_settings
from src.main import app
from src.recalls.client import RecallClient
from tests.test_recall_client import NHTSA_RECALL


def post_chat(payload: dict[str, Any]) -> Response:
    async def request() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/chat", json=payload)

    return asyncio.run(request())


def user(content: str) -> dict[str, str]:
    return {"role": "user", "content": content}


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def use_nhtsa(handler: Any) -> None:
    def client() -> RecallClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return RecallClient(http, Settings())

    app.dependency_overrides[get_recall_client] = client


def tool_returns(messages: list[ModelMessage]) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name != "final_result"
    ]


@pytest.mark.parametrize("api_key", [None, SecretStr("")])
def test_chat_returns_503_when_openai_key_missing(api_key: SecretStr | None) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(openai_api_key=api_key)
    use_nhtsa(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 503


def test_chat_builds_openai_model_from_settings() -> None:
    model = get_chat_model(Settings(openai_api_key=SecretStr("sk-test"), openai_model="gpt-x"))

    assert model.model_name == "gpt-x"


@pytest.mark.parametrize(
    "messages",
    [[], [user("hi"), {"role": "assistant", "content": "hello"}], [user("")]],
)
def test_chat_rejects_invalid_conversations(messages: list[dict[str, str]]) -> None:
    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(lambda *_: ModelResponse([]))
    use_nhtsa(lambda _: httpx.Response(200, json={"results": []}))

    assert post_chat({"messages": messages}).status_code == 422


def test_chat_answers_from_tool_results_and_only_cites_retrieved_recalls() -> None:
    seen_history: list[list[ModelMessage]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen_history.append(messages)
        returns = tool_returns(messages)
        if not returns:
            args = {"make": "Honda", "model": "Accord", "model_year": 2018}
            return ModelResponse(parts=[ToolCallPart("search_vehicle_recalls", args)])
        assert returns[0].model_response_object()["total_found"] == 1
        output = {
            "answer": "Recall 18V268000: park outside. The wiring may short.",
            "cited_recall_ids": ["18V268000", "99V999000"],
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(model)
    use_nhtsa(lambda _: httpx.Response(200, json={"results": [NHTSA_RECALL]}))

    response = post_chat(
        {
            "messages": [
                user("Is my car recalled?"),
                {"role": "assistant", "content": "What year, make, and model?"},
                user("2018 Honda Accord"),
            ]
        }
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Recall 18V268000")
    assert body["sources"] == [
        {
            "id": "18V268000",
            "agency": "NHTSA",
            "title": "2018 HONDA ACCORD: ELECTRICAL SYSTEM",
            "url": "https://www.nhtsa.gov/recalls?nhtsaId=18V268000",
        }
    ]
    first_request_text = [
        part.content
        for message in seen_history[0]
        for part in message.parts
        if isinstance(part, TextPart | UserPromptPart)
    ]
    assert "What year, make, and model?" in first_request_text
    assert "2018 Honda Accord" in first_request_text


def test_chat_reports_unavailable_source_to_model() -> None:
    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = tool_returns(messages)
        if not returns:
            args = {"make": "Honda", "model": "Accord", "model_year": 2018}
            return ModelResponse(parts=[ToolCallPart("search_vehicle_recalls", args)])
        assert returns[0].model_response_object()["agency"] == "NHTSA"
        output = {"answer": "I couldn't reach NHTSA right now.", "cited_recall_ids": []}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(model)
    use_nhtsa(lambda _: httpx.Response(503, text="down"))

    response = post_chat({"messages": [user("Recalls for 2018 Honda Accord?")]})

    assert response.status_code == 200
    assert response.json() == {"answer": "I couldn't reach NHTSA right now.", "sources": []}


def test_chat_rejects_invalid_vin_before_calling_nhtsa() -> None:
    calls: list[httpx.Request] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        retried = any(
            isinstance(part, ToolReturnPart) and part.tool_name == "decode_vin"
            for message in messages
            for part in message.parts
        )
        if not retried:
            return ModelResponse(parts=[ToolCallPart("decode_vin", {"vin": "OOPS"})])
        output = {"answer": "That VIN looks invalid. Please re-check it.", "cited_recall_ids": []}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(model)
    use_nhtsa(lambda request: calls.append(request) or httpx.Response(200, json={}))

    response = post_chat({"messages": [user("My VIN is OOPS")]})

    assert response.status_code == 200
    assert calls == []
