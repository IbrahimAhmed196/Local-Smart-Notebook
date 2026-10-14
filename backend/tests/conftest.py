import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.database import Base, get_db
from app.main import app


@pytest.fixture()
def db():
    """A fresh in-memory database for every test (your real .db file is untouched)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def login(client):
    """login("a@x.com") registers the user (if new) and returns the auth headers."""

    def _login(email="ibrahim@example.com", password="secret123"):
        client.post("/auth/register", json={"email": email, "password": password})
        form = {"username": email, "password": password}
        token = client.post("/auth/login", data=form).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _login
