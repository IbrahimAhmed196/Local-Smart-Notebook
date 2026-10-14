from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_notebook
from app.database.database import get_db
from app.database.models import Notebook, User
from app.schemas.common import MessageResponse
from app.schemas.projects import NotebookCreate, NotebookResponse
from app.services import project_service

# The design calls these "projects"; the team's name (and the URL) is "notebooks".
router = APIRouter(prefix="/notebooks", tags=["Notebooks"])


@router.post(
    "/", response_model=NotebookResponse, status_code=status.HTTP_201_CREATED
)
def create_notebook(
    notebook: NotebookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return project_service.create_notebook(db, current_user, notebook)


@router.get("/", response_model=list[NotebookResponse])
def get_notebooks(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return project_service.list_notebooks(db, current_user)


# get_owned_notebook answers 404 if the notebook is not the caller's
@router.put("/{notebook_id}", response_model=NotebookResponse)
def update_notebook(
    notebook_update: NotebookCreate,
    db: Session = Depends(get_db),
    db_notebook: Notebook = Depends(get_owned_notebook),
):
    return project_service.update_notebook(db, db_notebook, notebook_update)


@router.delete("/{notebook_id}", response_model=MessageResponse)
def delete_notebook(
    db: Session = Depends(get_db),
    db_notebook: Notebook = Depends(get_owned_notebook),
):
    project_service.delete_notebook(db, db_notebook)
    return MessageResponse(message="Notebook deleted successfully")
