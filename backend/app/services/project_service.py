"""Business rules for projects. The design calls a project what the team calls a
"notebook": the model is `Notebook` and the URLs are /notebooks."""
from sqlalchemy.orm import Session

from app.database.models import Notebook, User
from app.database.repositories import project_repo
from app.schemas.projects import NotebookCreate
from app.services import document_service
from app.artifacts import manager as artifacts 


def create_notebook(db: Session, user: User, data: NotebookCreate) -> Notebook:
    return project_repo.create(
        db, owner_id=user.id, title=data.title, description=data.description
    )


def list_notebooks(db: Session, user: User) -> list[Notebook]:
    return project_repo.list_for_owner(db, user.id)


def update_notebook(db: Session, notebook: Notebook, data: NotebookCreate) -> Notebook:
    return project_repo.update(
        db, notebook, title=data.title, description=data.description
    )


def delete_notebook(db: Session, notebook: Notebook) -> None:
    notebook_id = notebook.id  # read it before the row is gone
    project_repo.delete(db, notebook)  # database rows ...
    document_service.purge_notebook_files(notebook_id)  # ... and the files on disk
    artifacts.purge_notebook_artifacts(notebook_id) 
