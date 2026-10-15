"""Business logic for conversations and messages (Task 4).

Only the user's own messages are stored for now: there is no LLM yet, so nothing
answers them. When Stage 2 adds the AI answer, call `add_message` with sender="assistant".
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Conversation, Message, Notebook, User

USER_SENDER = "user"


def create_conversation(
    db: Session, user: User, notebook_id: int, title: str
) -> Conversation | None:
    """None if the notebook does not exist or is not the user's (the router answers 404)."""
    notebook = db.get(Notebook, notebook_id)
    if notebook is None or notebook.user_id != user.id:
        return None
    conversation = Conversation(title=title, notebook_id=notebook_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_conversations(
    db: Session, user: User, notebook_id: int | None, limit: int, offset: int
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .join(Notebook, Notebook.id == Conversation.notebook_id)
        .where(Notebook.user_id == user.id)
    )
    if notebook_id is not None:
        stmt = stmt.where(Conversation.notebook_id == notebook_id)
    stmt = (
        stmt.order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def get_history(
    db: Session, conversation: Conversation, limit: int, offset: int
) -> list[Message]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.timestamp.asc(), Message.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def count_messages(db: Session, conversation: Conversation) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation.id)
        )
        or 0
    )


def update_conversation(db: Session, conversation: Conversation, title: str) -> Conversation:
    conversation.title = title
    db.commit()
    db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, conversation: Conversation) -> None:
    db.delete(conversation)  # its messages go with it (cascade)
    db.commit()


def add_message(
    db: Session, conversation: Conversation, content: str, sender: str = USER_SENDER
) -> Message:
    message = Message(conversation_id=conversation.id, sender=sender, content=content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
