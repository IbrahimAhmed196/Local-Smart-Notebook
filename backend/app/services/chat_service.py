from sqlalchemy.orm import Session

from app.database.models import Conversation, Message, MessageSender, Notebook, User
from app.database.repositories import chat_repo


def create_conversation(
    db: Session, user: User, notebook_id: int, title: str
) -> Conversation | None:
    notebook = (
        db.query(Notebook)
        .filter(Notebook.id == notebook_id, Notebook.user_id == user.id)
        .first()
    )
    if notebook is None:
        return None
    return chat_repo.create_conversation(db, notebook_id=notebook.id, title=title.strip())


def list_conversations(
    db: Session, user: User, notebook_id: int | None = None, limit: int = 50, offset: int = 0
) -> list[Conversation]:
    return chat_repo.list_for_owner(
        db, owner_id=user.id, notebook_id=notebook_id, limit=limit, offset=offset
    )


def add_message(db: Session, conversation: Conversation, content: str) -> Message:
    content = content.strip()
    message = chat_repo.add_message(
        db, conversation_id=conversation.id, sender=MessageSender.USER, content=content
    )
    if conversation.title.strip().lower() in {"new conversation", ""}:
        conversation.title = " ".join(content.split())[:50]
        db.commit()
        db.refresh(conversation)
    return message


def get_history(
    db: Session, conversation: Conversation, limit: int = 100, offset: int = 0
) -> list[Message]:
    return chat_repo.list_messages(
        db, conversation_id=conversation.id, limit=limit, offset=offset
    )


def count_messages(db: Session, conversation: Conversation) -> int:
    return chat_repo.count_messages(db, conversation_id=conversation.id)


def update_conversation(db: Session, conversation: Conversation, title: str) -> Conversation:
    return chat_repo.update_conversation(db, conversation, title=title.strip())


def delete_conversation(db: Session, conversation: Conversation) -> None:
    chat_repo.delete_conversation(db, conversation)
