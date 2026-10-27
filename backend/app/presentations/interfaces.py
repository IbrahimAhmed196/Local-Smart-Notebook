"""Contracts between presentation pipeline components.

These contracts are adopted incrementally after ARC-01.
Type-only imports avoid loading database and spreadsheet dependencies
when this module is imported.
"""

from __future__ import annotations
from threading import Event
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Protocol
from dataclasses import dataclass

if TYPE_CHECKING:
    from app.database.models import Document, Notebook
    from app.llm.base import LlmClient
    from app.presentations.context.schemas import (
        ContextOptions,
        PresentationContext,
    )
    from app.schemas.slide_content import PresentationContent, SourceChunk
    from app.schemas.slides import (
        PresentationOutlineResponse,
        SlideOutlineItem,
    )
    from app.tools.chart_tool import DataSource


# Preserve today's progress format until JOB-02 introduces its replacement.
ProgressCallback = Callable[[str], None]


class ContextProvider(Protocol):
    """Build context and select the evidence available to each slide.

    Context is passed explicitly so selection can also work with context
    restored from storage.
    """

    def build(
        self,
        documents: Sequence[Document],
        topic: str,
        options: ContextOptions | None = None,
        *,
        progress: ProgressCallback | None = None,
    ) -> PresentationContext:
        ...

    def for_slide(
        self,
        context: PresentationContext,
        item: SlideOutlineItem,
    ) -> list[SourceChunk]:
        ...


class OutlineGenerator(Protocol):
    """Generate an outline using the current outline-generation inputs.

    OUT-05 will replace chunks/data_names with context/data_catalog and
    update implementations and callers in the same change.
    """

    def __call__(
        self,
        client: LlmClient,
        options: dict,
        chunks: Sequence[SourceChunk],
        data_names: Sequence[str],
        *,
        cancel_event: Event | None = None,
    ) -> PresentationOutlineResponse:
        ...


class SlideWriter(Protocol):
    """Callable interface for generate_presentation_content."""

    def __call__(
        self,
        outline: PresentationOutlineResponse,
        *,
        chunks_for_slide: (
            Callable[[SlideOutlineItem], Sequence[SourceChunk]] | None
        ) = None,
        data_files: Sequence[DataSource] = (),
        style: str | None = None,
        user_request: str = "",
        client: LlmClient | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        cancel_event: Event | None = None,
    ) -> PresentationContent:
        ...


@dataclass(frozen=True)
class GenerationSources:
    """Existing text chunks and spreadsheet inputs; no new extraction policy."""
    chunks: Sequence[SourceChunk]
    data_files: Sequence[DataSource]


class DeckGenerator(Protocol):
    """Generation stages used by the runner, plus a whole-deck convenience API."""

    def prepare(
        self, *, notebook: Notebook, options: dict,
        documents: Sequence[Document], cancel_event: Event | None = None,
    ) -> None:
        ...

    def read_context(
        self, documents: Sequence[Document], *,
        cancel_event: Event | None = None,
    ) -> GenerationSources:
        ...

    def outline(
        self, options: dict, sources: GenerationSources, *,
        cancel_event: Event | None = None,
    ) -> PresentationOutlineResponse:
        ...

    def write_slides(
        self, options: dict, sources: GenerationSources,
        outline: PresentationOutlineResponse, *, progress: ProgressCallback,
        cancel_event: Event | None = None,
    ) -> PresentationContent:
        ...

    def generate(
        self, *, notebook: Notebook, options: dict,
        documents: Sequence[Document], progress: ProgressCallback,
        cancel_event: Event | None = None,
    ) -> PresentationContent:
        ...