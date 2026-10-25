"""Plain-text context for the slide writer: a stand-in until the retrieval feature exists.
 
It reads the notebook's text documents (txt, pdf, docx), cuts them into chunks and, for
each slide, picks the chunks that share the most words with the slide's title and purpose.
When embeddings and Qdrant are ready, replace make_selector() with a real search; the
slide writer only needs "a function from a slide to a list of SourceChunk"."""
 
import logging
import re
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
 
from lxml import etree
from pypdf import PdfReader
 
from app.schemas.slide_content import SourceChunk
from app.schemas.slides import SlideOutlineItem
from app.services import document_service
 
log = logging.getLogger(__name__)
 
CHUNK_CHARS = 900
MAX_CHARS_PER_DOCUMENT = 300_000
TOP_K = 4  # chunks given to the model for one slide
TEXT_TYPES = ("txt", "pdf", "docx")  # csv / xlsx are data files, not text
WORD = re.compile(r"\w{3,}", re.UNICODE)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 
 
def read_blocks(path: Path, file_type: str) -> list[tuple[int | None, str]]:
    """(page number or None, text) for every page / block of a document."""
    if file_type == "txt":
        return [(None, path.read_text(encoding="utf-8", errors="replace"))]
    if file_type == "pdf":
        reader = PdfReader(str(path))
        return [(n, page.extract_text() or "") for n, page in enumerate(reader.pages, 1)]
    if file_type == "docx":
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(xml, parser)
        paragraphs = [
            "".join(t.text or "" for t in p.iter(f"{{{W_NS}}}t"))
            for p in root.iter(f"{{{W_NS}}}p")
        ]
        return [(None, "\n".join(paragraphs))]
    return []
 
 
def _pieces(text: str) -> list[str]:
    """Paragraphs, with anything longer than a chunk cut at sentence ends."""
    pieces = []
    for paragraph in re.split(r"\n{2,}", text):
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        while len(paragraph) > CHUNK_CHARS:
            cut = paragraph.rfind(". ", 0, CHUNK_CHARS)
            cut = cut + 1 if cut > CHUNK_CHARS // 3 else CHUNK_CHARS
            pieces.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if paragraph:
            pieces.append(paragraph)
    return pieces
 
 
def _pack(pieces: list[str]) -> list[str]:
    """Join neighbouring pieces until a chunk is about CHUNK_CHARS long."""
    chunks, current = [], ""
    for piece in pieces:
        if current and len(current) + len(piece) + 1 > CHUNK_CHARS:
            chunks.append(current)
            current = ""
        current = f"{current} {piece}".strip()
    if current:
        chunks.append(current)
    return chunks
 
 
def build_chunks(documents: Sequence) -> list[SourceChunk]:
    """Chunks of every text document; a document that cannot be read is skipped."""
    chunks: list[SourceChunk] = []
    for doc in documents:
        if doc.file_type not in TEXT_TYPES:
            continue
        try:
            blocks = read_blocks(document_service.get_file_path(doc), doc.file_type)
        except Exception:
            log.warning(
                "Document %s could not be read for slide context", doc.id, exc_info=True
            )
            continue
        number, used = 0, 0
        for page, text in blocks:
            for chunk in _pack(_pieces(text)):
                if used >= MAX_CHARS_PER_DOCUMENT:
                    break
                number += 1
                used += len(chunk)
                chunks.append(
                    SourceChunk(
                        chunk_id=f"doc{doc.id}-c{number}",
                        document_id=doc.id,
                        filename=doc.filename,
                        page=page,
                        text=chunk,
                    )
                )
    return chunks
 
 
def make_selector(
    chunks: Sequence[SourceChunk], top_k: int = TOP_K
) -> Callable[[SlideOutlineItem], list[SourceChunk]]:
    """The `chunks_for_slide` function that Task 2's slide writer expects."""
    tokens = [{w.lower() for w in WORD.findall(c.text)} for c in chunks]
 
    def select(item: SlideOutlineItem) -> list[SourceChunk]:
        if (item.layout_type or "").strip().lower() == "title" or not chunks:
            return []
        query = {w.lower() for w in WORD.findall(f"{item.title} {item.purpose}")}
        ranked = sorted(range(len(chunks)), key=lambda i: (-len(query & tokens[i]), i))
        best = [chunks[i] for i in ranked[:top_k] if query & tokens[i]]
        return best or list(chunks[:top_k])  # nothing matched: the opening chunks
 
    return select
