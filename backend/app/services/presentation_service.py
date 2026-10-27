"""Business logic for creating, generating, editing and deleting presentations."""
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol
from threading import Event
from sqlalchemy.orm import Session
from app.agents.slide_content_agent import generate_presentation_content
from app.artifacts import manager as artifacts
from app.core.config import settings
from app.core.exceptions import ConflictError, InvalidFileError, NotFoundError
from app.database import database
from app.database.models import Document, Notebook, Presentation, PresentationStatus
from app.jobs.manager import job_manager
from app.llm.base import LlmClient
from app.llm.errors import LlmUnavailableError
from app.llm.ollama_client import OllamaJSONClient
from app.presentations.outline import generate_outline
from app.schemas.presentations import PresentationCreate
from app.schemas.slide_content import PresentationContent
from app.services import presentation_context
from app.tools.chart_tool import sources_from_documents
from app.tools.pptx_tool import build_pptx
from app.llm.cancellation import raise_if_cancelled

log = logging.getLogger(__name__)

class DeckGenerator(Protocol):
    def generate(
        self,
        *,
        notebook: Notebook,
        options: dict,
        documents: list[Document],
        progress: Callable[[str], None],
        cancel_event: Event | None = None,
    ) -> PresentationContent: ...

class LocalLlmDeckGenerator:
    """Generate an outline followed by its slide content."""

    def __init__(self, client: LlmClient | None = None, check_ready: bool = True):
        self.client: LlmClient = (
            client if client is not None
            else OllamaJSONClient(model_name=settings.presentation_model)
        )
        self.check_ready = check_ready

    def generate(
        self, *, notebook, options, documents, progress,
        cancel_event: Event | None = None,
    ) -> PresentationContent:
        raise_if_cancelled(cancel_event)
        if self.check_ready:
            self.client.check_ready()

        progress("reading documents")
        chunks = presentation_context.build_chunks(documents)
        data_files = sources_from_documents(documents)

        progress("outline")
        outline = generate_outline(
            self.client,
            options,
            chunks,
            [d.filename for d in data_files],
            cancel_event=cancel_event,
        )
        total = len(outline.slides)
        progress(f"content 0/{total}")

        return generate_presentation_content(
            outline,
            chunks_for_slide=presentation_context.make_selector(chunks),
            data_files=data_files,
            style=options["style"],
            user_request=options["topic"],
            client=self.client,
            cancel_event=cancel_event,
            on_progress=lambda done, count: progress(f"content {done}/{count}"),
        )

def get_generator() -> DeckGenerator:
    """The composition point for presentation generation; tests replace this."""
    return LocalLlmDeckGenerator()

def _touch(db: Session, p: Presentation, **fields) -> None:
    for key, value in fields.items():
        setattr(p, key, value)
    p.updated_at = datetime.utcnow()
    db.commit()

def _selected_documents(
    db: Session, notebook: Notebook, ids: list[int] | None
) -> list[Document]:
    query = db.query(Document).filter(Document.notebook_id == notebook.id)
    if ids is None:
        return query.order_by(Document.id).all()
    found = query.filter(Document.id.in_(ids)).order_by(Document.id).all()
    if len(found) != len(set(ids)):
        raise InvalidFileError("Some document_ids do not exist in this notebook.")
    return found

def _render(p: Presentation, deck: PresentationContent) -> str:
    """Render the deck and return its relative artifact path."""
    options = p.options
    relative = artifacts.presentation_file(p.notebook_id, p.id)
    build_pptx(
        deck,
        artifacts.resolve(relative),
        theme=options.get("theme", "classic"),
        rtl={"auto": None, "ltr": False, "rtl": True}[options.get("direction", "auto")],
        include_sources_slide=options.get("include_sources_slide", True),
    )
    return relative

def create_presentation(
    db: Session, notebook: Notebook, data: PresentationCreate
) -> Presentation:
    if data.num_slides > settings.max_presentation_slides:
        raise InvalidFileError(
            f"num_slides cannot be more than {settings.max_presentation_slides}."
        )
    _selected_documents(db, notebook, data.document_ids)
    p = Presentation(
        notebook_id=notebook.id,
        title=data.title or data.topic[:150],
        status=PresentationStatus.PENDING,
        stage="queued",
        options=data.model_dump(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    job_manager.submit(run_generation, p.id)
    db.refresh(p)
    return p

def run_generation(presentation_id: int) -> None:
    """Generate and render a presentation in a background worker."""
    db = database.SessionLocal()
    try:
        p = db.get(Presentation, presentation_id)
        if p is None or p.status != PresentationStatus.PENDING:
            return
        _touch(db, p, status=PresentationStatus.RUNNING, stage="starting")
        documents = _selected_documents(db, p.notebook, p.options.get("document_ids"))
        deck = get_generator().generate(
            notebook=p.notebook,
            options=p.options,
            documents=documents,
            progress=lambda stage: _touch(db, p, stage=stage),
        )
        _touch(db, p, stage="rendering", deck=deck.model_dump(mode="json"))
        relative = _render(p, deck)
        _touch(
            db, p,
            status=PresentationStatus.COMPLETED,
            stage="done",
            file_path=relative,
            error=None,
        )
    except Exception as exc:
        log.exception("Presentation %s failed", presentation_id)
        db.rollback()
        p = db.get(Presentation, presentation_id)
        if p is not None:
            message = str(exc) if isinstance(exc, LlmUnavailableError) else f"{type(exc).__name__}: {exc}"
            _touch(db, p, status=PresentationStatus.FAILED, error=message[:500])
    finally:
        db.close()

def update_deck(db: Session, p: Presentation, deck: PresentationContent) -> Presentation:
    """Render edited slide JSON without making model calls."""
    if p.status in (PresentationStatus.PENDING, PresentationStatus.RUNNING):
        raise ConflictError("The presentation is still being generated.")
    try:
        relative = _render(p, deck)
    except Exception as exc:
        raise InvalidFileError(f"The deck could not be drawn: {exc}")
    _touch(
        db, p,
        deck=deck.model_dump(mode="json"),
        file_path=relative,
        status=PresentationStatus.COMPLETED,
        stage="done",
        error=None,
    )
    db.refresh(p)
    return p

def get_deck(p: Presentation) -> PresentationContent:
    if not p.deck:
        raise ConflictError("The presentation has no slides yet.")
    return PresentationContent.model_validate(p.deck)

def get_download(p: Presentation) -> Path:
    if p.status != PresentationStatus.COMPLETED or not p.file_path:
        raise ConflictError("The presentation is not ready yet.")
    path = artifacts.resolve(p.file_path)
    if not path.is_file():
        raise NotFoundError("The presentation file is missing on the server.")
    return path

def list_presentations(db: Session, notebook: Notebook) -> list[Presentation]:
    return (
        db.query(Presentation)
        .filter(Presentation.notebook_id == notebook.id)
        .order_by(Presentation.id.desc())
        .all()
    )

def delete_presentation(db: Session, p: Presentation) -> None:
    if p.file_path:
        artifacts.delete(p.file_path)
    db.delete(p)
    db.commit()

def fail_interrupted_jobs() -> int:
    """Mark presentation jobs interrupted by a server restart as failed."""
    db = database.SessionLocal()
    try:
        stuck = (
            db.query(Presentation)
            .filter(Presentation.status.in_([PresentationStatus.PENDING, PresentationStatus.RUNNING]))
            .all()
        )
        for p in stuck:
            _touch(
                db, p,
                status=PresentationStatus.FAILED,
                error="Interrupted by a server restart.",
            )
        return len(stuck)
    finally:
        db.close()
