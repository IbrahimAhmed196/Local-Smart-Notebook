from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings


class ConversationCreate(BaseModel):
    notebook_id: int
    title: str = Field(default="New conversation", min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip()


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title cannot be blank")
        return value.strip()


class ConversationResponse(BaseModel):
    id: int
    title: str
    notebook_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=settings.max_message_length)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message cannot be blank")
        return value.strip()


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True


class ConversationHistory(BaseModel):
    conversation: ConversationResponse
    messages: list[MessageResponse]
