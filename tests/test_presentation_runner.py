from unittest.mock import Mock
import pytest
from app.database import database
from app.database.models import Presentation, PresentationStatus
from app.presentations import runner
from app.schemas.presentations import PresentationCreate


@pytest.fixture
def pending(db, notebook_id):
    p = Presentation(
        notebook_id=notebook_id,
        title="Runner test",
        status=PresentationStatus.PENDING,
        stage="queued",
        options=PresentationCreate(topic="Sales", num_slides=6).model_dump(),
    )
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def worker_sessions(db, monkeypatch):
    factory = database.SessionLocal
    sessions = []

    def create():
        session = factory()
        session.close = Mock(wraps=session.close)
        sessions.append(session)
        return session

    monkeypatch.setattr(database, "SessionLocal", create)
    return sessions


@pytest.mark.parametrize("step,stage", [
    ("prepare", "starting"),
    ("read_context", "reading documents"),
    ("outline", "outline"),
    ("write_slides", "content 0/5"),
    ("render", "rendering"),
])
def test_failure_stops_later_steps_and_closes_session(
    db, pending, fake_generator, monkeypatch, worker_sessions, step, stage,
):
    render = Mock(return_value="unused.pptx")
    monkeypatch.setattr(runner, "render_deck", render)
    if step == "render":
        render.side_effect = RuntimeError("Broken stage")
    else:
        fake_generator.error_stage = step
        fake_generator.error = RuntimeError("Broken stage")

    runner.run_generation(pending.id)
    db.refresh(pending)

    assert pending.status == PresentationStatus.FAILED
    assert pending.stage == stage
    assert pending.error == "RuntimeError: Broken stage"
    assert pending.file_path is None
    assert (pending.deck is not None) == (step == "render")

    stages = ["prepare", "read_context", "outline", "write_slides"]
    expected = stages if step == "render" else stages[:stages.index(step) + 1]
    assert fake_generator.stages == expected
    assert render.call_count == int(step == "render")
    worker_sessions[0].close.assert_called_once_with()


def test_success_runs_in_order_and_duplicate_execution_is_skipped(
    db, pending, fake_generator, worker_sessions,
):
    runner.run_generation(pending.id)
    db.refresh(pending)

    assert pending.status == PresentationStatus.COMPLETED
    assert pending.stage == "done" and pending.error is None
    assert fake_generator.stages == [
        "prepare", "read_context", "outline", "write_slides"
    ]

    runner.run_generation(pending.id)
    assert len(fake_generator.calls) == 1
    assert len(worker_sessions) == 2
    for session in worker_sessions:
        session.close.assert_called_once_with()


def test_missing_job_is_skipped(fake_generator, worker_sessions):
    runner.run_generation(-1)
    assert fake_generator.calls == []
    worker_sessions[0].close.assert_called_once_with()