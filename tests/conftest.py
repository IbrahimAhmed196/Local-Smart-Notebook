import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
 
from app.core.config import settings
from app.database import database as database_module
from app.database.database import Base, get_db
from app.jobs.manager import job_manager
from app.main import app
from app.presentations import generator as deck_generation
 
 
@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Uploads go to a temp folder (never your real data/ folder); size limit = 1 MB."""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "max_upload_mb", 1)
 
 
@pytest.fixture(autouse=True)
def inline_jobs(monkeypatch):
    """Background jobs run immediately in the test thread (no waiting, no threads)."""
    monkeypatch.setattr(job_manager, "inline", True)
 
 
@pytest.fixture()
def db(monkeypatch):
    """A fresh in-memory database for every test (your real .db file is untouched)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    # background jobs open their own session: point it at the same in-memory database
    monkeypatch.setattr(database_module, "SessionLocal", maker)
    session = maker()
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

@pytest.fixture()
def sample_deck():
    """Load the existing sample containing all five public layouts."""
    from pathlib import Path

    from app.schemas.slide_content import PresentationContent

    path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "samples"
        / "sample_deck.json"
    )
    return PresentationContent.model_validate_json(
        path.read_text(encoding="utf-8")
    )


@pytest.fixture()
def fake_generator(monkeypatch, sample_deck):
    """Replace generation stages while keeping the real runner and renderer."""
    from app.presentations.interfaces import GenerationSources
    from app.schemas.slides import PresentationOutlineResponse, SlideOutlineItem

    class FakeDeckGenerator:
        def __init__(self):
            self.calls = []
            self.stages = []
            self.error = None
            self.error_stage = "outline"

        def _enter(self, stage):
            self.stages.append(stage)
            if self.error is not None and self.error_stage == stage:
                raise self.error

        def prepare(self, *, notebook, options, documents, cancel_event=None):
            self.calls.append({
                "notebook_id": notebook.id,
                "options": options,
                "document_ids": [document.id for document in documents],
            })
            self._enter("prepare")

        def read_context(self, documents, *, cancel_event=None):
            self._enter("read_context")
            return GenerationSources(chunks=[], data_files=[])

        def outline(self, options, sources, *, cancel_event=None):
            self._enter("outline")
            return PresentationOutlineResponse(
                presentation_title=sample_deck.presentation_title,
                target_audience=sample_deck.target_audience,
                slides=[
                    SlideOutlineItem(
                        slide_number=i,
                        title=slide.title,
                        purpose="Test slide",
                        layout_type=slide.layout_type,
                    )
                    for i, slide in enumerate(sample_deck.slides, start=1)
                ],
            )

        def write_slides(
            self, options, sources, outline, *, progress, cancel_event=None
        ):
            self._enter("write_slides")
            count = len(sample_deck.slides)
            progress(f"content {count}/{count}")
            return sample_deck.model_copy(deep=True)

        def generate(
            self, *, notebook, options, documents, progress, cancel_event=None
        ):
            self.prepare(
                notebook=notebook, options=options, documents=documents,
                cancel_event=cancel_event,
            )
            progress("reading documents")
            sources = self.read_context(documents, cancel_event=cancel_event)
            progress("outline")
            outline = self.outline(options, sources, cancel_event=cancel_event)
            progress(f"content 0/{len(outline.slides)}")
            return self.write_slides(
                options, sources, outline,
                progress=progress, cancel_event=cancel_event,
            )

    generator = FakeDeckGenerator()
    monkeypatch.setattr(deck_generation, "get_generator", lambda: generator)
    return generator

@pytest.fixture()
def scripted_llm():
    """Factory for scripted clients, with call-count checks at teardown."""
    from tests.fake_llm import ScriptedLLMClient

    clients = []

    def make(*responses):
        client = ScriptedLLMClient(*responses)
        clients.append(client)
        return client

    yield make

    for client in clients:
        client.assert_finished()