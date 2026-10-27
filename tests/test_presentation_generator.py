from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.core.exceptions import GenerationCancelled
from app.presentations import generator
from app.schemas.presentations import PresentationCreate
from tests.test_presentation_outline import outline_response


def test_pre_cancel_stops_before_readiness_or_documents(scripted_llm, monkeypatch):
    client = scripted_llm()
    read = Mock()
    monkeypatch.setattr(generator.presentation_context, "build_chunks", read)
    cancel = Event()
    cancel.set()

    with pytest.raises(GenerationCancelled):
        generator.LocalLlmDeckGenerator(client=client).generate(
            notebook=SimpleNamespace(id=1),
            options={},
            documents=(),
            progress=Mock(),
            cancel_event=cancel,
        )

    assert client.ready_checks == 0
    read.assert_not_called()


def test_same_cancel_event_reaches_outline_and_slides(scripted_llm):
    client = scripted_llm(
        outline_response(),
        {"subtitle": "Hello"},
        {"bullets": []},
    )
    cancel = Event()
    deck = generator.LocalLlmDeckGenerator(client=client).generate(
        notebook=SimpleNamespace(id=1),
        options=PresentationCreate(topic="Sales", num_slides=3).model_dump(),
        documents=(),
        progress=Mock(),
        cancel_event=cancel,
    )

    assert len(deck.slides) == 2
    assert len(client.calls) == 3
    assert all(call["cancel_event"] is cancel for call in client.calls)