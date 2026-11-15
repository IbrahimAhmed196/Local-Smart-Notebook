"""CTX-01: the shape of the context that every later step relies on."""
 
from app.presentations.context.schemas import (
    ContextFact,
    ContextOptions,
    DocumentContext,
    DocumentExtraction,
    PresentationContext,
)
 
 
def sample():
    return PresentationContext(
        topic="Sales",
        documents=[
            DocumentContext(
                document_id=3,
                filename="a.pdf",
                summary="About sales.",
                facts=[ContextFact(fact_id="doc3-f1", text="Sales grew.", document_id=3, filename="a.pdf", page=2, evidence="Sales grew by 12 percent")],
            ),
            DocumentContext(document_id=4, filename="b.txt", status="empty", warnings=["'b.txt' was not used: it contains no text."]),
        ],
        warnings=["'b.txt' was not used: it contains no text."],
    )
 
 
def test_an_empty_context_is_valid_and_has_no_facts():
    context = PresentationContext()
    assert context.facts == [] and context.warnings == [] and context.document(1) is None
 
 
def test_the_context_survives_a_trip_through_json():
    # CTX-07 stores it in a JSON column and loads it again after a restart
    restored = PresentationContext.model_validate(sample().model_dump(mode="json"))
    assert restored == sample()
    assert [f.fact_id for f in restored.facts] == ["doc3-f1"]
 
 
def test_a_fact_becomes_the_source_chunk_that_the_slide_writer_accepts():
    chunk = sample().facts[0].as_chunk()
    assert (chunk.chunk_id, chunk.document_id, chunk.filename, chunk.page, chunk.text) == (
        "doc3-f1", 3, "a.pdf", 2, "Sales grew."
    )
 
 
def test_the_json_schema_that_the_model_receives_is_small_and_has_no_ids():
    schema = DocumentExtraction.model_json_schema()
    fact = schema["$defs"]["ExtractedFact"]["properties"]
    assert set(fact) == {"text", "page", "section", "evidence"}  # ids are assigned by the code, not the model
    assert set(schema["properties"]) == {"summary", "facts"}
 
 
def test_the_options_have_sensible_defaults():
    options = ContextOptions()
    assert options.audience == "general audience"
    assert options.max_facts_per_document <= options.max_facts_total
