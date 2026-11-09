import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, Response
from pydantic import SecretStr
from pydantic_ai import (
    ModelHTTPError,
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.google import GoogleModel

from src.chat.agent import mentioned_campaign_numbers
from src.chat.langchain_agent import LangChainChatModel
from src.chat.router import get_agent_backend, get_chat_model, get_recall_client
from src.chat.schemas import ChatMessage, ChatRequest
from src.core.config import Settings, get_settings
from src.main import app
from src.recalls.client import RecallClient
from tests.test_recall_client import NHTSA_RECALL, cpsc_recall


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


def use_recall_api(handler: Any) -> None:
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
def test_chat_returns_503_when_gemini_key_missing(api_key: SecretStr | None) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(gemini_api_key=api_key)
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 503


def test_chat_builds_gemini_model_from_settings() -> None:
    model = get_chat_model(
        Settings(
            gemini_api_key=SecretStr("test-key"),
            gemini_model="gemini-x-flash",
            gemini_fallback_models=[],
        )
    )

    assert isinstance(model, GoogleModel)
    assert model.model_name == "gemini-x-flash"


def test_chat_builds_fallback_chain_without_duplicates() -> None:
    model = get_chat_model(
        Settings(
            gemini_api_key=SecretStr("test-key"),
            gemini_model="gemini-a",
            gemini_fallback_models=["gemini-b", "gemini-a", "gemini-c"],
        )
    )

    assert isinstance(model, FallbackModel)
    assert [m.model_name for m in model.models] == ["gemini-a", "gemini-b", "gemini-c"]


def overloaded(*_: Any) -> ModelResponse:
    raise ModelHTTPError(503, "gemini-a", {"error": {"status": "UNAVAILABLE"}})


def test_chat_falls_back_when_primary_model_is_overloaded() -> None:
    def backup(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        output = {"answer": "Answered by the backup model.", "cited_recall_ids": []}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    app.dependency_overrides[get_chat_model] = lambda: FallbackModel(
        FunctionModel(overloaded), FunctionModel(backup)
    )
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 200
    assert response.json()["answer"] == "Answered by the backup model."


def test_chat_returns_502_when_all_models_fail() -> None:
    app.dependency_overrides[get_chat_model] = lambda: FallbackModel(
        FunctionModel(overloaded), FunctionModel(overloaded)
    )
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 502


@pytest.mark.parametrize(
    "messages",
    [[], [user("hi"), {"role": "assistant", "content": "hello"}], [user("")]],
)
def test_chat_rejects_invalid_conversations(messages: list[dict[str, str]]) -> None:
    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(lambda *_: ModelResponse([]))
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    assert post_chat({"messages": messages}).status_code == 422


def test_chat_answers_from_tool_results_with_retrieved_sources() -> None:
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
            "cited_recall_ids": ["18V268000"],
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(model)
    use_recall_api(lambda _: httpx.Response(200, json={"results": [NHTSA_RECALL]}))

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
    use_recall_api(lambda _: httpx.Response(503, text="down"))

    response = post_chat({"messages": [user("Recalls for 2018 Honda Accord?")]})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "I couldn't reach NHTSA right now.",
        "sources": [],
        "backend": "pydantic_ai",
    }


def test_chat_rejects_invalid_vin_before_calling_nhtsa() -> None:
    calls: list[httpx.Request] = []
    feedback: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        parts = [part for message in messages for part in message.parts]
        # ModelRetry may surface as a RetryPromptPart or ToolReturnPart depending on
        # the pydantic-ai version, so key off the earlier tool call instead.
        retried = any(
            isinstance(part, ToolCallPart) and part.tool_name == "decode_vin" for part in parts
        )
        feedback.extend(
            str(part.content)
            for part in parts
            if isinstance(part, RetryPromptPart | ToolReturnPart) and part.tool_name == "decode_vin"
        )
        if not retried:
            return ModelResponse(parts=[ToolCallPart("decode_vin", {"vin": "OOPS"})])
        output = {"answer": "That VIN looks invalid. Please re-check it.", "cited_recall_ids": []}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(model)
    use_recall_api(lambda request: calls.append(request) or httpx.Response(200, json={}))

    response = post_chat({"messages": [user("My VIN is OOPS")]})

    assert response.status_code == 200
    assert calls == []
    assert any("17 letters" in text for text in feedback)


@pytest.mark.parametrize(("failures", "status"), [(2, 200), (3, 502)])
def test_chat_limits_invalid_structured_answers(failures: int, status: int) -> None:
    model_calls: list[list[ModelMessage]] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        model_calls.append(messages)
        name = info.output_tools[0].name
        if len(model_calls) <= failures:
            return ModelResponse(parts=[ToolCallPart(name, {"cited_recall_ids": []})])
        output = {"answer": "Please tell me the year, make, and model.", "cited_recall_ids": []}
        return ModelResponse(parts=[ToolCallPart(name, output)])

    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(model)
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Is my car recalled?")]})

    assert response.status_code == status


def test_chat_returns_502_when_tool_exceeds_retries() -> None:
    model_calls: list[list[ModelMessage]] = []
    calls: list[httpx.Request] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        model_calls.append(messages)
        return ModelResponse(parts=[ToolCallPart("decode_vin", {"vin": "OOPS"})])

    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(model)
    use_recall_api(lambda request: calls.append(request) or httpx.Response(200, json={}))

    response = post_chat({"messages": [user("My VIN is OOPS")]})

    # retries=2: two failures are fed back to the model, the third fails the run.
    assert response.status_code == 502
    assert len(model_calls) == 3
    assert calls == []


def retry_feedback(messages: list[ModelMessage]) -> list[str]:
    # Output validation feedback may arrive as a RetryPromptPart or as a ToolReturnPart for
    # the output tool, depending on the pydantic-ai version.
    return [
        str(part.content)
        for message in messages
        for part in message.parts
        if isinstance(part, RetryPromptPart)
        or (isinstance(part, ToolReturnPart) and part.tool_name == "final_result")
    ]


def accord_recall_model(answers: list[dict[str, Any]], feedback: list[str]) -> FunctionModel:
    """Search NHTSA once, then return each answer in turn as the model's output."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if not tool_returns(messages):
            args = {"make": "Honda", "model": "Accord", "model_year": 2018}
            return ModelResponse(parts=[ToolCallPart("search_vehicle_recalls", args)])
        feedback[:] = retry_feedback(messages)
        output = answers[min(len(feedback), len(answers) - 1)]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return FunctionModel(model)


@pytest.mark.parametrize(
    "unsupported",
    [
        {
            "answer": "Recall 18V268000 and 99V999000 both affect this car.",
            "cited_recall_ids": ["18V268000", "99V999000"],
        },
        {
            "answer": "Recall 18V268000 applies. Recall 99V-999 also covers the airbags.",
            "cited_recall_ids": ["18V268000"],
        },
    ],
    ids=["cited", "mentioned-only"],
)
def test_chat_makes_model_correct_unretrieved_recalls(unsupported: dict[str, Any]) -> None:
    feedback: list[str] = []
    corrected = {"answer": "Recall 18V268000 applies.", "cited_recall_ids": ["18V268000"]}
    app.dependency_overrides[get_chat_model] = lambda: accord_recall_model(
        [unsupported, corrected], feedback
    )
    use_recall_api(lambda _: httpx.Response(200, json={"results": [NHTSA_RECALL]}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Recall 18V268000 applies."
    assert [source["id"] for source in body["sources"]] == ["18V268000"]
    assert len(feedback) == 1
    assert "99V999000" in feedback[0]


def test_chat_never_publishes_persistently_unsupported_recalls() -> None:
    feedback: list[str] = []
    unsupported = {
        "answer": "Recall 99V999000 means you should stop driving.",
        "cited_recall_ids": ["99V999000"],
    }
    app.dependency_overrides[get_chat_model] = lambda: accord_recall_model([unsupported], feedback)
    use_recall_api(lambda _: httpx.Response(200, json={"results": [NHTSA_RECALL]}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 502
    assert "99V999000" not in response.text
    assert feedback


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("See 18V268000 and 20v-123.", ["18V268000", "20V123000"]),
        ("Campaign 24E012345 (equipment).", ["24E012345"]),
        ("Call 1-888-327-4236 or visit nhtsa.gov in 2018.", []),
    ],
)
def test_mentioned_campaign_numbers(text: str, expected: list[str]) -> None:
    assert mentioned_campaign_numbers(text) == expected


def tool_feedback(messages: list[ModelMessage], tool_name: str) -> list[str]:
    # ModelRetry may surface as a RetryPromptPart or ToolReturnPart depending on the
    # pydantic-ai version.
    return [
        str(part.content)
        for message in messages
        for part in message.parts
        if isinstance(part, RetryPromptPart | ToolReturnPart) and part.tool_name == tool_name
    ]


def stroller_search_model(
    answers: list[dict[str, Any]], seen_results: list[dict[str, Any]], feedback: list[str]
) -> FunctionModel:
    """Search the CPSC for Acme strollers once, then return each answer in turn."""

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        returns = tool_returns(messages)
        if not returns:
            args = {"product_name": "stroller", "manufacturer": "Acme"}
            return ModelResponse(parts=[ToolCallPart("search_product_recalls", args)])
        seen_results[:] = [returns[0].model_response_object()]
        feedback[:] = retry_feedback(messages)
        output = answers[min(len(feedback), len(answers) - 1)]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    return FunctionModel(model)


def test_chat_answers_from_cpsc_search_with_verified_sources() -> None:
    requests: list[httpx.Request] = []
    seen_results: list[dict[str, Any]] = []
    feedback: list[str] = []
    no_url = cpsc_recall("25002", "2025-02-01") | {"URL": None}

    def cpsc(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[cpsc_recall("25001", "2025-03-01"), no_url])

    # Recall 25002 has no CPSC URL, so it is never registered as a source and can't be cited.
    answers = [
        {
            "answer": "Recalls 25001 and 25002 cover Acme strollers.",
            "cited_recall_ids": ["25001", "25002"],
        },
        {
            "answer": "Recall 25001: the frame can break. Get a refund.",
            "cited_recall_ids": ["25001"],
        },
    ]
    app.dependency_overrides[get_chat_model] = lambda: stroller_search_model(
        answers, seen_results, feedback
    )
    use_recall_api(cpsc)

    response = post_chat({"messages": [user("Any recalls on Acme strollers?")]})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Recall 25001: the frame can break. Get a refund.",
        "sources": [
            {
                "id": "25001",
                "agency": "CPSC",
                "title": "Stroller recall 25001",
                "url": "https://www.cpsc.gov/Recalls/25001",
            }
        ],
        "backend": "pydantic_ai",
    }
    assert [request.url.path for request in requests] == ["/RestWebServices/Recall"]
    assert requests[0].url.params["ProductName"] == "stroller"
    assert requests[0].url.params["Manufacturer"] == "Acme"
    assert seen_results[0]["total_found"] == 2
    assert len(feedback) == 1
    assert "25002" in feedback[0]


def test_chat_reports_unavailable_cpsc_source_to_model() -> None:
    seen_results: list[dict[str, Any]] = []
    answer = {"answer": "I couldn't reach the CPSC right now.", "cited_recall_ids": []}
    app.dependency_overrides[get_chat_model] = lambda: stroller_search_model(
        [answer], seen_results, []
    )
    use_recall_api(lambda _: httpx.Response(503, text="down"))

    response = post_chat({"messages": [user("Any recalls on Acme strollers?")]})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "I couldn't reach the CPSC right now.",
        "sources": [],
        "backend": "pydantic_ai",
    }
    assert seen_results[0]["agency"] == "CPSC"
    assert "503" in seen_results[0]["error"]


def test_chat_requires_cpsc_search_terms_before_calling_cpsc() -> None:
    calls: list[httpx.Request] = []
    feedback: list[str] = []

    def model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        parts = [part for message in messages for part in message.parts]
        retried = any(
            isinstance(part, ToolCallPart) and part.tool_name == "search_product_recalls"
            for part in parts
        )
        feedback.extend(tool_feedback(messages, "search_product_recalls"))
        if not retried:
            args = {"recall_date_start": "2025-01-01"}
            return ModelResponse(parts=[ToolCallPart("search_product_recalls", args)])
        output = {"answer": "Which product or brand should I check?", "cited_recall_ids": []}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    app.dependency_overrides[get_chat_model] = lambda: FunctionModel(model)
    use_recall_api(lambda request: calls.append(request) or httpx.Response(200, json=[]))

    response = post_chat({"messages": [user("Any product recalls this year?")]})

    assert response.status_code == 200
    assert calls == []
    assert any("product_name, manufacturer, or recall_number" in text for text in feedback)


def test_chat_config_reports_backend_selection_and_voice_input() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        agent_backend="langchain", allow_backend_selection=True, stt_url="http://stt:8000"
    )

    async def request() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/chat/config")

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json() == {
        "default_backend": "langchain",
        "backend_selection": True,
        "voice_input": True,
    }


@pytest.mark.parametrize(
    ("allow", "requested", "expected"),
    [
        (True, "langchain", "langchain"),
        (True, None, "pydantic_ai"),
        (False, "langchain", "pydantic_ai"),
    ],
)
def test_agent_backend_honors_request_only_when_selection_allowed(
    allow: bool, requested: str | None, expected: str
) -> None:
    body = ChatRequest(messages=[ChatMessage(role="user", content="hi")], backend=requested)
    settings = Settings(allow_backend_selection=allow)

    assert get_agent_backend(body, settings) == expected


def test_chat_builds_model_for_selected_backend() -> None:
    settings = Settings(gemini_api_key=SecretStr("test-key"), gemini_fallback_models=[])

    assert isinstance(get_chat_model(settings, "langchain"), LangChainChatModel)
    assert isinstance(get_chat_model(settings, "pydantic_ai"), GoogleModel)
