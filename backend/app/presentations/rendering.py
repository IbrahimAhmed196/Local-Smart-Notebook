"""Render a presentation deck using its saved options."""

from app.artifacts import manager as artifacts
from app.database.models import Presentation
from app.presentations.pptx import build_pptx
from app.presentations.schemas.slide_content import PresentationContent


def render_deck(p: Presentation, deck: PresentationContent) -> str:
    """Draw the deck into data/artifacts and return the relative path."""
    options = p.options
    relative = artifacts.presentation_file(p.notebook_id, p.id)
    build_pptx(
        deck,
        artifacts.resolve(relative),
        theme=options.get("theme", "classic"),
        rtl={"auto": None, "ltr": False, "rtl": True}[options.get("direction", "auto")],
        include_sources_slide=options.get("include_sources_slide", True),
    )
    return relative
