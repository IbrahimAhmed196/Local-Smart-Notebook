"""Presentation generation stages and the single generator factory."""
from collections.abc import Sequence
from threading import Event
from app.agents.slide_content_agent import generate_presentation_content
from app.core.config import settings
from app.database.models import Document, Notebook
from app.llm.base import LlmClient
from app.llm.cancellation import raise_if_cancelled
from app.llm.errors import LlmUnavailableError
from app.llm.ollama_client import OllamaJSONClient
from app.presentations.interfaces import DeckGenerator, GenerationSources, ProgressCallback
from app.presentations.outline import generate_outline
from app.schemas.slide_content import PresentationContent
from app.schemas.slides import PresentationOutlineResponse
from app.services import presentation_context
from app.tools.chart_tool import sources_from_documents


class LocalLlmDeckGenerator:
    def __init__(self, client: LlmClient | None = None, check_ready: bool = True):
        self.client = client if client is not None else OllamaJSONClient(
            model_name=settings.presentation_model
        )
        self.check_ready = check_ready

    def prepare(
        self, *, notebook: Notebook, options: dict,
        documents: Sequence[Document], cancel_event: Event | None = None,
    ) -> None:
        raise_if_cancelled(cancel_event)
        if self.check_ready:
            self.client.check_ready()
        raise_if_cancelled(cancel_event)

    def read_context(
        self, documents: Sequence[Document], *,
        cancel_event: Event | None = None,
    ) -> GenerationSources:
        raise_if_cancelled(cancel_event)
        sources = GenerationSources(
            chunks=presentation_context.build_chunks(documents),
            data_files=sources_from_documents(documents),
        )
        raise_if_cancelled(cancel_event)
        return sources

    def outline(
        self, options: dict, sources: GenerationSources, *,
        cancel_event: Event | None = None,
    ) -> PresentationOutlineResponse:
        raise_if_cancelled(cancel_event)
        return generate_outline(
            self.client,
            options,
            sources.chunks,
            [d.filename for d in sources.data_files],
            cancel_event=cancel_event,
        )

    def write_slides(
        self, options: dict, sources: GenerationSources,
        outline: PresentationOutlineResponse, *, progress: ProgressCallback,
        cancel_event: Event | None = None,
    ) -> PresentationContent:
        raise_if_cancelled(cancel_event)
        return generate_presentation_content(
            outline,
            chunks_for_slide=presentation_context.make_selector(sources.chunks),
            data_files=sources.data_files,
            style=options["style"],
            user_request=options["topic"],
            client=self.client,
            cancel_event=cancel_event,
            on_progress=lambda done, count: progress(f"content {done}/{count}"),
        )

    def generate(
        self, *, notebook: Notebook, options: dict,
        documents: Sequence[Document], progress: ProgressCallback,
        cancel_event: Event | None = None,
    ) -> PresentationContent:
        """Whole-deck API retained for direct callers and existing generator tests."""
        self.prepare(
            notebook=notebook, options=options, documents=documents,
            cancel_event=cancel_event,
        )
        progress("reading documents")
        sources = self.read_context(documents, cancel_event=cancel_event)
        progress("outline")
        outline = self.outline(options, sources, cancel_event=cancel_event)
        progress(f"content 0/{len(outline.slides)}")
        return self.write_slides(
            options, sources, outline,
            progress=progress, cancel_event=cancel_event,
        )


def get_generator() -> DeckGenerator:
    """Single factory override point for production callers and tests."""
    return LocalLlmDeckGenerator()


def generation_error_message(exc: Exception) -> str:
    return str(exc) if isinstance(exc, LlmUnavailableError) else f"{type(exc).__name__}: {exc}"