import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from google.genai.types import HttpRetryOptions
from pydantic_ai import (
    AgentRunError,
    FallbackExceptionGroup,
    ModelAPIError,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from src.chat.agent import USAGE_LIMITS, ChatAnswer, ChatDeps, recall_agent
from src.chat.langchain_agent import (
    LANGCHAIN_RUN_ERRORS,
    LangChainChatModel,
    LangChainDeps,
    gemini_chat_model,
    run_langchain_agent,
)
from src.chat.schemas import ChatConfig, ChatMessage, ChatRequest, ChatResponse
from src.core.config import AgentBackend, Settings, get_settings
from src.recalls.client import RecallClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

# A Pydantic AI model or a LangChain model, depending on AGENT_BACKEND.
ChatModel = Model | LangChainChatModel


def get_agent_backend(
    body: ChatRequest, settings: Annotated[Settings, Depends(get_settings)]
) -> AgentBackend:
    if body.backend and settings.allow_backend_selection:
        return body.backend
    return settings.agent_backend


def get_chat_model(
    settings: Annotated[Settings, Depends(get_settings)],
    backend: Annotated[AgentBackend | None, Depends(get_agent_backend)] = None,
) -> ChatModel:
    api_key = settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else ""
    if not api_key:
        raise HTTPException(status_code=503, detail="Chat is not configured")
    names = dict.fromkeys([settings.gemini_model, *settings.gemini_fallback_models])
    if (backend or settings.agent_backend) == "langchain":
        return gemini_chat_model(list(names), api_key, settings.gemini_retry_attempts)
    retry = HttpRetryOptions(
        attempts=max(settings.gemini_retry_attempts, 1), initial_delay=1.0, max_delay=4.0
    )
    provider = GoogleProvider(api_key=api_key, retry_options=retry)
    models = [GoogleModel(name, provider=provider) for name in names]
    return models[0] if len(models) == 1 else FallbackModel(*models)


def get_recall_client(
    request: Request, settings: Annotated[Settings, Depends(get_settings)]
) -> RecallClient:
    http: httpx.AsyncClient = request.app.state.http_client
    return RecallClient(http, settings)


def to_model_history(messages: list[ChatMessage]) -> list[ModelMessage]:
    history: list[ModelMessage] = []
    for message in messages:
        if message.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=message.content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=message.content)]))
    return history


async def run_pydantic_ai_agent(
    model: Model, messages: list[ChatMessage], deps: ChatDeps
) -> ChatAnswer:
    result = await recall_agent.run(
        messages[-1].content,
        message_history=to_model_history(messages[:-1]),
        model=model,
        deps=deps,
        usage_limits=USAGE_LIMITS,
    )
    return result.output


@router.get("/chat/config", response_model=ChatConfig)
async def chat_config(settings: Annotated[Settings, Depends(get_settings)]) -> ChatConfig:
    return ChatConfig(
        default_backend=settings.agent_backend,
        backend_selection=settings.allow_backend_selection,
        voice_input=bool(settings.stt_url),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    model: Annotated[ChatModel, Depends(get_chat_model)],
    recalls: Annotated[RecallClient, Depends(get_recall_client)],
) -> ChatResponse:
    backend: AgentBackend = "langchain" if isinstance(model, LangChainChatModel) else "pydantic_ai"
    try:
        if isinstance(model, LangChainChatModel):
            deps: ChatDeps = LangChainDeps(recalls=recalls)
            output = await run_langchain_agent(model, body.messages, deps)
        else:
            deps = ChatDeps(recalls=recalls)
            output = await run_pydantic_ai_agent(model, body.messages, deps)
    except (ModelAPIError, AgentRunError, FallbackExceptionGroup, *LANGCHAIN_RUN_ERRORS) as exc:
        logger.exception("Chat run failed")
        raise HTTPException(status_code=502, detail="The assistant could not answer") from exc

    # Both agents' grounding checks guarantee every cited recall was retrieved during this run.
    sources = [deps.sources[recall_id] for recall_id in output.cited_recall_ids]
    return ChatResponse(answer=output.answer, sources=sources, backend=backend)
