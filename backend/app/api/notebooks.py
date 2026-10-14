from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_owned_notebook
from app.database.database import get_db
from app.database.models import Notebook, User
from app.schemas.notebook_schema import NotebookCreate, NotebookResponse

router = APIRouter(prefix="/notebooks", tags=["Notebooks"])


# 1. CREATE: the notebook belongs to whoever is logged in
@router.post(
    "/", response_model=NotebookResponse, status_code=status.HTTP_201_CREATED
)
def create_notebook(
    notebook: NotebookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_notebook = Notebook(
        title=notebook.title,
        description=notebook.description,
        user_id=current_user.id,
    )
    db.add(db_notebook)
    db.commit()
    db.refresh(db_notebook)
    return db_notebook


# 2. READ: only MY notebooks
@router.get("/", response_model=List[NotebookResponse])
def get_notebooks(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return db.query(Notebook).filter(Notebook.user_id == current_user.id).all()


# 3. UPDATE: get_owned_notebook returns 404 if it is not mine
@router.put("/{notebook_id}", response_model=NotebookResponse)
def update_notebook(
    notebook_update: NotebookCreate,
    db: Session = Depends(get_db),
    db_notebook: Notebook = Depends(get_owned_notebook),
):
    db_notebook.title = notebook_update.title
    db_notebook.description = notebook_update.description
    db.commit()
    db.refresh(db_notebook)
    return db_notebook


# 4. DELETE: same ownership check
@router.delete("/{notebook_id}")
def delete_notebook(
    db: Session = Depends(get_db),
    db_notebook: Notebook = Depends(get_owned_notebook),
):
    db.delete(db_notebook)
    db.commit()
    return {"message": "Notebook deleted successfully"}
