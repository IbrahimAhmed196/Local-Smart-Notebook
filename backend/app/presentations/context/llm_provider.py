"""LlmContextProvider: one model call per document gives a summary and cited facts (CTX-04).
 
A temporary stand-in for retrieval (RAG-01): it only handles documents that fit one model call (CTX-03).
It reports progress, honours cancellation, and never changes a stored fact id.
"""
 
from __future__ import annotations
 
import logging
import re
from collections.abc import Callable, Sequence
from threading import Event
 
from app.llm.base import LlmClient
from app.llm.cancellation import raise_if_cancelled
from app.presentations.context.errors import ContextExtractionError
from app.presentations.context.limits import check_document_count, check_sizes
from app.presentations.context.readers import TEXT_TYPES, DocumentText, read_document
from app.presentations.context.schemas import (
    ContextFact,
    ContextOptions,
    DocumentContext,
    DocumentExtraction,
    ExtractedFact,
    PresentationContext,
)
from app.presentations.context.selection import select_facts
from app.presentations.context.verify import verify_facts
from app.presentations.prompts.context import build_context_prompt
from app.presentations.schemas.outline import SlideOutlineItem
from app.presentations.schemas.slide_content import SourceChunk
 
log = logging.getLogger(__name__)
 
MAX_FACT_CHARS = 400
MAX_EVIDENCE_CHARS = 300
MAX_SUMMARY_CHARS = 600
 
 
def shorten(text: str, limit: int, ellipsis: bool = True) -> str:
    """Cut at a word boundary, never inside a word. A quote (evidence) is cut without '…', so it stays verbatim."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:") + ("…" if ellipsis else "")
 
 
class LlmContextProvider:
    def __init__(self, client: LlmClient):
        self.client = client
 
    # ------------------------------------------------------------------ build
 
    def build(
        self,
        documents: Sequence,
        topic: str,
        options: ContextOptions | None = None,
        *,
        progress: Callable[[str], None] | None = None,
        cancel_event: Event | None = None,
        previous: PresentationContext | None = None,
        on_document: Callable[[PresentationContext], None] | None = None,
    ) -> PresentationContext:
        options = options or ContextOptions()
        raise_if_cancelled(cancel_event)
 
        text_documents = [d for d in documents if d.file_type in TEXT_TYPES]
        check_document_count(len(text_documents), options)
        texts = [read_document(d) for d in text_documents]
        check_sizes(texts, options)  # before any model call
 
        usable = [t for t in texts if t.status == "used"]
        cap = min(options.max_facts_per_document, max(1, options.max_facts_total // max(1, len(usable))))
 
        saved = {d.document_id: d for d in (previous.documents if previous else []) if d.status == "used"}
 
        results: list[DocumentContext] = []
        number = 0
        for text in texts:
            raise_if_cancelled(cancel_event)
            if text.status != "used":
                results.append(_unusable(text))
            else:
                number += 1
                if progress:
                    progress(f"extracting {number}/{len(usable)}")
                earlier = saved.get(text.document_id)
                if earlier is not None and text.sha256 is not None and earlier.sha256 == text.sha256:
                    results.append(earlier)  # CTX-07: same file, already extracted: no model call
                    continue
                results.append(self._extract(text, topic, options, cap, cancel_event))
            if on_document:  # CTX-07: hand over what is finished so far, so that the caller can save it
                on_document(assemble(topic, results))
        return assemble(topic, results)

 
    def _extract(
        self, text: DocumentText, topic: str, options: ContextOptions, cap: int, cancel_event: Event | None
    ) -> DocumentContext:
        prompt = build_context_prompt(
            topic=topic, audience=options.audience, filename=text.filename, blocks=text.blocks, max_facts=cap
        )
        try:
            extraction = self.client.generate_json(
                prompt,
                DocumentExtraction,
                temperature=options.temperature,
                num_ctx=options.num_ctx,
                cancel_event=cancel_event,
            )
        except RuntimeError as exc:  # LlmError and OllamaError; GenerationCancelled is not a RuntimeError
            raise ContextExtractionError(
                f"Could not extract facts from '{text.filename}': {exc}"
            ) from exc
 
        found = _facts(extraction.facts, text)
        checked = verify_facts(found, text.blocks)  # CTX-06: keep only facts whose quote is in the document
        facts = checked.kept[:cap]
        warnings = list(text.warnings)
        if checked.dropped:
            warnings.append(
                f"'{text.filename}': {len(checked.kept)} of {len(found)} extracted facts matched the document text "
                f"({len(checked.kept) * 100 // len(found)}%); the other {len(checked.dropped)} were dropped."
            )
        if not facts:
            warnings.append(f"'{text.filename}': no usable facts were found in it.")
        return DocumentContext(
            document_id=text.document_id,
            filename=text.filename,
            sha256=text.sha256,
            status="used",
            summary=shorten(extraction.summary, MAX_SUMMARY_CHARS),
            facts=facts,
            facts_checked=len(found),
            facts_dropped=len(checked.dropped),
            chars=text.chars,
            warnings=warnings,
        )
    def for_slide(self, context: PresentationContext, item: SlideOutlineItem) -> list[SourceChunk]:
        """Stateless: it only reads the context it is given, so a stored context works the same."""
        return [fact.as_chunk() for fact in select_facts(context, item)]

 
 
def assemble(topic: str, documents: list[DocumentContext]) -> PresentationContext:
    """The context as it is saved: the user-facing warnings are always rebuilt from the documents."""
    return PresentationContext(
        topic=topic,
        documents=documents,
        warnings=[w for document in documents for w in document.warnings],
    )
 
 
def _unusable(text: DocumentText) -> DocumentContext:
    return DocumentContext(
        document_id=text.document_id,
        filename=text.filename,
        sha256=text.sha256,
        status=text.status,
        warnings=list(text.warnings),
    )
 
 
def _facts(extracted: Sequence[ExtractedFact], text: DocumentText) -> list[ContextFact]:
    """Ids come from the position in the model's answer, assigned before anything is dropped."""
    pages = {block.page for block in text.blocks if block.page is not None}
    facts, seen = [], set()
    for position, item in enumerate(extracted, start=1):
        fact_text = shorten(item.text, MAX_FACT_CHARS)
        key = fact_text.casefold()
        if not fact_text or key in seen:
            continue
        seen.add(key)
        facts.append(
            ContextFact(
                fact_id=f"doc{text.document_id}-f{position}",
                text=fact_text,
                document_id=text.document_id,
                filename=text.filename,
                page=item.page if item.page in pages else None,
                section=(item.section or "").strip() or None,
                evidence=shorten(item.evidence, MAX_EVIDENCE_CHARS, ellipsis=False),
            )
        )
    return facts
