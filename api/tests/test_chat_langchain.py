import asyncio
import json
from collections.abc import Callable, Iterator, Sequence
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import GoogleRateLimitError
from pydantic import SecretStr
from pydantic_ai import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from src.chat import langchain_agent
from src.chat.langchain_agent import LangChainChatModel, LimitToolRetries, ToolRetry
from src.chat.router import ChatModel, get_agent_backend, get_chat_model
from src.core.config import Settings, get_settings
from src.main import app
from tests.test_chat import post_chat, use_recall_api, user
from tests.test_recall_client import NHTSA_RECALL, cpsc_recall

Script = Callable[[list[BaseMessage]], AIMessage]


class ScriptedChatModel(BaseChatModel):
    """Replies with whatever the script returns, like Pydantic AI's FunctionModel."""

    script: Script

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        return self

    def _generate(self, messages: list[BaseMessage], *_: Any, **__: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self.script(messages))])


def call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}])


def answer(text: str, cited: list[str] | None = None) -> AIMessage:
    return call("ChatAnswer", {"answer": text, "cited_recall_ids": cited or []})


def tool_messages(messages: list[BaseMessage], name: str) -> list[ToolMessage]:
    return [m for m in messages if isinstance(m, ToolMessage) and m.name == name]


def use_model(script: Script, *fallbacks: Script) -> None:
    model = LangChainChatModel(
        primary=ScriptedChatModel(script=script),
        fallbacks=[ScriptedChatModel(script=fallback) for fallback in fallbacks],
    )
    app.dependency_overrides[get_chat_model] = lambda: model


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def test_builds_langchain_gemini_models_without_duplicates() -> None:
    model = get_chat_model(
        Settings(
            agent_backend="langchain",
            gemini_api_key=SecretStr("test-key"),
            gemini_model="gemini-a",
            gemini_fallback_models=["gemini-b", "gemini-a", "gemini-c"],
            gemini_retry_attempts=3,
        )
    )

    assert isinstance(model, LangChainChatModel)
    models = [model.primary, *model.fallbacks]
    assert all(isinstance(m, ChatGoogleGenerativeAI) for m in models)
    assert [m.model for m in models] == ["gemini-a", "gemini-b", "gemini-c"]
    assert model.primary.max_retries == 3


def test_returns_503_when_gemini_key_missing() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(agent_backend="langchain")
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 503


def accord_search(*answers: AIMessage, feedback: list[str] | None = None) -> Script:
    """Search NHTSA once, then reply with each answer in turn."""

    def script(messages: list[BaseMessage]) -> AIMessage:
        if not tool_messages(messages, "search_vehicle_recalls"):
            return call(
                "search_vehicle_recalls", {"make": "Honda", "model": "Accord", "model_year": 2018}
            )
        retries = [str(m.content) for m in tool_messages(messages, "ChatAnswer")]
        if feedback is not None:
            feedback[:] = retries
        return answers[min(len(retries), len(answers) - 1)]

    return script


def test_answers_from_tool_results_with_retrieved_sources() -> None:
    seen: list[list[BaseMessage]] = []
    search = accord_search(answer("Recall 18V268000: park outside.", ["18V268000"]))
    use_model(lambda messages: seen.append(messages) or search(messages))
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
    assert response.json() == {
        "answer": "Recall 18V268000: park outside.",
        "sources": [
            {
                "id": "18V268000",
                "agency": "NHTSA",
                "title": "2018 HONDA ACCORD: ELECTRICAL SYSTEM",
                "url": "https://www.nhtsa.gov/recalls?nhtsaId=18V268000",
            }
        ],
        "backend": "langchain",
    }
    history = [(type(m), m.content) for m in seen[0][1:]]
    assert history == [
        (HumanMessage, "Is my car recalled?"),
        (AIMessage, "What year, make, and model?"),
        (HumanMessage, "2018 Honda Accord"),
    ]
    results = json.loads(str(tool_messages(seen[1], "search_vehicle_recalls")[0].content))
    assert results["total_found"] == 1


@pytest.mark.parametrize(
    "unsupported",
    [
        answer("Recall 18V268000 and 99V999000 apply.", ["18V268000", "99V999000"]),
        answer("Recall 18V268000 applies. Recall 99V-999 too.", ["18V268000"]),
    ],
    ids=["cited", "mentioned-only"],
)
def test_makes_model_correct_unretrieved_recalls(unsupported: AIMessage) -> None:
    feedback: list[str] = []
    corrected = answer("Recall 18V268000 applies.", ["18V268000", " 18V268000"])
    use_model(accord_search(unsupported, corrected, feedback=feedback))
    use_recall_api(lambda _: httpx.Response(200, json={"results": [NHTSA_RECALL]}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 200
    assert response.json()["answer"] == "Recall 18V268000 applies."
    assert [source["id"] for source in response.json()["sources"]] == ["18V268000"]
    assert len(feedback) == 1
    assert "99V999000" in feedback[0]


def test_never_publishes_persistently_unsupported_recalls() -> None:
    feedback: list[str] = []
    unsupported = answer("Recall 99V999000 means you should stop driving.", ["99V999000"])
    use_model(accord_search(unsupported, feedback=feedback))
    use_recall_api(lambda _: httpx.Response(200, json={"results": [NHTSA_RECALL]}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 502
    assert "99V999000" not in response.text
    assert len(feedback) == 2


@pytest.mark.parametrize(("failures", "status"), [(2, 200), (3, 502)])
def test_limits_invalid_structured_answers(failures: int, status: int) -> None:
    feedback: list[str] = []

    def script(messages: list[BaseMessage]) -> AIMessage:
        feedback[:] = [str(m.content) for m in tool_messages(messages, "ChatAnswer")]
        if len(feedback) < failures:
            return call("ChatAnswer", {"cited_recall_ids": []})
        return answer("Please tell me the year, make, and model.")

    use_model(script)
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Is my car recalled?")]})

    assert response.status_code == status
    assert len(feedback) == min(failures, 2)


def test_schema_and_grounding_failures_share_output_retries() -> None:
    replies = [
        lambda: call("ChatAnswer", {"cited_recall_ids": []}),
        lambda: answer("Recall 99V999000 applies."),
        lambda: call("ChatAnswer", {"cited_recall_ids": []}),
    ]

    def script(messages: list[BaseMessage]) -> AIMessage:
        return replies[len(tool_messages(messages, "ChatAnswer"))]()

    use_model(script)
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Is my car recalled?")]})

    assert response.status_code == 502


def test_returns_502_when_model_gives_no_structured_answer() -> None:
    use_model(lambda _: AIMessage(""))
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Is my car recalled?")]})

    assert response.status_code == 502


def test_reports_unavailable_source_to_model() -> None:
    seen: list[str] = []

    def script(messages: list[BaseMessage]) -> AIMessage:
        if results := tool_messages(messages, "search_vehicle_recalls"):
            seen.append(str(results[0].content))
            return answer("I couldn't reach NHTSA right now.")
        return accord_search()(messages)

    use_model(script)
    use_recall_api(lambda _: httpx.Response(503, text="down"))

    response = post_chat({"messages": [user("Recalls for 2018 Honda Accord?")]})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "I couldn't reach NHTSA right now.",
        "sources": [],
        "backend": "langchain",
    }
    assert json.loads(seen[0])["agency"] == "NHTSA"


def test_rejects_invalid_vin_before_calling_nhtsa() -> None:
    calls: list[httpx.Request] = []
    feedback: list[str] = []

    def script(messages: list[BaseMessage]) -> AIMessage:
        if results := tool_messages(messages, "decode_vin"):
            feedback.append(str(results[0].content))
            return answer("That VIN looks invalid. Please re-check it.")
        return call("decode_vin", {"vin": "OOPS"})

    use_model(script)
    use_recall_api(lambda request: calls.append(request) or httpx.Response(200, json={}))

    response = post_chat({"messages": [user("My VIN is OOPS")]})

    assert response.status_code == 200
    assert calls == []
    assert "17 letters" in feedback[0]


@pytest.mark.parametrize("args", [{"vin": "OOPS"}, {"vin": 123}], ids=["tool_retry", "bad_args"])
def test_returns_502_when_tool_exceeds_retries(args: dict[str, Any]) -> None:
    calls: list[httpx.Request] = []
    feedback: list[str] = []

    def script(messages: list[BaseMessage]) -> AIMessage:
        feedback[:] = [str(m.content) for m in tool_messages(messages, "decode_vin")]
        return call("decode_vin", args)

    use_model(script)
    use_recall_api(lambda request: calls.append(request) or httpx.Response(200, json={}))

    response = post_chat({"messages": [user("My VIN is OOPS")]})

    # Like Pydantic AI's retries=2: two failures are fed back, the third fails the run.
    assert response.status_code == 502
    assert len(feedback) == 2
    assert calls == []


def test_successful_tool_call_resets_retries() -> None:
    bad = {"recall_date_start": "2025-01-01"}
    steps = [bad, {"product_name": "stroller"}, bad, bad]

    def script(messages: list[BaseMessage]) -> AIMessage:
        step = len(tool_messages(messages, "search_product_recalls"))
        if step == len(steps):
            return answer("Which stroller brand should I check?")
        return call("search_product_recalls", steps[step])

    use_model(script)
    use_recall_api(lambda _: httpx.Response(200, json=[]))

    response = post_chat({"messages": [user("Any stroller recalls?")]})

    assert response.status_code == 200


def test_counts_failures_in_one_step_as_one_retry() -> None:
    def script(messages: list[BaseMessage]) -> AIMessage:
        if tool_messages(messages, "decode_vin"):
            return answer("Those VINs look invalid. Please re-check them.")
        message = call("decode_vin", {"vin": "OOPS"})
        message.tool_calls = [{**message.tool_calls[0], "id": f"vin-{i}"} for i in range(3)]
        return message

    use_model(script)
    use_recall_api(lambda _: httpx.Response(200, json={}))

    response = post_chat({"messages": [user("My VINs are OOPS, OOPS, and OOPS")]})

    assert response.status_code == 200


@pytest.mark.parametrize("valid_first", [True, False], ids=["valid_first", "invalid_first"])
def test_counts_mixed_parallel_calls_as_failed_step(
    valid_first: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FinishInOrder(LimitToolRetries):
        """Delay one outcome so parallel calls finish in a chosen order."""

        async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
            async def ordered(req: Any) -> Any:
                try:
                    result = await handler(req)
                except ToolRetry:
                    if valid_first:
                        await asyncio.sleep(0.05)
                    raise
                if not valid_first:
                    await asyncio.sleep(0.05)
                return result

            return await super().awrap_tool_call(request, ordered)

    monkeypatch.setattr(langchain_agent, "LimitToolRetries", FinishInOrder)
    bad = {"recall_date_start": "2025-01-01"}

    def script(messages: list[BaseMessage]) -> AIMessage:
        step = len([m for m in messages if isinstance(m, AIMessage)])
        if step > 2:
            return answer("Which stroller brand should I check?")
        message = call("search_product_recalls", bad)
        if step == 2:
            good = {**message.tool_calls[0], "id": "good", "args": {"product_name": "stroller"}}
            message.tool_calls = [message.tool_calls[0], good]
        return message

    use_model(script)
    use_recall_api(lambda _: httpx.Response(200, json=[]))

    response = post_chat({"messages": [user("Any stroller recalls?")]})

    # After two failed steps, a step with any failure exhausts the budget regardless of order.
    assert response.status_code == 502


def test_answers_from_cpsc_search_with_verified_sources() -> None:
    requests: list[httpx.Request] = []
    feedback: list[str] = []
    no_url = cpsc_recall("25002", "2025-02-01") | {"URL": None}

    def cpsc(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[cpsc_recall("25001", "2025-03-01"), no_url])

    answers = [
        answer("Recalls 25001 and 25002 cover Acme strollers.", ["25001", "25002"]),
        answer("Recall 25001: the frame can break.", ["25001"]),
    ]

    def script(messages: list[BaseMessage]) -> AIMessage:
        if not tool_messages(messages, "search_product_recalls"):
            args = {"product_name": "stroller", "manufacturer": "Acme"}
            return call("search_product_recalls", args)
        feedback[:] = [str(m.content) for m in tool_messages(messages, "ChatAnswer")]
        return answers[min(len(feedback), 1)]

    use_model(script)
    use_recall_api(cpsc)

    response = post_chat({"messages": [user("Any recalls on Acme strollers?")]})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Recall 25001: the frame can break.",
        "sources": [
            {
                "id": "25001",
                "agency": "CPSC",
                "title": "Stroller recall 25001",
                "url": "https://www.cpsc.gov/Recalls/25001",
            }
        ],
        "backend": "langchain",
    }
    assert requests[0].url.params["ProductName"] == "stroller"
    assert requests[0].url.params["Manufacturer"] == "Acme"
    assert len(feedback) == 1
    assert "25002" in feedback[0]


def test_requires_cpsc_search_terms_before_calling_cpsc() -> None:
    calls: list[httpx.Request] = []
    feedback: list[str] = []

    def script(messages: list[BaseMessage]) -> AIMessage:
        if results := tool_messages(messages, "search_product_recalls"):
            feedback.append(str(results[0].content))
            return answer("Which product or brand should I check?")
        return call("search_product_recalls", {"recall_date_start": "2025-01-01"})

    use_model(script)
    use_recall_api(lambda request: calls.append(request) or httpx.Response(200, json=[]))

    response = post_chat({"messages": [user("Any product recalls this year?")]})

    assert response.status_code == 200
    assert calls == []
    assert "product_name, manufacturer, or recall_number" in feedback[0]


def overloaded(_: list[BaseMessage]) -> AIMessage:
    raise GoogleRateLimitError("Error calling model 'gemini-a' (RESOURCE_EXHAUSTED)")


def test_falls_back_when_primary_model_fails() -> None:
    use_model(overloaded, lambda _: answer("Answered by the backup model."))
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 200
    assert response.json()["answer"] == "Answered by the backup model."


def test_returns_502_when_all_models_fail() -> None:
    use_model(overloaded, overloaded)
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 502


def test_returns_502_when_tool_call_limit_is_exceeded() -> None:
    use_model(accord_search(call("decode_vin", {"vin": "1HGCV1F30JA000000"})))
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))

    response = post_chat({"messages": [user("Any recalls on a 2018 Honda Accord?")]})

    assert response.status_code == 502


def use_model_per_backend() -> None:
    """Answer with a scripted model for whichever backend the request resolves to."""

    def pydantic_ai(_: Any, info: AgentInfo) -> ModelResponse:
        output = {"answer": "Answered by pydantic_ai.", "cited_recall_ids": []}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, output)])

    def model(backend: Annotated[str, Depends(get_agent_backend)]) -> ChatModel:
        if backend == "langchain":
            return LangChainChatModel(
                primary=ScriptedChatModel(script=lambda _: answer("Answered by langchain."))
            )
        return FunctionModel(pydantic_ai)

    app.dependency_overrides[get_chat_model] = model
    use_recall_api(lambda _: httpx.Response(200, json={"results": []}))


@pytest.mark.parametrize(
    ("allow", "requested", "expected"),
    [
        (True, "langchain", "langchain"),
        (True, "pydantic_ai", "pydantic_ai"),
        (True, None, "pydantic_ai"),
        (False, "langchain", "pydantic_ai"),
    ],
)
def test_chat_runs_requested_backend_only_when_selection_allowed(
    allow: bool, requested: str | None, expected: str
) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(allow_backend_selection=allow)
    use_model_per_backend()

    response = post_chat({"messages": [user("hi")], "backend": requested})

    assert response.status_code == 200
    assert response.json()["answer"] == f"Answered by {expected}."
    assert response.json()["backend"] == expected


def test_chat_rejects_unknown_backend() -> None:
    use_model_per_backend()

    assert post_chat({"messages": [user("hi")], "backend": "other"}).status_code == 422
