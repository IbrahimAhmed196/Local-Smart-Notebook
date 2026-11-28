"""CTX-03: the limits are checked before any model call and the error names the document."""
 
import pytest
 
from app.core.config import settings
from app.presentations.context.errors import ContextTooLargeError
from app.presentations.context.llm_provider import LlmContextProvider
from app.presentations.context.schemas import ContextOptions
from tests.fake_llm import ScriptedLLMClient
from tests.presentations.context_samples import extraction, fact, txt_document
from tests.presentations.doc_samples import fake_document, make_pdf
 
 
def test_the_options_read_their_limits_from_the_settings(monkeypatch):
    monkeypatch.setattr(settings, "presentation_context_max_documents", 2)
    monkeypatch.setattr(settings, "presentation_context_max_chars_per_document", 777)
    options = ContextOptions()
    assert (options.max_documents, options.max_chars_per_document) == (2, 777)
 
 
def test_too_many_documents_fail_before_any_model_call(tmp_path, use_files):
    client = ScriptedLLMClient()
    documents = [txt_document(tmp_path, i, f"d{i}.txt", "some text here") for i in range(1, 4)]
    with pytest.raises(ContextTooLargeError, match="3 text documents are selected and the limit is 2"):
        LlmContextProvider(client).build(documents, "topic", ContextOptions(max_documents=2))
    assert client.calls == []
 
 
def test_data_files_do_not_count_as_text_documents(tmp_path, use_files):
    client = ScriptedLLMClient()
    sheet = fake_document(1, tmp_path / "sales.csv", "csv")
    context = LlmContextProvider(client).build([sheet], "topic", ContextOptions(max_documents=1))
    assert context.documents == [] and client.calls == []
 
 
def test_a_document_over_the_character_limit_fails_with_its_name_size_and_limit(tmp_path, use_files):
    client = ScriptedLLMClient()
    big = txt_document(tmp_path, 1, "big.txt", "word " * 400)  # about 2,000 characters
    with pytest.raises(ContextTooLargeError) as error:
        LlmContextProvider(client).build([big], "topic", ContextOptions(max_chars_per_document=1000))
    message = str(error.value)
    assert "'big.txt'" in message and "1,999 characters" in message and "limit is 1,000" in message
    assert client.calls == []
 
 
def test_every_oversized_document_is_named_in_one_error(tmp_path, use_files):
    documents = [txt_document(tmp_path, i, f"big{i}.txt", "x" * 600) for i in (1, 2)]
    with pytest.raises(ContextTooLargeError) as error:
        LlmContextProvider(ScriptedLLMClient()).build(documents, "t", ContextOptions(max_chars_per_document=500))
    assert "'big1.txt'" in str(error.value) and "'big2.txt'" in str(error.value)
 
 
def test_a_document_exactly_at_the_limit_is_accepted(tmp_path, use_files):
    client = ScriptedLLMClient(extraction(fact("It fits.")))
    document = txt_document(tmp_path, 1, "ok.txt", "x" * 500)
    LlmContextProvider(client).build([document], "t", ContextOptions(max_chars_per_document=500))
    assert len(client.calls) == 1
 
 
def test_arabic_text_is_counted_in_characters_not_bytes(tmp_path, use_files):
    client = ScriptedLLMClient(extraction(fact("جملة.")))
    document = txt_document(tmp_path, 1, "ar.txt", "ا" * 500)  # 500 characters, 1,000 bytes
    LlmContextProvider(client).build([document], "t", ContextOptions(max_chars_per_document=500))
    assert len(client.calls) == 1
 
 
def test_a_pdf_over_the_page_limit_fails_fast_with_the_page_count(tmp_path, use_files, monkeypatch):
    monkeypatch.setattr(settings, "presentation_context_max_pdf_pages", 1)
    client = ScriptedLLMClient()
    pdf = fake_document(1, make_pdf(tmp_path / "long.pdf", ["one two", "three four"]), "pdf")
    with pytest.raises(ContextTooLargeError, match="'long.pdf': it has 2 pages and the limit is 1"):
        LlmContextProvider(client).build([pdf], "t")
    assert client.calls == []
 
 
def test_the_context_settings_have_documented_defaults_and_can_be_set_from_the_environment(monkeypatch):
    from app.core.config import Settings
 
    plain = Settings(_env_file=None)
    assert (plain.presentation_context_max_chars_per_document, plain.presentation_context_max_documents) == (None, 5)  # None: by model and language
    assert (plain.presentation_context_max_pdf_pages, plain.presentation_context_max_docx_mb) == (100, 20)
    assert (plain.presentation_context_max_facts_per_document, plain.presentation_context_max_facts_total, plain.presentation_context_temperature) == (12, 40, 0.1)
 
    monkeypatch.setenv("PRESENTATION_CONTEXT_MAX_CHARS_PER_DOCUMENT", "24000")
    monkeypatch.setenv("PRESENTATION_CONTEXT_MAX_DOCUMENTS", "3")
    changed = Settings(_env_file=None)
    assert (changed.presentation_context_max_chars_per_document, changed.presentation_context_max_documents) == (24_000, 3)
