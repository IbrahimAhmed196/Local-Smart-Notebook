"""Reads the notebook's uploaded files so the chat model can answer from them.

There is no vector index yet (the ingestion pipeline is still a stub), so this does a
simple, dependable version of retrieval:

  1. read the text of every document in the notebook (pdf, docx, txt, csv, xlsx),
  2. cut it into chunks,
  3. keep the chunks that share the most words with the user's question,
  4. hand them to the model, labelled with the file name (and page for PDFs).

When Stage 2 adds real retrieval, replace `build_context` and nothing else changes.
"""
import csv
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Document
from app.services import file_storage

log = logging.getLogger(__name__)

CHUNK_CHARS = 1200
MAX_FILE_CHARS = 400_000      # never read more than this from one file
MAX_SHEET_ROWS = 500
_WORD = re.compile(r"\w+", re.UNICODE)


@dataclass
class Chunk:
    filename: str
    page: int | None
    text: str


# ---- reading files ------------------------------------------------------------------

def _read_pdf(path: Path) -> list[tuple[int | None, str]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]


def _read_docx(path: Path) -> list[tuple[int | None, str]]:
    import docx

    document = docx.Document(str(path))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    for table in document.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text.strip() for cell in row.cells))
    return [(None, "\n".join(parts))]


def _read_txt(path: Path) -> list[tuple[int | None, str]]:
    raw = path.read_bytes()[:MAX_FILE_CHARS * 4]
    for encoding in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            return [(None, raw.decode(encoding))]
        except UnicodeDecodeError:
            continue
    return [(None, raw.decode("utf-8", errors="replace"))]


def _read_csv(path: Path) -> list[tuple[int | None, str]]:
    text = _read_txt(path)[0][1]
    rows = list(csv.reader(text.splitlines()))[: MAX_SHEET_ROWS + 1]
    return [(None, "\n".join(" | ".join(r) for r in rows))]


def _read_xlsx(path: Path) -> list[tuple[int | None, str]]:
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out: list[tuple[int | None, str]] = []
    try:
        for sheet in book.worksheets:
            lines = [f"[Sheet: {sheet.title}]"]
            for n, row in enumerate(sheet.iter_rows(values_only=True)):
                if n >= MAX_SHEET_ROWS:
                    break
                lines.append(" | ".join("" if c is None else str(c) for c in row))
            out.append((None, "\n".join(lines)))
    finally:
        book.close()
    return out


_READERS = {
    "pdf": _read_pdf,
    "docx": _read_docx,
    "txt": _read_txt,
    "csv": _read_csv,
    "xlsx": _read_xlsx,
}


def read_document(document: Document) -> list[tuple[int | None, str]]:
    """[(page or None, text), ...]. A file that cannot be read gives [] (and is logged)."""
    reader = _READERS.get((document.file_type or "").lower().lstrip("."))
    if reader is None:
        return []
    try:
        return reader(file_storage.resolve(document.file_path))
    except Exception:
        log.exception("Could not read document %s (%s)", document.id, document.filename)
        return []


# ---- chunking and picking the relevant parts ------------------------------------------

def _split(text: str) -> list[str]:
    """Cut on paragraph boundaries into pieces of about CHUNK_CHARS characters."""
    text = re.sub(r"[ \t]+", " ", text).strip()[:MAX_FILE_CHARS]
    chunks, current = [], ""
    for para in re.split(r"\n\s*\n|\n", text):
        para = para.strip()
        if not para:
            continue
        while len(para) > CHUNK_CHARS:  # one huge line: cut it
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:CHUNK_CHARS])
            para = para[CHUNK_CHARS:]
        if len(current) + len(para) + 1 > CHUNK_CHARS and current:
            chunks.append(current)
            current = ""
        current = f"{current}\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


def _words(text: str) -> set[str]:
    return {w for w in (m.lower() for m in _WORD.findall(text)) if len(w) > 2}


def load_chunks(db: Session, notebook_id: int) -> list[Chunk]:
    documents = db.scalars(
        select(Document)
        .where(Document.notebook_id == notebook_id)
        .order_by(Document.uploaded_at.asc(), Document.id.asc())
    )
    chunks: list[Chunk] = []
    for document in documents:
        for page, text in read_document(document):
            chunks.extend(Chunk(document.filename, page, piece) for piece in _split(text))
    return chunks


def pick_chunks(chunks: list[Chunk], question: str, budget: int) -> list[Chunk]:
    """Everything if it fits in `budget` characters; otherwise the best-matching chunks,
    returned in their original reading order."""
    if sum(len(c.text) for c in chunks) <= budget:
        return chunks
    wanted = _words(question)
    scored = []
    for index, chunk in enumerate(chunks):
        overlap = len(wanted & _words(chunk.text))
        scored.append((overlap, -index, index))
    scored.sort(reverse=True)  # most overlap first; ties keep the earlier chunk
    chosen, used = [], 0
    for overlap, _, index in scored:
        size = len(chunks[index].text)
        if used + size > budget:
            continue
        chosen.append(index)
        used += size
    return [chunks[i] for i in sorted(chosen)]


def format_context(chunks: list[Chunk]) -> str:
    blocks = []
    for c in chunks:
        where = f"{c.filename}, page {c.page}" if c.page else c.filename
        blocks.append(f"[{where}]\n{c.text}")
    return "\n\n".join(blocks)


def build_context(db: Session, notebook_id: int, question: str, budget: int) -> tuple[str, list[str]]:
    """Returns (text for the prompt, file names used). ("", []) if the notebook has no
    readable documents."""
    chunks = pick_chunks(load_chunks(db, notebook_id), question, budget)
    names = list(dict.fromkeys(c.filename for c in chunks))
    return format_context(chunks), names
