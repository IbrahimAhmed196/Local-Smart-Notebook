from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Conversation, Message, Notebook


def create_conversation(db: Session, *, notebook_id: int, title: str) -> Conversation:
    conversation = Conversation(title=title, notebook_id=notebook_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def list_for_owner(
    db: Session, *, owner_id: int, notebook_id: int | None = None, limit: int = 50, offset: int = 0
) -> list[Conversation]:
    statement = (
        select(Conversation)
        .join(Notebook, Notebook.id == Conversation.notebook_id)
        .where(Notebook.user_id == owner_id)
    )
    if notebook_id is not None:
        statement = statement.where(Notebook.id == notebook_id)
    statement = (
        statement.order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(statement))


def add_message(db: Session, *, conversation_id: int, sender: str, content: str) -> Message:
    message = Message(conversation_id=conversation_id, sender=sender, content=content)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def count_messages(db: Session, *, conversation_id: int) -> int:
    statement = select(func.count()).select_from(Message).where(
        Message.conversation_id == conversation_id
    )
    return db.scalar(statement) or 0


def list_messages(
    db: Session, *, conversation_id: int, limit: int = 100, offset: int = 0
) -> list[Message]:
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.asc(), Message.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(statement))


def update_conversation(db: Session, conversation: Conversation, *, title: str) -> Conversation:
    conversation.title = title
    db.commit()
    db.refresh(conversation)
    return conversation


def delete_conversation(db: Session, conversation: Conversation) -> None:
    db.delete(conversation)
    db.commit()
