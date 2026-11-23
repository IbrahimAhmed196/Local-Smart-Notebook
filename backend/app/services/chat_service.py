"""Business logic for conversations and messages (Task 4) and the AI answer.

`add_message` only stores a message. `ask` stores the user's message, asks the Ollama
model (with the earlier messages of the chat and the text of the notebook's uploaded
files) and stores the answer as a message with sender="assistant".
"""
import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.models import Conversation, Message, Notebook, User
from app.llm.ollama_client import LlmChatError, OllamaChatClient
from app.services import document_context

log = logging.getLogger(__name__)

USER_SENDER = "user"
ASSISTANT_SENDER = "assistant"

SYSTEM_PROMPT = """You are the assistant of a personal notebook app. Answer the user's question helpfully and accurately.
- Reply in the same language as the user's last message.
- When DOCUMENT EXCERPTS are given, answer from them and say which file the information comes from, for example (report.pdf, page 3).
- If the excerpts do not contain the answer, say so plainly, then you may add what you know and mark it clearly as general knowledge.
- Never invent facts, numbers or quotes that are not in the excerpts.
- Use the earlier messages of the conversation to understand follow-up questions."""

NO_DOCUMENTS_NOTE = "The notebook has no readable uploaded documents, so answer from general knowledge."


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
    db: Session,
    conversation: Conversation,
    content: str,
    sender: str = USER_SENDER,
    feature: str = "chat",
    artifact_path: str | None = None,
    artifact_type: str | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        sender=sender,
        content=content,
        feature=feature,
        artifact_path=artifact_path,
        artifact_type=artifact_type,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


# ---- AI answer -------------------------------------------------------------------------

@dataclass
class Exchange:
    user_message: Message
    assistant_message: Message | None = None
    error: str | None = None
    sources: list[str] | None = None


def get_chat_client() -> OllamaChatClient:
    """One place that builds the client (tests replace this with a fake)."""
    return OllamaChatClient(
        model_name=settings.chat_model,
        base_url=settings.ollama_base_url,
        timeout=settings.chat_timeout_seconds,
    )


def _recent_history(db: Session, conversation: Conversation, before_id: int) -> list[dict]:
    """The last N messages of the chat that came before the new question."""
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id, Message.id < before_id)
            .order_by(Message.id.desc())
            .limit(settings.chat_history_messages)
        )
    )
    rows.reverse()
    return [
        {
            "role": "user" if m.sender == USER_SENDER else "assistant",
            "content": m.content,
        }
        for m in rows
    ]


def build_prompt(
    db: Session, conversation: Conversation, question: str, before_id: int
) -> tuple[list[dict], list[str]]:
    """The messages sent to the model, and the names of the files that were used."""
    context, sources = document_context.build_context(
        db, conversation.notebook_id, question, settings.chat_context_chars
    )
    system = SYSTEM_PROMPT + "\n\n" + (
        f"DOCUMENT EXCERPTS:\n{context}" if context else NO_DOCUMENTS_NOTE
    )
    messages = [{"role": "system", "content": system}]
    messages.extend(_recent_history(db, conversation, before_id))
    messages.append({"role": "user", "content": question})
    return messages, sources


def ask(
    db: Session,
    conversation: Conversation,
    content: str,
    feature: str = "chat",
) -> Exchange:
    """Store the question, get the model's answer, store that too.

    The question is saved even if the model is down: the caller then gets `error` and no
    assistant message, and the user can simply ask again.
    """
    user_message = add_message(db, conversation, content, USER_SENDER, feature=feature or "chat")

    if feature == "infographic":
        try:
            from app.infographic.pipeline import generate_infographic_plan
            from app.infographic.rendering import render_infographic
            from app.artifacts import manager

            report_text = content
            sources = []
            if len(content.strip()) < 100:
                context, doc_sources = document_context.build_context(
                    db, conversation.notebook_id, content, settings.chat_context_chars
                )
                if context:
                    report_text = context
                    sources = doc_sources

            plan = generate_infographic_plan(report_text)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        rendered = pool.submit(asyncio.run, render_infographic(plan, output_format="png", scale=2.0)).result()
                else:
                    rendered = loop.run_until_complete(render_infographic(plan, output_format="png", scale=2.0))
            except RuntimeError:
                rendered = asyncio.run(render_infographic(plan, output_format="png", scale=2.0))

            filename = f"infographic_{user_message.id}.png"
            rel_path = f"notebook_{conversation.notebook_id}/infographics/{filename}"
            abs_path = manager.resolve(rel_path)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_bytes(rendered.content)

            assistant_message = add_message(
                db,
                conversation,
                "Here is your generated infographic:",
                ASSISTANT_SENDER,
                feature="infographic",
                artifact_path=rel_path,
                artifact_type="image/png",
            )
            return Exchange(user_message, assistant_message, sources=sources)
        except Exception as exc:
            log.warning("Infographic generation failed: %s", exc)
            return Exchange(user_message, error=f"Infographic generation failed: {exc}")

    try:
        prompt, sources = build_prompt(db, conversation, content, user_message.id)
        answer = get_chat_client().chat(
            prompt,
            temperature=settings.chat_temperature,
            num_ctx=settings.chat_num_ctx,
        )
    except LlmChatError as exc:
        log.warning("Chat answer failed: %s", exc)
        return Exchange(user_message, error=str(exc))
    except Exception:
        log.exception("Unexpected error while answering a chat message")
        return Exchange(user_message, error="Something went wrong while preparing the answer.")

    assistant_message = add_message(db, conversation, answer, ASSISTANT_SENDER, feature="chat")
    return Exchange(user_message, assistant_message, sources=sources)
