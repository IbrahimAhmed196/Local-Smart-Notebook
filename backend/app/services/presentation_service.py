"""Presentation CRUD/use cases; generation jobs are submitted to the runner."""
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from app.artifacts import manager as artifacts
from app.core.config import settings
from app.core.exceptions import ConflictError, InvalidFileError, NotFoundError
from app.database.models import Notebook, Presentation, PresentationStatus
from app.jobs.manager import job_manager
from app.presentations import runner
from app.presentations.rendering import render_deck
from app.presentations.repository import selected_documents
from app.schemas.presentations import PresentationCreate
from app.schemas.slide_content import PresentationContent


def create_presentation(
    db: Session, notebook: Notebook, data: PresentationCreate
) -> Presentation:
    if data.num_slides > settings.max_presentation_slides:
        raise InvalidFileError(
            f"num_slides cannot be more than {settings.max_presentation_slides}."
        )
    selected_documents(db, notebook, data.document_ids)
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
    job_manager.submit(runner.run_generation, p.id)
    db.refresh(p)
    return p


def update_deck(
    db: Session, p: Presentation, deck: PresentationContent
) -> Presentation:
    """Render a manually edited deck without calling the model."""
    if p.status in (PresentationStatus.PENDING, PresentationStatus.RUNNING):
        raise ConflictError("The presentation is still being generated.")
    try:
        relative = render_deck(p, deck)
    except Exception as exc:
        raise InvalidFileError(f"The deck could not be drawn: {exc}")

    p.deck = deck.model_dump(mode="json")
    p.file_path = relative
    p.status = PresentationStatus.COMPLETED
    p.stage = "done"
    p.error = None
    p.updated_at = datetime.utcnow()
    db.commit()
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