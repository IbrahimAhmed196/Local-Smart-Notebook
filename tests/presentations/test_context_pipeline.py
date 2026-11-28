"""CTX-08: the whole generator with the new context step (scripted model, real files)."""
 
from types import SimpleNamespace
 
from app.presentations import generator
from app.presentations.context.errors import ContextTooLargeError
from app.schemas.presentations import PresentationCreate
from tests.presentations.context_samples import extraction, fact, txt_document
 
import pytest
 
TEXT = "Revenue grew by 12 percent in the second quarter. Operating costs fell after the warehouse moved."
OUTLINE = {
    "presentation_title": "Sales review",
    "target_audience": "Managers",
    "slides": [
        {"slide_number": 1, "title": "Sales review", "purpose": "Open", "layout_type": "title"},
        {"slide_number": 2, "title": "Revenue growth", "purpose": "How revenue changed", "layout_type": "bullet_points"},
        {"slide_number": 3, "title": "Weather", "purpose": "Rain tomorrow", "layout_type": "bullet_points"},
    ],
}
 
 
def run(client, documents, progress=None):
    options = PresentationCreate(topic="Sales review", num_slides=4).model_dump()  # 3 slides + the sources slide
    return generator.LocalLlmDeckGenerator(client=client).generate(
        notebook=SimpleNamespace(id=1),
        options=options,
        documents=documents,
        progress=progress or (lambda stage: None),
    )
 
 
def test_every_slide_sees_only_its_own_facts_and_the_stages_are_reported(tmp_path, use_files, scripted_llm):
    client = scripted_llm(
        extraction(
            fact("Revenue grew 12%.", evidence="Revenue grew by 12 percent in the second quarter."),
            fact("Costs fell.", evidence="Operating costs fell after the warehouse moved."),
        ),
        OUTLINE,
        {"subtitle": "Hello"},
        {"bullets": []},
        {"bullets": []},
    )
    stages = []
    run(client, [txt_document(tmp_path, 1, "sales.txt", TEXT)], progress=stages.append)
 
    extraction_call, outline_call, _, revenue_call, weather_call = client.calls
    assert "sales.txt" in extraction_call["prompt"]
    assert "Revenue grew 12%." in outline_call["prompt"]  # the outline reads the extracted facts, not raw chunks
    assert "Revenue grew 12%." in revenue_call["prompt"] and "Costs fell." not in revenue_call["prompt"]
    assert "Revenue grew 12%." not in weather_call["prompt"] and "Costs fell." not in weather_call["prompt"]
    assert stages[:3] == ["reading documents", "extracting 1/1", "outline"]
    client.assert_finished()
 
 
def test_a_document_over_the_limit_stops_the_job_before_any_model_call(tmp_path, use_files, scripted_llm, monkeypatch):
    from app.core.config import settings
 
    monkeypatch.setattr(settings, "presentation_context_max_chars_per_document", 500)
    client = scripted_llm()
    with pytest.raises(ContextTooLargeError, match="'big.txt'"):
        run(client, [txt_document(tmp_path, 1, "big.txt", "word " * 300)])
    assert client.calls == []
 
 
def test_the_job_error_message_of_a_context_error_is_shown_as_it_is():
    error = ContextTooLargeError("'big.txt': 9,000 characters; the limit is 500.")
    assert generator.generation_error_message(error) == str(error)
