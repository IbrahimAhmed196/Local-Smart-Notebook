"""Fixtures that only the presentation tests use (the shared ones stay in tests/conftest.py)."""

import pytest

from app.presentations import generator as deck_generation


@pytest.fixture()
def sample_deck():
    """Load the existing sample containing all five public layouts."""
    from pathlib import Path

    from app.presentations.schemas.slide_content import PresentationContent

    path = Path(__file__).resolve().parents[2] / "docs" / "samples" / "sample_deck.json"
    return PresentationContent.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.fixture()
def fake_generator(monkeypatch, sample_deck):
    """Replace generation stages while keeping the real runner and renderer."""
    from app.presentations.context.schemas import PresentationContext
    from app.presentations.interfaces import GenerationSources
    from app.presentations.schemas.outline import PresentationOutlineResponse, SlideOutlineItem

    class FakeDeckGenerator:
        def __init__(self):
            self.calls = []
            self.stages = []
            self.error = None
            self.error_stage = "outline"

        def _enter(self, stage):
            self.stages.append(stage)
            if self.error is not None and self.error_stage == stage:
                raise self.error

        def prepare(self, *, notebook, options, documents, cancel_event=None):
            self.calls.append(
                {
                    "notebook_id": notebook.id,
                    "options": options,
                    "document_ids": [document.id for document in documents],
                }
            )
            self._enter("prepare")

        def read_context(
            self, documents, *, options=None, progress=None, cancel_event=None, previous=None, on_document=None
        ):
            self._enter("read_context")
            return GenerationSources(context=PresentationContext(), data_files=[])


        def outline(self, options, sources, *, cancel_event=None):
            self._enter("outline")
            return PresentationOutlineResponse(
                presentation_title=sample_deck.presentation_title,
                target_audience=sample_deck.target_audience,
                slides=[
                    SlideOutlineItem(
                        slide_number=i,
                        title=slide.title,
                        purpose="Test slide",
                        layout_type=slide.layout_type,
                    )
                    for i, slide in enumerate(sample_deck.slides, start=1)
                ],
            )

        def write_slides(self, options, sources, outline, *, progress, cancel_event=None):
            self._enter("write_slides")
            count = len(sample_deck.slides)
            progress(f"content {count}/{count}")
            return sample_deck.model_copy(deep=True)

        def generate(self, *, notebook, options, documents, progress, cancel_event=None):
            self.prepare(
                notebook=notebook,
                options=options,
                documents=documents,
                cancel_event=cancel_event,
            )
            progress("reading documents")
            sources = self.read_context(documents, cancel_event=cancel_event)
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

    generator = FakeDeckGenerator()
    monkeypatch.setattr(deck_generation, "get_generator", lambda: generator)
    return generator

@pytest.fixture
def use_files(monkeypatch):
    """Let the context readers open the real path stored in a fake Document (no storage folder, no database)."""
    from pathlib import Path
 
    from app.presentations.context import readers
 
    monkeypatch.setattr(readers.document_service, "get_file_path", lambda doc: Path(doc.file_path))

