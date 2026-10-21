from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.database.database import get_db
from app.database.models import Conversation, Document, Notebook, User, Presentation
from app.database.repositories import user_repo

# Must match the real login path; it follows API_PREFIX from the settings
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_prefix}/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    """Authentication: who is calling? Raises 401 if the token is missing/invalid."""
    user_id = decode_access_token(token)
    user = user_repo.get(db, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


# ---- Authorization: may this user touch this object? -----------------------
# We answer 404 (not 403) so nobody can probe which ids exist.

def get_owned_notebook(
    notebook_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Notebook:
    notebook = db.get(Notebook, notebook_id)
    if notebook is None or notebook.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notebook not found")
    return notebook


def get_owned_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Document:
    document = db.get(Document, document_id)
    if document is None or document.notebook.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return document


def get_owned_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.notebook.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversation

def get_owned_presentation(
    presentation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Presentation:
    presentation = db.get(Presentation, presentation_id)
    if presentation is None or presentation.notebook.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Presentation not found")
    return presentation

