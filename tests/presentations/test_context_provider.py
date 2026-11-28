"""CTX-04: one model call per document gives a summary and facts with stable ids."""
 
from threading import Event
 
import pytest
 
from app.core.exceptions import GenerationCancelled
from app.presentations.context.errors import ContextExtractionError
from app.presentations.context.llm_provider import LlmContextProvider
from app.presentations.context.schemas import ContextOptions, DocumentExtraction
from tests.fake_llm import ScriptedLLMClient
from tests.presentations.context_samples import extraction, fact, txt_document
from tests.presentations.doc_samples import fake_document, make_blank_pdf, make_pdf
 
 
def build(client, documents, **kwargs):
    return LlmContextProvider(client).build(documents, kwargs.pop("topic", "Sales review"), **kwargs)
 
 
def test_one_call_per_document_with_topic_audience_and_the_document_text(tmp_path, use_files):
    client = ScriptedLLMClient(extraction(fact("Sales grew 12 percent.")), extraction(fact("Costs fell.")))
    documents = [
        txt_document(tmp_path, 1, "sales.txt", "Sales grew 12 percent in March."),
        txt_document(tmp_path, 2, "costs.txt", "Costs fell in April."),
    ]
    options = ContextOptions(audience="the board", temperature=0.2, num_ctx=4096)
    context = build(client, documents, options=options)
 
    assert len(client.calls) == 2
    first = client.calls[0]
    assert first["schema"] is DocumentExtraction
    assert (first["temperature"], first["num_ctx"]) == (0.2, 4096)
    for expected in ("Sales review", "the board", "sales.txt", "Sales grew 12 percent in March."):
        assert expected in first["prompt"]
    assert "Costs fell in April." not in first["prompt"]  # one document per call
    assert [d.filename for d in context.documents] == ["sales.txt", "costs.txt"]
    client.assert_finished()
 
 
def test_pdf_pages_reach_the_prompt_as_markers_and_the_facts_keep_their_page(tmp_path, use_files):
    pdf = fake_document(3, make_pdf(tmp_path / "r.pdf", ["Revenue grew by 12 percent.", "Costs fell in March."]), "pdf")
    client = ScriptedLLMClient(
        extraction(fact("Costs fell in March.", page=2), fact("Revenue is up.", evidence="Revenue grew by 12 percent.", page=9))
    )

    context = build(client, [pdf])
    assert "[Page 1]\nRevenue grew" in client.calls[0]["prompt"] and "[Page 2]" in client.calls[0]["prompt"]
    first, second = context.facts
    assert first.page == 2
    assert second.page == 1  # the model named page 9; the check found the quote on page 1 (CTX-06)
 
 
def test_fact_ids_are_stable_and_carry_the_document_id(tmp_path, use_files):
    text = "Alpha is first. Beta is second. Gamma is third."
    client = ScriptedLLMClient(
        extraction(fact("Alpha is first."), fact("Beta is second."), fact("Gamma is third."))
    )
    context = build(client, [txt_document(tmp_path, 12, "a.txt", text)])
    assert [f.fact_id for f in context.facts] == ["doc12-f1", "doc12-f2", "doc12-f3"]
    assert all(f.document_id == 12 and f.filename == "a.txt" for f in context.facts)
 
 
def test_a_duplicate_fact_keeps_the_original_ids_of_the_others(tmp_path, use_files):
    client = ScriptedLLMClient(extraction(fact("The same fact."), fact("the same fact."), fact("Another fact.")))
    context = build(client, [txt_document(tmp_path, 1, "a.txt", "The same fact. Another fact.")])
    assert [f.fact_id for f in context.facts] == ["doc1-f1", "doc1-f3"]
 
 
def test_a_long_fact_is_cut_at_a_word_and_a_quote_is_not_given_an_ellipsis(tmp_path, use_files):
    long_text = "word " * 200
    client = ScriptedLLMClient(extraction(fact(long_text, evidence=long_text)))
    saved = build(client, [txt_document(tmp_path, 1, "a.txt", long_text)]).facts[0]
    assert len(saved.text) <= 401 and saved.text.endswith("word…")
    assert len(saved.evidence) <= 300 and not saved.evidence.endswith("…")
 
 
def test_the_fact_budget_is_shared_between_documents(tmp_path, use_files):
    many = [fact(f"Fact number {i} here.") for i in range(1, 9)]
    text = " ".join(f"Fact number {i} here." for i in range(1, 9))
    client = ScriptedLLMClient(extraction(*many), extraction(*many))
    documents = [txt_document(tmp_path, i, f"d{i}.txt", text) for i in (1, 2)]
    context = build(client, documents, options=ContextOptions(max_facts_per_document=10, max_facts_total=6))
    assert [len(d.facts) for d in context.documents] == [3, 3]
    assert "at most 3 facts" in client.calls[0]["prompt"]
 
 
def test_progress_counts_only_the_documents_that_are_extracted(tmp_path, use_files):
    stages = []
    scan = fake_document(1, make_blank_pdf(tmp_path / "scan.pdf"), "pdf")
    documents = [scan, txt_document(tmp_path, 2, "a.txt", "Alpha."), txt_document(tmp_path, 3, "b.txt", "Beta.")]
    client = ScriptedLLMClient(extraction(fact("Alpha.")), extraction(fact("Beta.")))
    build(client, documents, progress=stages.append)
    assert stages == ["extracting 1/2", "extracting 2/2"]
 
 
def test_a_scanned_pdf_makes_no_model_call_and_leaves_a_visible_warning(tmp_path, use_files):
    scan = fake_document(1, make_blank_pdf(tmp_path / "scan.pdf"), "pdf")
    client = ScriptedLLMClient()
    context = build(client, [scan])
    assert client.calls == []
    assert context.documents[0].status == "empty"
    assert len(context.warnings) == 1 and "'scan.pdf' was not used" in context.warnings[0]
 
 
def test_a_document_with_no_usable_facts_says_so(tmp_path, use_files):
    client = ScriptedLLMClient(extraction())
    context = build(client, [txt_document(tmp_path, 1, "a.txt", "Some text.")])
    assert context.warnings == ["'a.txt': no usable facts were found in it."]
 
 
def test_no_documents_means_an_empty_context_and_no_model_call():
    client = ScriptedLLMClient()
    context = build(client, [])
    assert context.documents == [] and context.facts == [] and client.calls == []
 
 
def test_a_failing_document_fails_the_job_with_its_name(tmp_path, use_files):
    client = ScriptedLLMClient(extraction(fact("A.")), RuntimeError("Ollama returned invalid JSON"))
    documents = [txt_document(tmp_path, 1, "ok.txt", "A."), txt_document(tmp_path, 2, "bad.txt", "B.")]
    with pytest.raises(ContextExtractionError, match="Could not extract facts from 'bad.txt': Ollama returned invalid JSON"):
        build(client, documents)
 
 
def test_a_cancelled_job_stops_before_the_first_call(tmp_path, use_files):
    event = Event()
    event.set()
    client = ScriptedLLMClient()
    with pytest.raises(GenerationCancelled):
        build(client, [txt_document(tmp_path, 1, "a.txt", "Alpha.")], cancel_event=event)
    assert client.calls == []
 
 
def test_a_cancel_between_documents_stops_before_the_next_call(tmp_path, use_files):
    event = Event()
    client = ScriptedLLMClient(extraction(fact("Alpha.")))
    documents = [txt_document(tmp_path, 1, "a.txt", "Alpha."), txt_document(tmp_path, 2, "b.txt", "Beta.")]
 
    def progress(stage):
        if stage == "extracting 2/2":
            event.set()  # the user pressed cancel while document 1 was being read
 
    with pytest.raises(GenerationCancelled):
        build(client, documents, progress=progress, cancel_event=event)
    assert len(client.calls) == 1
 
 
def test_arabic_documents_are_extracted_in_their_own_language(tmp_path, use_files):
    text = "ارتفعت المبيعات بنسبة ١٢ في المئة."
    client = ScriptedLLMClient(extraction(fact(text), summary="ملخص قصير."))
    context = build(client, [txt_document(tmp_path, 1, "ar.txt", text)])
    assert context.facts[0].text == text and context.documents[0].summary == "ملخص قصير."
    assert text in client.calls[0]["prompt"]
