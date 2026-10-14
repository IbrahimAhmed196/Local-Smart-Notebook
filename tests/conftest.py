import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database.database import Base, get_db
from app.main import app


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Uploads go to a temp folder (never your real data/ folder); size limit = 1 MB."""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "max_upload_mb", 1)


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
    # base_url carries API_PREFIX, so the tests can use short URLs like "/auth/me"
    yield TestClient(app, base_url=f"http://testserver{settings.api_prefix}")
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


@pytest.fixture()
def auth(login):
    """Auth headers of a default test user."""
    return login()


@pytest.fixture()
def make_notebook(client):
    """make_notebook(headers) creates a notebook for that user and returns its id."""

    def _make(headers, title="Test notebook"):
        r = client.post("/notebooks/", json={"title": title}, headers=headers)
        return r.json()["id"]

    return _make


@pytest.fixture()
def notebook_id(make_notebook, auth):
    return make_notebook(auth)
