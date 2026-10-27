"""Notebook-scoped document selection shared by presentation use cases and jobs."""
from sqlalchemy.orm import Session
from app.core.exceptions import InvalidFileError
from app.database.models import Document, Notebook


def selected_documents(
    db: Session, notebook: Notebook, ids: list[int] | None
) -> list[Document]:
    query = db.query(Document).filter(Document.notebook_id == notebook.id)
    if ids is None:
        return query.order_by(Document.id).all()
    found = query.filter(Document.id.in_(ids)).order_by(Document.id).all()
    if len(found) != len(set(ids)):
        raise InvalidFileError("Some document_ids do not exist in this notebook.")
    return found