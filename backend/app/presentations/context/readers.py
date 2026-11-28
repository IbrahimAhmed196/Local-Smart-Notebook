"""Reading TXT, PDF and DOCX documents into text blocks, with a status the user can see (CTX-02).
 
One block is one page (PDF), one section under a heading (DOCX) or the whole file (TXT). Nothing here calls a model
or touches the database: read_file() works on a path, read_document() adds the Document row's name and id.
"""
 
from __future__ import annotations
 
import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
 
from lxml import etree
from pypdf import PdfReader
 
from app.core.config import settings
from app.presentations.context.schemas import DocumentStatus
from app.services import document_service
 
log = logging.getLogger(__name__)
 
TEXT_TYPES = ("txt", "pdf", "docx")  # csv / xlsx are data files, not text
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = f"{{{W_NS}}}"
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
 
 
@dataclass(frozen=True)
class Block:
    text: str
    page: int | None = None
    heading: str | None = None
 
 
@dataclass
class DocumentText:
    document_id: int
    filename: str
    sha256: str | None = None
    status: DocumentStatus = "used"
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # why it was not used, or what was skipped
 
    @property
    def chars(self) -> int:
        return sum(len(block.text) for block in self.blocks)
 
 
class _Problem(Exception):
    """A document that cannot be used; carries the status and the reason (without the file name)."""
 
    def __init__(self, status: DocumentStatus, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason
 
 
def normalise_text(text: str) -> str:
    """Tidy whitespace so that the character count is the size of what a model will really read."""
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
 
 
def read_document(doc) -> DocumentText:
    """Read one Document row. It never raises for a bad file: the result says what happened."""
    result = DocumentText(document_id=doc.id, filename=doc.filename, sha256=getattr(doc, "sha256", None))
    try:
        path = document_service.get_file_path(doc)
        result.blocks, notes = read_file(path, doc.file_type)
        result.warnings = [f"'{doc.filename}': {note}" for note in notes]
    except _Problem as problem:
        result.status = problem.status
        result.warnings = [f"'{doc.filename}' was not used: {problem.reason}"]
    except Exception as exc:  # parsers raise many kinds of errors for a damaged file
        log.warning("Document %s could not be read for the presentation context", doc.id, exc_info=True)
        result.status = "unreadable"
        result.warnings = [
            f"'{doc.filename}' was not used: the file could not be read ({type(exc).__name__}). "
            "It may be damaged, password-protected or missing."
        ]
    return result
 
 
def read_file(path: Path, file_type: str) -> tuple[list[Block], list[str]]:
    """(blocks, notes) of a file. Raises _Problem when the file cannot be used at all."""
    readers = {"txt": _read_txt, "pdf": _read_pdf, "docx": _read_docx}
    if file_type not in readers:
        raise _Problem("unreadable", f"the file type '{file_type}' is not a text document")
    blocks, notes = readers[file_type](path)
    blocks = [Block(normalise_text(b.text), b.page, b.heading) for b in blocks]
    blocks = [b for b in blocks if b.text]
    if not blocks:
        if file_type == "pdf":
            raise _Problem("empty", "it has no readable text. It may be a scanned PDF (text recognition is not available yet).")
        raise _Problem("empty", "it contains no text.")
    return blocks, notes
 
 
# ------------------------------------------------------------------ TXT
 
 
def _read_txt(path: Path) -> tuple[list[Block], list[str]]:
    text = path.read_bytes().decode("utf-8-sig", errors="replace")
    if text and text.count("\ufffd") / len(text) > 0.02:
        raise _Problem("unreadable", "it is not UTF-8 text (save it as UTF-8 and upload it again).")
    return [Block(text)], []
 
 
# ------------------------------------------------------------------ PDF
 
 
def _read_pdf(path: Path) -> tuple[list[Block], list[str]]:
    reader = PdfReader(str(path))
    if reader.is_encrypted and not reader.decrypt(""):
        raise _Problem("unreadable", "it is password-protected.")
    count = len(reader.pages)
    if count > settings.presentation_context_max_pdf_pages:
        raise _Problem("too_large", f"it has {count} pages and the limit is {settings.presentation_context_max_pdf_pages}.")
    blocks, empty = [], []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            blocks.append(Block(text, page=number))
        else:
            empty.append(number)
    notes = []
    if blocks and empty:
        shown = ", ".join(str(n) for n in empty[:10]) + (" ..." if len(empty) > 10 else "")
        notes.append(f"page(s) {shown} have no readable text and were skipped (scanned images?).")
    return blocks, notes
 
 
# ------------------------------------------------------------------ DOCX
 
 
def _read_docx(path: Path) -> tuple[list[Block], list[str]]:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("word/document.xml")
        limit = int(settings.presentation_context_max_docx_mb * 1024 * 1024)
        if info.file_size > limit:
            raise _Problem(
                "too_large",
                f"its text part is {info.file_size / 1024 / 1024:.0f} MB uncompressed and the limit is "
                f"{settings.presentation_context_max_docx_mb:g} MB.",
            )
        xml = archive.read(info)
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    body = etree.fromstring(xml, parser).find(f"{_W}body")
    if body is None:
        raise _Problem("unreadable", "it has no document body.")
 
    blocks: list[Block] = []
    heading: str | None = None
    lines: list[str] = []
 
    def flush():
        if lines:
            blocks.append(Block("\n".join(lines), heading=heading))
            lines.clear()
 
    for element in _body_items(body):
        if element.tag == f"{_W}tbl":
            lines.extend(_table_rows(element))
            continue
        text = _paragraph_text(element)
        if not text.strip():
            continue
        if _is_heading(element):
            flush()
            heading = text.strip()
        else:
            lines.append(text)
    flush()
    return blocks, []
 
 
def _body_items(parent):
    """Paragraphs and tables in reading order, also inside content controls (w:sdt)."""
    for child in parent:
        if child.tag in (f"{_W}p", f"{_W}tbl"):
            yield child
        elif child.tag == f"{_W}sdt":
            content = child.find(f"{_W}sdtContent")
            if content is not None:
                yield from _body_items(content)
 
 
def _paragraph_text(paragraph) -> str:
    parts = []
    for node in paragraph.iter(f"{_W}t", f"{_W}tab", f"{_W}br"):
        parts.append(node.text or "" if node.tag == f"{_W}t" else " ")
    return "".join(parts)
 
 
def _is_heading(paragraph) -> bool:
    properties = paragraph.find(f"{_W}pPr")
    if properties is None:
        return False
    style = properties.find(f"{_W}pStyle")
    name = (style.get(f"{_W}val") if style is not None else "") or ""
    return name.lower().startswith(("heading", "title")) or properties.find(f"{_W}outlineLvl") is not None
 
 
def _table_rows(table) -> list[str]:
    rows = []
    for row in table.findall(f"{_W}tr"):
        cells = [" ".join(_paragraph_text(p).strip() for p in cell.iter(f"{_W}p")).strip() for cell in row.findall(f"{_W}tc")]
        if any(cells):
            rows.append(" | ".join(cells))
    return rows
