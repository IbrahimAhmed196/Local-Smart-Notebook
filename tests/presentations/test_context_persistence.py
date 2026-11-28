"""CTX-07: each document is saved as soon as it is extracted, and a later run of the same row reuses it."""
 
from pathlib import Path
from unittest.mock import Mock
 
import pytest
 
from app.database import database
from app.database.models import Presentation, PresentationStatus
from app.presentations import generator as deck_generation
from app.presentations import runner
from app.presentations.context import readers
from app.presentations.context.llm_provider import LlmContextProvider
from app.presentations.context.schemas import PresentationContext
from app.presentations.schemas.outline import SlideOutlineItem
from app.schemas.presentations import PresentationCreate, PresentationOut
from tests.presentations.context_samples import extraction, fact
from tests.presentations.doc_samples import fake_document, make_blank_pdf
 
SENTENCES = {n: f"Document number {n} states one clear fact." for n in range(1, 6)}
OUTLINE = {
    "presentation_title": "Sales",
    "target_audience": "Managers",
    "slides": [
        {"slide_number": 1, "title": "Sales", "purpose": "Open", "layout_type": "title"},
        {"slide_number": 2, "title": "Facts", "purpose": "The facts", "layout_type": "bullet_points"},
        {"slide_number": 3, "title": "Details", "purpose": "The details", "layout_type": "bullet_points"},
    ],
}
 
 
def answer(n):
    return extraction(fact(f"Fact {n}.", evidence=SENTENCES[n]), summary=f"Summary {n}.")
 
 
@pytest.fixture
def five_documents(tmp_path, monkeypatch):
    documents = []
    for n in range(1, 6):
        path = tmp_path / f"d{n}.txt"
        path.write_text(SENTENCES[n], encoding="utf-8")
        documents.append(fake_document(n, path, "txt", sha256=f"sha-{n}"))
    monkeypatch.setattr(readers.document_service, "get_file_path", lambda doc: Path(doc.file_path))
    monkeypatch.setattr(runner, "selected_documents", lambda db, notebook, ids: documents)
    monkeypatch.setattr(runner, "render_deck", Mock(return_value="unused.pptx"))
    return documents
 
 
@pytest.fixture
def pending(db, notebook_id):
    p = Presentation(
        notebook_id=notebook_id,
        title="Context test",
        status=PresentationStatus.PENDING,
        stage="queued",
        options=PresentationCreate(topic="Sales", num_slides=4).model_dump(),
    )
    db.add(p)
    db.commit()
    return p
 
 
def use_client(monkeypatch, client):
    monkeypatch.setattr(
        deck_generation, "get_generator", lambda: deck_generation.LocalLlmDeckGenerator(client=client)
    )
 
 
def run(db, p):
    runner.run_generation(p.id)
    db.expire_all()
    return db.get(Presentation, p.id)
 
 
def test_a_failure_at_document_3_keeps_documents_1_and_2(db, pending, five_documents, monkeypatch, scripted_llm):
    use_client(monkeypatch, scripted_llm(answer(1), answer(2), RuntimeError("model crashed")))
    p = run(db, pending)
 
    assert p.status == PresentationStatus.FAILED
    assert p.error == "Could not extract facts from 'd3.txt': model crashed"  # readable, names the document
    assert p.stage == "extracting 3/5"
    saved = PresentationContext.model_validate(p.context)
    assert [d.filename for d in saved.documents] == ["d1.txt", "d2.txt"]
    assert [f.fact_id for f in saved.facts] == ["doc1-f1", "doc2-f1"]
 
 
def test_a_later_run_of_the_same_row_extracts_only_documents_3_to_5(db, pending, five_documents, monkeypatch, scripted_llm):
    use_client(monkeypatch, scripted_llm(answer(1), answer(2), RuntimeError("model crashed")))
    failed = run(db, pending)
    assert failed.status == PresentationStatus.FAILED
 
    # JOB-05 will do this move in the service; here the test makes it by hand: back to PENDING, same row.
    failed.status, failed.error, failed.stage = PresentationStatus.PENDING, None, "queued"
    db.commit()
    second = scripted_llm(answer(3), answer(4), answer(5), OUTLINE, {"subtitle": "Hi"}, {"bullets": []}, {"bullets": []})
    use_client(monkeypatch, second)
    p = run(db, failed)
 
    assert p.status == PresentationStatus.COMPLETED
    extraction_prompts = [c["prompt"] for c in second.calls if "prepare source material" in c["prompt"]]
    assert len(extraction_prompts) == 3
    assert all(name in prompt for name, prompt in zip(["d3.txt", "d4.txt", "d5.txt"], extraction_prompts))
    assert [d.document_id for d in PresentationContext.model_validate(p.context).documents] == [1, 2, 3, 4, 5]
    second.assert_finished()
 
 
def test_a_document_that_changed_since_the_first_run_is_extracted_again(db, pending, five_documents, monkeypatch, scripted_llm):
    use_client(monkeypatch, scripted_llm(answer(1), answer(2), RuntimeError("model crashed")))
    failed = run(db, pending)
    failed.status, failed.error = PresentationStatus.PENDING, None
    db.commit()
    five_documents[0].sha256 = "sha-1-edited"  # the user replaced d1.txt in the meantime
 
    second = scripted_llm(answer(1), answer(3), answer(4), answer(5), OUTLINE, {"subtitle": "Hi"}, {"bullets": []}, {"bullets": []})
    use_client(monkeypatch, second)
    run(db, failed)
    assert sum("prepare source material" in c["prompt"] for c in second.calls) == 4  # d1 again, d2 reused
    second.assert_finished()
 
 
def test_unusable_documents_leave_a_warning_that_the_api_returns(db, pending, tmp_path, monkeypatch, scripted_llm):
    scan = fake_document(1, make_blank_pdf(tmp_path / "scan.pdf"), "pdf", sha256="sha-scan")
    monkeypatch.setattr(readers.document_service, "get_file_path", lambda doc: Path(doc.file_path))
    monkeypatch.setattr(runner, "selected_documents", lambda db, notebook, ids: [scan])
    monkeypatch.setattr(runner, "render_deck", Mock(return_value="unused.pptx"))
    use_client(monkeypatch, scripted_llm(OUTLINE, {"subtitle": "Hi"}, {"bullets": []}, {"bullets": []}))
    p = run(db, pending)
 
    assert p.status == PresentationStatus.COMPLETED
    out = PresentationOut.model_validate(p)
    assert any("'scan.pdf' was not used" in w for w in out.warnings)
 
 
def test_the_context_is_never_part_of_the_api_response(db, pending, five_documents, monkeypatch, scripted_llm):
    use_client(monkeypatch, scripted_llm(answer(1), answer(2), RuntimeError("model crashed")))
    p = run(db, pending)
    assert p.context  # it is stored ...
    assert "context" not in PresentationOut.model_validate(p).model_dump()  # ... but never returned
 
 
def test_regenerating_a_slide_needs_no_extraction_call(db, pending, five_documents, monkeypatch, scripted_llm):
    use_client(monkeypatch, scripted_llm(answer(1), answer(2), RuntimeError("model crashed")))
    p = run(db, pending)
    stored = PresentationContext.model_validate(p.context)  # what JOB-06 loads from the row
 
    client = scripted_llm()  # no scripted answers at all
    item = SlideOutlineItem(
        slide_number=2, title="Document", purpose="The facts", layout_type="bullet_points", source_hints=["doc2-f1"]
    )
    chunks = LlmContextProvider(client).for_slide(stored, item)
    assert chunks[0].chunk_id == "doc2-f1" and client.calls == []  # the stored facts are enough
