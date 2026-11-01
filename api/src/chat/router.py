import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic_ai import (
    AgentRunError,
    ModelAPIError,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UsageLimits,
    UserPromptPart,
)
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from src.chat.agent import ChatDeps, recall_agent
from src.chat.schemas import ChatMessage, ChatRequest, ChatResponse
from src.core.config import Settings, get_settings
from src.recalls.client import RecallClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

USAGE_LIMITS = UsageLimits(request_limit=8, tool_calls_limit=6)


def get_chat_model(settings: Annotated[Settings, Depends(get_settings)]) -> Model:
    api_key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else ""
    if not api_key:
        raise HTTPException(status_code=503, detail="Chat is not configured")
    provider = OpenAIProvider(api_key=api_key)
    return OpenAIChatModel(settings.openai_model, provider=provider)


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


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    model: Annotated[Model, Depends(get_chat_model)],
    recalls: Annotated[RecallClient, Depends(get_recall_client)],
) -> ChatResponse:
    deps = ChatDeps(recalls=recalls)
    try:
        result = await recall_agent.run(
            body.messages[-1].content,
            message_history=to_model_history(body.messages[:-1]),
            model=model,
            deps=deps,
            usage_limits=USAGE_LIMITS,
        )
    except (ModelAPIError, AgentRunError) as exc:
        logger.exception("Chat run failed")
        raise HTTPException(status_code=502, detail="The assistant could not answer") from exc

    # Only cite recalls that were actually retrieved during this run.
    cited = dict.fromkeys(result.output.cited_recall_ids)
    sources = [deps.sources[recall_id] for recall_id in cited if recall_id in deps.sources]
    return ChatResponse(answer=result.output.answer, sources=sources)
