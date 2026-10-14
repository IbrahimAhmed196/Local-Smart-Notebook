from sqlalchemy.orm import Session

from app.database.models import Notebook


def list_for_owner(db: Session, owner_id: int) -> list[Notebook]:
    return db.query(Notebook).filter(Notebook.user_id == owner_id).all()


def create(db: Session, *, owner_id: int, title: str, description: str | None) -> Notebook:
    notebook = Notebook(title=title, description=description, user_id=owner_id)
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    return notebook


def update(db: Session, notebook: Notebook, **fields) -> Notebook:
    for key, value in fields.items():
        setattr(notebook, key, value)
    db.commit()
    db.refresh(notebook)
    return notebook


def delete(db: Session, notebook: Notebook) -> None:
    db.delete(notebook)  # the ORM cascade removes documents, conversations, messages
    db.commit()
