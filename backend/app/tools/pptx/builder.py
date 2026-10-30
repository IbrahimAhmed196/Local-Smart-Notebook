from pathlib import Path
from pptx import Presentation
from pptx.util import Inches
from app.schemas.slide_content import PresentationContent
from app.tools.pptx_themes import Theme, get_theme
from .constants import SLIDE_W, SLIDE_H
from .language import detect_language, detect_rtl
from .planning import plan_slides
from .layouts import _RENDERERS


def build_pptx(
    deck: PresentationContent,
    out_path: str | Path,
    theme: str | Theme = "classic",
    rtl: bool | None = None,
    include_sources_slide: bool = True,
) -> Path:
    """Render `deck` to `out_path` (a .pptx file) and return the path.
 
    rtl=None means "decide from the text": Arabic or Hebrew decks are mirrored.
    """
    th = get_theme(theme) if isinstance(theme, str) else theme
    rtl = detect_rtl(deck) if rtl is None else rtl
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(SLIDE_W), Inches(SLIDE_H)
    prs.core_properties.title = deck.presentation_title
    lang = detect_language(deck)
    for number, planned in enumerate(
        plan_slides(deck, include_sources_slide, lang), start=1
    ):
        _RENDERERS[planned.kind](prs, planned, th, rtl, number)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(out_path)
    return out_path
