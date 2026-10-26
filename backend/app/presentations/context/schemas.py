"""Context placeholders; CTX-01 defines the complete schemas."""

from pydantic import BaseModel, Field


class ContextOptions(BaseModel):
    """Context settings; fields will be defined in CTX-01 and CTX-03."""


class PresentationContext(BaseModel):
    """Extracted context; CTX-01 will add facts, summaries and provenance."""

    warnings: list[str] = Field(default_factory=list)