"""Task 4: conversations and persistent user messages."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_conversation
from app.database.database import get_db
from app.database.models import Conversation, User
from app.schemas.chat import (
    ConversationCreate,
    ConversationHistory,
    ConversationResponse,
    ConversationUpdate,
    MessageCreate,
    MessageResponse,
)
from app.services import chat_service

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = chat_service.create_conversation(
        db, current_user, data.notebook_id, data.title
    )
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found")
    return conversation


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    notebook_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return chat_service.list_conversations(db, current_user, notebook_id, limit, offset)


@router.get("/{conversation_id}", response_model=ConversationHistory)
def get_conversation_history(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conversation: Conversation = Depends(get_owned_conversation),
    db: Session = Depends(get_db),
):
    return ConversationHistory(
        conversation=conversation,
        messages=chat_service.get_history(db, conversation, limit, offset),
    )


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    data: ConversationUpdate,
    conversation: Conversation = Depends(get_owned_conversation),
    db: Session = Depends(get_db),
):
    return chat_service.update_conversation(db, conversation, data.title)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation: Conversation = Depends(get_owned_conversation),
    db: Session = Depends(get_db),
):
    chat_service.delete_conversation(db, conversation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_message(
    data: MessageCreate,
    conversation: Conversation = Depends(get_owned_conversation),
    db: Session = Depends(get_db),
):
    return chat_service.add_message(db, conversation, data.content)


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def get_messages(
    response: Response,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conversation: Conversation = Depends(get_owned_conversation),
    db: Session = Depends(get_db),
):
    response.headers["X-Total-Count"] = str(chat_service.count_messages(db, conversation))
    return chat_service.get_history(db, conversation, limit, offset)