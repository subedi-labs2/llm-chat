"""LangChain implementation of the recall agent, selected with AGENT_BACKEND=langchain.

It mirrors the Pydantic AI agent in src.chat.agent: same instructions, tools, output schema,
grounding check, model fallback, and usage limits. Only the framework differs.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from google.genai.errors import APIError
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallLimitMiddleware,
    ToolCallRequest,
    ToolErrorMiddleware,
)
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from langchain.agents.structured_output import StructuredOutputError, ToolStrategy
from langchain.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langchain.tools import ToolRuntime, tool
from langchain_core.exceptions import LangChainException
from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import ChatGoogleGenerativeAIError
from langgraph.errors import GraphRecursionError
from pydantic import SecretStr

from src.chat.agent import (
    INSTRUCTIONS,
    USAGE_LIMITS,
    VIN_PATTERN,
    ChatAnswer,
    ChatDeps,
    grounding_feedback,
    record_product_sources,
    record_vehicle_sources,
    with_unique_citations,
)
from src.chat.schemas import ChatMessage
from src.recalls.client import RecallSourceError
from src.recalls.schemas import SourceUnavailable

# Matches the Pydantic AI agent's retries=2 for output validation.
MAX_OUTPUT_RETRIES = 2


@dataclass
class LangChainChatModel:
    """A primary chat model and the models tried in order when it fails."""

    primary: BaseChatModel
    fallbacks: list[BaseChatModel] = field(default_factory=list)


@dataclass
class LangChainDeps(ChatDeps):
    output_retries: int = 0


class ToolRetry(Exception):
    """Raised by a tool to send correction feedback to the model, like Pydantic AI's ModelRetry."""


class UngroundedAnswerError(Exception):
    """The model kept referencing recalls that no tool returned."""


# Failures that should surface as a 502 from /api/chat.
LANGCHAIN_RUN_ERRORS: tuple[type[Exception], ...] = (
    APIError,
    ChatGoogleGenerativeAIError,
    GraphRecursionError,
    LangChainException,
    ModelCallLimitExceededError,
    StructuredOutputError,
    ToolCallLimitExceededError,
    UngroundedAnswerError,
)


def gemini_chat_model(
    model_names: list[str], api_key: str, retry_attempts: int
) -> LangChainChatModel:
    models: list[BaseChatModel] = [
        ChatGoogleGenerativeAI(
            model=name, google_api_key=SecretStr(api_key), max_retries=max(retry_attempts, 1)
        )
        for name in model_names
    ]
    return LangChainChatModel(primary=models[0], fallbacks=models[1:])


def to_langchain_messages(messages: list[ChatMessage]) -> list[AnyMessage]:
    return [
        HumanMessage(message.content) if message.role == "user" else AIMessage(message.content)
        for message in messages
    ]


def to_json(result: Any) -> dict[str, Any]:
    return result.model_dump(mode="json")


@tool
async def decode_vin(vin: str, runtime: ToolRuntime[LangChainDeps]) -> dict[str, Any]:
    """Decode a 17-character VIN into make, model, and model year using NHTSA vPIC."""
    normalized = vin.strip().upper()
    if not VIN_PATTERN.fullmatch(normalized):
        raise ToolRetry(
            "A VIN has 17 letters and digits and never contains I, O, or Q. "
            "Ask the user to double-check it."
        )
    try:
        return to_json(await runtime.context.recalls.decode_vin(normalized))
    except RecallSourceError as exc:
        return to_json(SourceUnavailable(agency="NHTSA", error=str(exc)))


@tool(parse_docstring=True)
async def search_vehicle_recalls(
    make: str, model: str, model_year: int, runtime: ToolRuntime[LangChainDeps]
) -> dict[str, Any]:
    """Search NHTSA for recalls on a vehicle by make, model, and model year.

    Args:
        make: Vehicle make, for example "Honda".
        model: Vehicle model, for example "Accord".
        model_year: Four-digit model year.
    """
    if not 1949 <= model_year <= date.today().year + 2:
        raise ToolRetry("model_year must be a realistic four-digit year.")
    try:
        results = await runtime.context.recalls.search_vehicle_recalls(
            make.strip(), model.strip(), model_year
        )
    except RecallSourceError as exc:
        return to_json(SourceUnavailable(agency="NHTSA", error=str(exc)))
    record_vehicle_sources(results, runtime.context.sources)
    return to_json(results)


@tool(parse_docstring=True)
async def search_product_recalls(
    runtime: ToolRuntime[LangChainDeps],
    product_name: str | None = None,
    manufacturer: str | None = None,
    recall_number: str | None = None,
    recall_date_start: date | None = None,
) -> dict[str, Any]:
    """Search CPSC consumer product recalls. Results are sorted newest first.

    Args:
        product_name: Product name keywords, for example "stroller" or "space heater".
        manufacturer: Brand or manufacturer name.
        recall_number: CPSC recall number, if known.
        recall_date_start: Only return recalls announced on or after this date.
    """
    if not any([product_name, manufacturer, recall_number]):
        raise ToolRetry("Provide at least one of product_name, manufacturer, or recall_number.")
    try:
        results = await runtime.context.recalls.search_product_recalls(
            product_name=product_name,
            manufacturer=manufacturer,
            recall_number=recall_number,
            recall_date_start=recall_date_start,
        )
    except RecallSourceError as exc:
        return to_json(SourceUnavailable(agency="CPSC", error=str(exc)))
    record_product_sources(results, runtime.context.sources)
    return to_json(results)


TOOLS = [decode_vin, search_vehicle_recalls, search_product_recalls]


def tool_retry_feedback(exc: Exception, _: ToolCallRequest) -> str | None:
    # Returning None lets every other exception propagate instead of reaching the model.
    return str(exc) if isinstance(exc, ToolRetry) else None


class RequireRetrievedRecalls(AgentMiddleware[Any, LangChainDeps]):
    """Reject answers that cite or mention recalls not retrieved by a tool in this request.

    Rejected answers are returned to the model as an error on its structured-output tool call,
    which makes the agent loop ask the model again.
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[LangChainDeps],
        handler: Callable[[ModelRequest[LangChainDeps]], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        response = await handler(request)
        output = response.structured_response
        if not isinstance(output, ChatAnswer):
            return response
        deps = request.runtime.context
        feedback = grounding_feedback(output, deps.sources)
        if feedback is None:
            return ModelResponse(
                result=response.result, structured_response=with_unique_citations(output)
            )
        if deps.output_retries >= MAX_OUTPUT_RETRIES:
            raise UngroundedAnswerError(feedback)
        deps.output_retries += 1
        message = next(m for m in response.result if isinstance(m, AIMessage))
        call = next(c for c in message.tool_calls if c["name"] == ChatAnswer.__name__)
        retry = ToolMessage(feedback, tool_call_id=call["id"], name=call["name"], status="error")
        return ModelResponse(result=[message, retry])


async def run_langchain_agent(
    model: LangChainChatModel, messages: list[ChatMessage], deps: LangChainDeps
) -> ChatAnswer:
    # The model is chosen per request, so the agent graph is built per request too.
    fallback = [ModelFallbackMiddleware(*model.fallbacks)] if model.fallbacks else []
    agent = create_agent(
        model.primary,
        tools=TOOLS,
        system_prompt=INSTRUCTIONS.format(today=date.today().isoformat()),
        response_format=ToolStrategy(ChatAnswer),
        context_schema=LangChainDeps,
        middleware=[
            RequireRetrievedRecalls(),
            *fallback,
            ToolErrorMiddleware(on_error=tool_retry_feedback),
            ModelCallLimitMiddleware(run_limit=USAGE_LIMITS.request_limit, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=USAGE_LIMITS.tool_calls_limit, exit_behavior="error"),
        ],
    )
    state = await agent.ainvoke({"messages": to_langchain_messages(messages)}, context=deps)
    return state["structured_response"]
