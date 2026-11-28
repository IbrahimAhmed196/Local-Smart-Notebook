"""CTX-02: the readers return text blocks and a status the user can see."""
 
import zipfile
 
from app.core.config import settings
from app.presentations.context.readers import normalise_text, read_document
 
from tests.presentations.doc_samples import fake_document, make_blank_pdf, make_docx, make_pdf
 
 
def read(path, file_type, **kwargs):
    return read_document(fake_document(7, path, file_type, **kwargs))
 
 
def test_a_txt_file_is_one_block(tmp_path, use_files):
    path = tmp_path / "notes.txt"
    path.write_text("First line.\n\n\n\nSecond   line.", encoding="utf-8")
    result = read(path, "txt")
    assert result.status == "used" and result.warnings == []
    assert [b.text for b in result.blocks] == ["First line.\n\nSecond line."]
 
 
def test_arabic_text_is_read_as_it_is(tmp_path, use_files):
    path = tmp_path / "arabic.txt"
    path.write_text("ارتفعت المبيعات في الربع الثاني", encoding="utf-8")
    assert read(path, "txt").blocks[0].text == "ارتفعت المبيعات في الربع الثاني"
 
 
def test_a_txt_file_that_is_not_utf8_is_unreadable_with_a_reason(tmp_path, use_files):
    path = tmp_path / "old.txt"
    path.write_bytes("مرحبا بالعالم".encode("cp1256"))
    result = read(path, "txt")
    assert result.status == "unreadable" and "UTF-8" in result.warnings[0] and "'old.txt'" in result.warnings[0]
 
 
def test_a_pdf_keeps_page_numbers(tmp_path, use_files):
    path = make_pdf(tmp_path / "report.pdf", ["Revenue grew by 12 percent.", "Costs fell in March."])
    result = read(path, "pdf")
    assert result.status == "used"
    assert [(b.page, b.text) for b in result.blocks] == [(1, "Revenue grew by 12 percent."), (2, "Costs fell in March.")]
 
 
def test_a_scanned_pdf_is_reported_as_empty(tmp_path, use_files):
    result = read(make_blank_pdf(tmp_path / "scan.pdf"), "pdf")
    assert result.status == "empty" and result.blocks == []
    assert "scanned" in result.warnings[0] and "'scan.pdf'" in result.warnings[0]
 
 
def test_a_pdf_with_some_empty_pages_is_used_with_a_note(tmp_path, use_files):
    path = make_pdf(tmp_path / "mixed.pdf", ["Real text on page one.", "", "Real text on page three."])
    result = read(path, "pdf")
    assert result.status == "used" and [b.page for b in result.blocks] == [1, 3]
    assert "page(s) 2" in result.warnings[0]
 
 
def test_a_pdf_over_the_page_limit_is_too_large(tmp_path, use_files, monkeypatch):
    monkeypatch.setattr(settings, "presentation_context_max_pdf_pages", 2)
    result = read(make_pdf(tmp_path / "long.pdf", ["a one", "a two", "a three"]), "pdf")
    assert result.status == "too_large" and "3 pages" in result.warnings[0] and "limit is 2" in result.warnings[0]
 
 
def test_a_corrupt_pdf_is_unreadable_not_a_crash(tmp_path, use_files):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.4 this is not really a pdf")
    result = read(path, "pdf")
    assert result.status == "unreadable" and "'broken.pdf' was not used" in result.warnings[0]
 
 
def test_a_docx_keeps_headings_and_table_rows(tmp_path, use_files):
    result = read(make_docx(tmp_path / "sales.docx"), "docx")
    assert result.status == "used"
    first, second = result.blocks
    assert first.heading == "Sales review" and first.text == "Revenue grew in the second quarter."
    assert second.heading == "Regions"
    assert "North was the strongest region." in second.text
    assert "Region | Revenue" in second.text and "North | 200000" in second.text  # the table is not lost
 
 
def test_a_corrupt_docx_is_unreadable(tmp_path, use_files):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip file at all")
    assert read(path, "docx").status == "unreadable"
 
 
def test_a_docx_without_a_text_part_is_unreadable(tmp_path, use_files):
    path = tmp_path / "hollow.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
    assert read(path, "docx").status == "unreadable"
 
 
def test_a_huge_docx_text_part_is_too_large_and_is_never_read(tmp_path, use_files, monkeypatch):
    monkeypatch.setattr(settings, "presentation_context_max_docx_mb", 0.001)  # about 1 KB
    result = read(make_docx(tmp_path / "big.docx"), "docx")
    assert result.status == "too_large" and "uncompressed" in result.warnings[0]
 
 
def test_a_missing_file_is_reported_not_raised(tmp_path, use_files):
    assert read(tmp_path / "gone.txt", "txt").status == "unreadable"
 
 
def test_the_result_carries_the_document_identity(tmp_path, use_files):
    path = tmp_path / "a.txt"
    path.write_text("hello world", encoding="utf-8")
    result = read(path, "txt", sha256="abc")
    assert (result.document_id, result.filename, result.sha256) == (7, "a.txt", "abc")
 
 
def test_normalise_text_counts_what_a_model_will_read():
    assert normalise_text("a \t b\r\n\r\n\r\n\r\nc\x00 ") == "a b\n\nc"
