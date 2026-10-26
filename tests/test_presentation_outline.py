from types import SimpleNamespace

import pytest

from app.schemas.presentations import PresentationCreate
from app.schemas.slide_content import SlideContentDraft
from app.schemas.slides import PresentationOutlineResponse
from app.services import presentation_service as service


def outline_response():
    return {
        "presentation_title": "Model title",
        "target_audience": "Managers",
        "slides": [
            {
                "slide_number": 10,
                "title": "Introduction",
                "purpose": "Introduce the review",
                "layout_type": "bullet_points",
            },
            {
                "slide_number": 20,
                "title": "Conclusion",
                "purpose": "Summarise the review",
                "layout_type": "bullet_points",
            },
        ],
    }


def test_outline_uses_scripted_client_and_cleans_response(scripted_llm):
    client = scripted_llm(outline_response())
    options = PresentationCreate(
        topic="Sales review",
        title="User title",
        num_slides=3,
        include_sources_slide=True,
    ).model_dump()

    outline = service._make_outline(
        client,
        options,
        chunks=[],
        data_names=[],
    )

    assert outline.presentation_title == "User title"
    assert [slide.slide_number for slide in outline.slides] == [1, 2]
    assert outline.slides[0].layout_type == "title"
    assert outline.slides[0].title == "User title"

    call = client.calls[0]
    assert call["schema"] is PresentationOutlineResponse
    assert "NUMBER OF SLIDES: exactly 2" in call["prompt"]
    assert "There are no spreadsheets" in call["prompt"]
    assert call["temperature"] == 0.3
    assert call["num_ctx"] == 8192


def test_invalid_outline_schema_is_rejected(scripted_llm):
    client = scripted_llm({"slides": []})
    options = PresentationCreate(topic="Sales review").model_dump()

    with pytest.raises(RuntimeError, match="ValidationError"):
        service._make_outline(
            client,
            options,
            chunks=[],
            data_names=[],
        )


def test_generator_uses_one_client_for_outline_and_slide_content(
    scripted_llm, monkeypatch
):
    def unexpected_readiness_check(_client):
        pytest.fail("Readiness check should be explicitly disabled.")

    monkeypatch.setattr(
        service,
        "ensure_llm_ready",
        unexpected_readiness_check,
    )

    client = scripted_llm(
        outline_response(),
        '{"subtitle": "Sales overview", "speaker_notes": "Welcome."}',
        {
            "bullets": [{"text": "Review the findings", "source_ids": []}],
            "speaker_notes": "Discuss the findings.",
        },
    )

    generator = service.LocalLlmDeckGenerator(
        client=client,
        check_ready=False,
    )
    options = PresentationCreate(
        topic="Sales review",
        num_slides=3,
        include_sources_slide=True,
    ).model_dump()
    progress = []

    deck = generator.generate(
        notebook=SimpleNamespace(id=1),
        options=options,
        documents=[],
        progress=progress.append,
    )

    assert len(deck.slides) == 2
    assert deck.slides[0].subtitle == "Sales overview"
    assert deck.slides[1].bullets[0].text == "Review the findings"

    assert [call["schema"] for call in client.calls] == [
        PresentationOutlineResponse,
        SlideContentDraft,
        SlideContentDraft,
    ]
    assert progress == [
        "reading documents",
        "outline",
        "content 0/2",
        "content 1/2",
        "content 2/2",
    ]