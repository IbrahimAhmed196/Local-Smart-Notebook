"""Presentation generation stages and the single generator factory."""

from collections.abc import Callable, Sequence
from threading import Event

from app.core.config import settings
from app.database.models import Document, Notebook
from app.llm.base import LlmClient
from app.llm.cancellation import raise_if_cancelled
from app.llm.errors import LlmUnavailableError
from app.llm.ollama_client import OllamaJSONClient
from app.presentations.context.errors import ContextError
from app.presentations.context.llm_provider import LlmContextProvider
from app.presentations.context.schemas import ContextOptions, PresentationContext
from app.presentations.context.selection import overview_chunks
from app.presentations.data import describe_sources, sources_from_documents
from app.presentations.interfaces import ContextProvider, DeckGenerator, GenerationSources, ProgressCallback
from app.presentations.outline import generate_outline
from app.presentations.schemas.outline import PresentationOutlineResponse, SlideOutlineItem
from app.presentations.schemas.slide_content import PresentationContent, SourceChunk
from app.presentations.slide_content_agent import generate_presentation_content


class LocalLlmDeckGenerator:
    def __init__(
        self,
        client: LlmClient | None = None,
        check_ready: bool = True,
        context_provider: ContextProvider | None = None,
    ):
        self.client = client if client is not None else OllamaJSONClient(model_name=settings.presentation_model)
        self.check_ready = check_ready
        # The one place that chooses the context implementation; RAG-01 swaps it here.
        self.context_provider = context_provider or LlmContextProvider(self.client)


    def prepare(
        self,
        *,
        notebook: Notebook,
        options: dict,
        documents: Sequence[Document],
        cancel_event: Event | None = None,
    ) -> None:
        raise_if_cancelled(cancel_event)
        if self.check_ready:
            self.client.check_ready()
        raise_if_cancelled(cancel_event)

    def read_context(
        self,
        documents: Sequence[Document],
        *,
        options: dict | None = None,
        progress: ProgressCallback | None = None,
        cancel_event: Event | None = None,
        previous: PresentationContext | None = None,
        on_document=None,
    ) -> GenerationSources:
        raise_if_cancelled(cancel_event)
        options = options or {}
        context = self.context_provider.build(
            documents,
            options.get("topic", ""),
            ContextOptions(audience=options.get("audience") or "general audience", model_name=self.client.model_name),
            progress=progress,
            cancel_event=cancel_event,
            previous=previous,
            on_document=on_document,
        )
        sources = GenerationSources(context=context, data_files=sources_from_documents(documents))
        raise_if_cancelled(cancel_event)
        return sources


    def outline(
        self,
        options: dict,
        sources: GenerationSources,
        *,
        cancel_event: Event | None = None,
    ) -> PresentationOutlineResponse:
        raise_if_cancelled(cancel_event)
        return generate_outline(
            self.client,
            options,
            overview_chunks(sources.context),
            [d.filename for d in sources.data_files],
            # Week 6 presentation edits (DAT-05): the outline also gets the description of the spreadsheets.
            catalog=describe_sources(sources.data_files),
            cancel_event=cancel_event,
        )

    def write_slides(
        self,
        options: dict,
        sources: GenerationSources,
        outline: PresentationOutlineResponse,
        *,
        progress: ProgressCallback,
        cancel_event: Event | None = None,
    ) -> PresentationContent:
        raise_if_cancelled(cancel_event)
        return generate_presentation_content(
            outline,
            chunks_for_slide=chunks_for_slide(self.context_provider, sources.context),
            data_files=sources.data_files,
            style=options["style"],
            user_request=options["topic"],
            client=self.client,
            cancel_event=cancel_event,
            on_progress=lambda done, count: progress(f"content {done}/{count}"),
        )

    def generate(
        self,
        *,
        notebook: Notebook,
        options: dict,
        documents: Sequence[Document],
        progress: ProgressCallback,
        cancel_event: Event | None = None,
    ) -> PresentationContent:
        """Whole-deck API retained for direct callers and existing generator tests."""
        self.prepare(
            notebook=notebook,
            options=options,
            documents=documents,
            cancel_event=cancel_event,
        )
        progress("reading documents")
        sources = self.read_context(documents, options=options, progress=progress, cancel_event=cancel_event)       
        progress("outline")
        outline = self.outline(options, sources, cancel_event=cancel_event)
        progress(f"content 0/{len(outline.slides)}")
        return self.write_slides(
            options,
            sources,
            outline,
            progress=progress,
            cancel_event=cancel_event,
        )


def chunks_for_slide(
    provider: ContextProvider, context: PresentationContext
) -> Callable[[SlideOutlineItem], Sequence[SourceChunk]]:
    """Adapts for_slide(context, item) to the chunks_for_slide(item) callable that the slide writer accepts."""
    return lambda item: provider.for_slide(context, item)
 
 
def get_generator() -> DeckGenerator:
    """Single factory override point for production callers and tests."""
    return LocalLlmDeckGenerator()


def generation_error_message(exc: Exception) -> str:
    return str(exc) if isinstance(exc, (LlmUnavailableError, ContextError)) else f"{type(exc).__name__}: {exc}"
