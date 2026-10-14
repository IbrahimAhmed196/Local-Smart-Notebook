from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Document, Notebook

SORTABLE = {
    "uploaded_at": Document.uploaded_at,
    "filename": Document.filename,
    "file_size": Document.file_size,
    "file_type": Document.file_type,
}


def add(db: Session, doc: Document) -> Document:
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get(db: Session, document_id: int) -> Document | None:
    return db.get(Document, document_id)


def get_by_hash(db: Session, notebook_id: int, sha256: str) -> Document | None:
    return db.scalar(
        select(Document).where(Document.notebook_id == notebook_id, Document.sha256 == sha256)
    )


def list_documents(
    db: Session, *, owner_id=None, notebook_id=None, file_type=None, status=None,
    search=None, sort_by="uploaded_at", order="desc", limit=50, offset=0,
) -> tuple[list[Document], int]:
    stmt = select(Document)
    if owner_id is not None:  # only documents inside notebooks owned by this user
        stmt = stmt.join(Notebook, Notebook.id == Document.notebook_id).where(
            Notebook.user_id == owner_id
        )
    if notebook_id is not None:
        stmt = stmt.where(Document.notebook_id == notebook_id)
    if file_type:
        stmt = stmt.where(Document.file_type == file_type.lower().lstrip("."))
    if status:
        stmt = stmt.where(Document.status == status.upper())
    if search:
        stmt = stmt.where(Document.filename.ilike(f"%{search}%"))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = SORTABLE.get(sort_by, Document.uploaded_at)
    stmt = stmt.order_by(col.asc() if order == "asc" else col.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt)), total


def delete(db: Session, doc: Document) -> None:
    db.delete(doc)
    db.commit()
