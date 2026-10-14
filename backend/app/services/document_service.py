"""Document management: upload, list, download, update, delete."""
import logging
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, InvalidFileError, NotFoundError
from app.core.security import sanitize_filename
from app.database.models import Document, DocumentStatus, Notebook, User
from app.database.repositories import document_repo as repo
from app.ingestion import pipeline
from app.services.file_validation import MIME_TYPES, get_extension, validate_content
from app.services import file_storage

log = logging.getLogger(__name__)


def get_owned_notebook_or_404(db: Session, notebook_id: int, user: User) -> Notebook:
    """The notebook must exist AND belong to `user`. Both cases answer 404, so nobody
    can find out which notebook ids exist."""
    notebook = db.get(Notebook, notebook_id)
    if notebook is None or notebook.user_id != user.id:
        raise NotFoundError("Notebook not found.")
    return notebook


def upload_document(
    db: Session,
    user: User,
    notebook_id: int,
    upload: UploadFile,
    description: str | None = None,
) -> Document:
    get_owned_notebook_or_404(db, notebook_id, user)

    filename = sanitize_filename(upload.filename or "")
    ext = get_extension(filename)                                   # 415

    tmp, size, digest = file_storage.save_temp(upload.file, settings.max_upload_bytes)  # 413
    try:
        if size == 0:
            raise InvalidFileError("The uploaded file is empty.")
        validate_content(tmp, ext)                                  # 400
        existing = repo.get_by_hash(db, notebook_id, digest)
        if existing:
            raise ConflictError(
                f"This file already exists in the notebook as '{existing.filename}' "
                f"(document id {existing.id})."
            )
        relative = file_storage.commit(tmp, notebook_id, ext)
    except Exception:
        file_storage.discard(tmp)
        raise

    doc = Document(
        filename=filename,
        file_path=relative,
        file_type=ext.lstrip("."),
        notebook_id=notebook_id,
        file_size=size,
        mime_type=MIME_TYPES[ext],
        sha256=digest,
        description=description,
        status=DocumentStatus.UPLOADED,
    )
    try:
        repo.add(db, doc)
    except Exception:
        db.rollback()
        file_storage.delete(relative)       # never leave an orphan file behind
        raise

    pipeline.on_document_uploaded(doc)
    return doc


def list_documents(db: Session, user: User, **filters) -> tuple[list[Document], int]:
    """Only the user's own documents: one notebook (checked) or all of their notebooks."""
    if filters.get("notebook_id") is not None:
        get_owned_notebook_or_404(db, filters["notebook_id"], user)
    return repo.list_documents(db, owner_id=user.id, **filters)


def get_file_path(doc: Document) -> Path:
    path = file_storage.resolve(doc.file_path)
    if not path.is_file():
        log.error("File missing on disk for document %s (%s)", doc.id, path)
        raise NotFoundError("The stored file for this document is missing on disk.")
    return path


def update_document(
    db: Session, doc: Document, filename: str | None, description, fields: set
) -> Document:
    """`doc` comes from the get_owned_document dependency (already ownership-checked)."""
    if filename:
        new_name = sanitize_filename(filename)
        if get_extension(new_name).lstrip(".") != doc.file_type:
            raise InvalidFileError(f"The file extension must remain '.{doc.file_type}'.")
        doc.filename = new_name
    if "description" in fields:
        doc.description = description
    db.commit()
    db.refresh(doc)
    return doc


def delete_document(db: Session, doc: Document) -> None:
    path = doc.file_path
    repo.delete(db, doc)
    file_storage.delete(path)
    pipeline.on_document_deleted(doc)


def purge_notebook_files(notebook_id: int) -> None:
    """Call this AFTER deleting a notebook. Your Notebook -> Document cascade
    removes the DB rows; this removes the files on disk."""
    file_storage.delete_notebook_dir(notebook_id)
