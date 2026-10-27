"""Background presentation execution, progress persistence, and failure recovery."""
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import database
from app.database.models import Presentation, PresentationStatus
from app.presentations import generator as deck_generation
from app.presentations.rendering import render_deck
from app.presentations.repository import selected_documents

log = logging.getLogger(__name__)


def _touch(db: Session, p: Presentation, **fields) -> None:
    for key, value in fields.items():
        setattr(p, key, value)
    p.updated_at = datetime.utcnow()
    db.commit()


def _prepare(db, presentation_id):
    p = db.get(Presentation, presentation_id)
    if p is None or p.status != PresentationStatus.PENDING:
        return None

    _touch(db, p, status=PresentationStatus.RUNNING, stage="starting")
    documents = selected_documents(db, p.notebook, p.options.get("document_ids"))
    generator = deck_generation.get_generator()
    generator.prepare(
        notebook=p.notebook, options=p.options, documents=documents
    )
    return p, documents, generator


def _read_context(db, p, generator, documents):
    _touch(db, p, stage="reading documents")
    return generator.read_context(documents)


def _outline(db, p, generator, sources):
    _touch(db, p, stage="outline")
    return generator.outline(p.options, sources)


def _write_slides(db, p, generator, sources, outline):
    _touch(db, p, stage=f"content 0/{len(outline.slides)}")
    return generator.write_slides(
        p.options,
        sources,
        outline,
        progress=lambda stage: _touch(db, p, stage=stage),
    )


def _render(db, p, deck):
    _touch(db, p, stage="rendering", deck=deck.model_dump(mode="json"))
    return render_deck(p, deck)


def _finish(db, p, relative):
    _touch(
        db, p,
        status=PresentationStatus.COMPLETED,
        stage="done",
        file_path=relative,
        error=None,
    )


def _fail(db, presentation_id, exc):
    db.rollback()
    p = db.get(Presentation, presentation_id)
    if p is not None:
        message = deck_generation.generation_error_message(exc)
        _touch(db, p, status=PresentationStatus.FAILED, error=message[:500])


def run_generation(presentation_id: int) -> None:
    """Execute the stages using a dedicated worker-owned database session."""
    db = database.SessionLocal()
    try:
        prepared = _prepare(db, presentation_id)
        if prepared is None:
            return

        p, documents, generator = prepared
        sources = _read_context(db, p, generator, documents)
        outline = _outline(db, p, generator, sources)
        deck = _write_slides(db, p, generator, sources, outline)
        relative = _render(db, p, deck)
        _finish(db, p, relative)
    except Exception as exc:
        log.exception("Presentation %s failed", presentation_id)
        _fail(db, presentation_id, exc)
    finally:
        db.close()


def fail_interrupted_jobs() -> int:
    """Preserve the existing restart policy until the job-status tasks replace it."""
    db = database.SessionLocal()
    try:
        stuck = db.query(Presentation).filter(
            Presentation.status.in_([
                PresentationStatus.PENDING,
                PresentationStatus.RUNNING,
            ])
        ).all()
        for p in stuck:
            _touch(
                db, p,
                status=PresentationStatus.FAILED,
                error="Interrupted by a server restart.",
            )
        return len(stuck)
    finally:
        db.close()