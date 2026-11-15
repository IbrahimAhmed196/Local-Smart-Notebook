"""OUT-01: the outline schema v2 (strict layout names, plus section, key points, hints)."""
 
import json
from pathlib import Path
 
import pytest
from pydantic import ValidationError
 
from app.presentations.outline import clean_outline
from app.presentations.schemas.layouts import SLIDE_LAYOUTS
from app.presentations.schemas.outline import DataHint, PresentationOutlineResponse, SlideOutlineItem
 
 
def item(layout="bullet_points", **extra):
    return SlideOutlineItem(slide_number=1, title="T", purpose="P", layout_type=layout, **extra)
 
 
def test_an_outline_stored_before_v2_still_loads_with_empty_new_fields():
    old = {
        "presentation_title": "Old", "target_audience": "All",
        "slides": [{"slide_number": 1, "title": "A", "purpose": "B", "layout_type": "title"}],
    }
    outline = PresentationOutlineResponse.model_validate(old)
    slide = outline.slides[0]
    assert (outline.language, outline.sections) == (None, [])
    assert (slide.section, slide.key_points, slide.source_hints, slide.data_hint, slide.image_intent) == (None, [], [], None, None)
 
 
def test_the_sample_outline_in_the_docs_still_validates():
    # look upwards for the repo root, so that the test works from tests/ and from tests/presentations/
    relative = Path("docs") / "samples" / "sample_outline.json"
    path = next(p / relative for p in Path(__file__).resolve().parents if (p / relative).exists())
    PresentationOutlineResponse.model_validate_json(path.read_text(encoding="utf-8"))
 
 
def test_every_registry_layout_is_accepted_and_nothing_else():
    for name in SLIDE_LAYOUTS:
        assert item(name).layout_type == name
    with pytest.raises(ValidationError):
        item("timeline")
    with pytest.raises(ValidationError):
        item("closing")  # in the registry, but not selectable by the model
 
 
def test_a_rejected_layout_says_which_names_are_allowed():
    with pytest.raises(ValidationError, match="layout_type must be one of: title"):
        item("timeline")
 
 
def test_spelling_variants_are_mapped_to_the_real_layout_name():
    assert item("Bullet Points").layout_type == "bullet_points"
    assert item("comparison").layout_type == "two_columns"
 
 
def test_the_json_schema_sent_to_ollama_lists_exactly_the_registry_layouts():
    schema = SlideOutlineItem.model_json_schema()
    assert schema["properties"]["layout_type"]["enum"] == list(SLIDE_LAYOUTS)
 
 
def test_the_new_fields_round_trip():
    slide = item(
        "chart", section="Results", key_points=["North leads"], source_hints=["doc2-f3", "doc1:p4"],
        data_hint=DataHint(kind="chart", chart_type="bar", x="region", y=["revenue"], aggregation="sum", document_id=5),
    )
    outline = PresentationOutlineResponse(
        presentation_title="T", target_audience="A", slides=[slide], language="en", sections=["Results"]
    )
    again = PresentationOutlineResponse.model_validate(json.loads(outline.model_dump_json()))
    assert again == outline
 
 
def test_a_bad_data_hint_is_rejected():
    with pytest.raises(ValidationError):
        DataHint(kind="chart", chart_type="radar")
 
 
def options():
    return {"topic": "Sales", "audience": "Managers", "num_slides": 3, "title": None, "include_sources_slide": False}
 
 
def test_the_repair_keeps_language_and_sections():
    outline = PresentationOutlineResponse(
        presentation_title="T", target_audience="A", language="ar", sections=["One", "Two"],
        slides=[item("title"), item("bullet_points", section="One")],
    )
    outline.slides[1].slide_number = 2
    cleaned = clean_outline(outline, {**options(), "num_slides": 2}, has_data=False)
    assert (cleaned.language, cleaned.sections, cleaned.slides[1].section) == ("ar", ["One", "Two"], "One")
 
 
def test_the_repair_drops_the_data_hint_when_there_is_no_spreadsheet():
    hint = DataHint(kind="chart", chart_type="bar")
    outline = PresentationOutlineResponse(
        presentation_title="T", target_audience="A",
        slides=[item("title"), SlideOutlineItem(slide_number=2, title="C", purpose="P", layout_type="chart", data_hint=hint)],
    )
    cleaned = clean_outline(outline, {**options(), "num_slides": 2}, has_data=False)
    assert cleaned.slides[1].layout_type == "bullet_points" and cleaned.slides[1].data_hint is None

