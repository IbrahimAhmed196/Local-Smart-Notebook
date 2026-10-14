from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    hash_password,
    verify_password,
)
from app.database.models import User
from app.database.repositories import user_repo
from app.schemas.auth import UserCreate


def register(db: Session, data: UserCreate) -> User:
    if user_repo.get_by_email(db, data.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return user_repo.create(
        db, email=data.email, hashed_password=hash_password(data.password)
    )


def login(db: Session, email: str, password: str) -> str:
    user = user_repo.get_by_email(db, email)
    if user is None:
        verify_password(password, DUMMY_HASH)  # same timing if the user is unknown
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return create_access_token(user.id)
