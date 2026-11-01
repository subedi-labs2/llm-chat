from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.recalls.schemas import Agency


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)

    @field_validator("messages")
    @classmethod
    def last_message_is_from_user(cls, messages: list[ChatMessage]) -> list[ChatMessage]:
        if messages[-1].role != "user":
            raise ValueError("The last message must be from the user")
        return messages


class Source(BaseModel):
    id: str
    agency: Agency
    title: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]
