"""What the context step returns (CTX-01): per-document summaries and facts with stable ids.
 
Two kinds of model live here:
- ExtractedFact / DocumentExtraction: what the LLM answers for ONE document (kept small on purpose).
- ContextFact / DocumentContext / PresentationContext: what the pipeline keeps, stores and cites.
"""
 
from __future__ import annotations
 
from typing import Literal
 
from pydantic import BaseModel, Field
 
from app.core.config import settings
from app.presentations.schemas.slide_content import SourceChunk
 
DocumentStatus = Literal["used", "empty", "unreadable", "too_large"]
 
 
class ContextOptions(BaseModel):
    """What one context run needs. Limits default to the settings, read when the object is created."""
 
    audience: str = "general audience"
    model_name: str = Field(default_factory=lambda: settings.presentation_model)
    # None: the limit depends on the model and the language (context/budget.py); a number overrides that.
    max_chars_per_document: int | None = Field(default_factory=lambda: settings.presentation_context_max_chars_per_document)
    max_documents: int = Field(default_factory=lambda: settings.presentation_context_max_documents)
    max_facts_per_document: int = Field(default_factory=lambda: settings.presentation_context_max_facts_per_document)
    max_facts_total: int = Field(default_factory=lambda: settings.presentation_context_max_facts_total)
    num_ctx: int = Field(default_factory=lambda: settings.presentation_num_ctx)
    temperature: float = Field(default_factory=lambda: settings.presentation_context_temperature)
 
 
class ExtractedFact(BaseModel):
    """One fact as the model returns it (before ids and verification)."""
 
    text: str = Field(..., description="One fact that the document states, in the document's language")
    page: int | None = Field(None, description="Page number from the nearest [Page N] marker, or null")
    section: str | None = Field(None, description="Nearest heading above the fact, or null")
    evidence: str = Field(..., description="A short quote copied exactly, character for character, from the document")
 
 
class DocumentExtraction(BaseModel):
    """The model's whole answer for one document."""
 
    summary: str = Field(..., description="2 to 4 sentences about what the document is about")
    facts: list[ExtractedFact] = Field(default_factory=list)
 
 
class ContextFact(BaseModel):
    """A fact the slide writer may cite. fact_id never changes once the fact is stored."""
 
    fact_id: str = Field(..., description="doc<document_id>-f<n>; n is the position in the model's answer")
    text: str
    document_id: int
    filename: str
    page: int | None = None
    section: str | None = None
    evidence: str = ""  # verbatim quote; CTX-06 checks it against the page
 
    def as_chunk(self) -> SourceChunk:
        """The shape the slide writer already accepts."""
        return SourceChunk(
            chunk_id=self.fact_id,
            document_id=self.document_id,
            filename=self.filename,
            page=self.page,
            text=self.text,
        )
 
 
class DocumentContext(BaseModel):
    """Everything known about one document: how it was read and what was extracted."""
 
    document_id: int
    filename: str
    sha256: str | None = None  # CTX-07: a stored result is reused only if the file is unchanged
    status: DocumentStatus = "used"
    summary: str = ""
    facts: list[ContextFact] = Field(default_factory=list)
    facts_checked: int = 0  # facts the model returned and that were checked against the text (CTX-06)
    facts_dropped: int = 0  # of those, how many were not found in the text and were dropped (CTX-06)
    chars: int = 0
    warnings: list[str] = Field(default_factory=list)
 
 
class PresentationContext(BaseModel):
    """The extracted context of one presentation. Stored as JSON in presentations.context (CTX-07)."""
 
    topic: str = ""
    documents: list[DocumentContext] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)  # everything the user should see about the context
 
    @property
    def facts(self) -> list[ContextFact]:
        return [fact for document in self.documents for fact in document.facts]
 
    def document(self, document_id: int) -> DocumentContext | None:
        return next((d for d in self.documents if d.document_id == document_id), None)

