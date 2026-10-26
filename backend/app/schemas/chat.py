"""Pydantic schemas for conversations and messages (Task 4)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    notebook_id: int
    title: str = Field(default="New chat", min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title must not be blank.")
        return v


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Title must not be blank.")
        return v


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    notebook_id: int
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=10000)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message must not be empty.")
        return v


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    sender: str
    content: str
    timestamp: datetime


class ConversationHistory(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]


class AskResponse(BaseModel):
    """Result of asking the AI a question in a conversation.

    `assistant_message` is None when the model could not answer; `error` then says why.
    The user's message is stored in both cases."""

    user_message: MessageResponse
    assistant_message: MessageResponse | None = None
    error: str | None = None
    sources: list[str] = Field(default_factory=list)  # files the answer was based on
