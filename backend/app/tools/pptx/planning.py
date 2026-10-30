from dataclasses import dataclass
from app.schemas.layouts import DEFAULT_LAYOUT, find_layout
from app.schemas.slide_content import PresentationContent, SlideContent
from .constants import LABELS, MAX_TABLE_ROWS_PER_SLIDE
from .sources import _footer_text, _sources_lines


@dataclass
class Planned:
    """One slide as it will be drawn: the content, the layout actually used, the footer."""
 
    slide: SlideContent
    kind: str  # title | bullet_points | two_columns | chart | table | closing | sources
    footer: str = ""


def _layout_of(slide: SlideContent) -> str:
    spec = find_layout(slide.layout_type)
    if spec is None:
        return DEFAULT_LAYOUT  # the contract: an unknown layout is a bullet slide
    if any(getattr(slide, field) is None for field in spec.required):
        return DEFAULT_LAYOUT  # e.g. a chart slide without its chart data
    return spec.name


def plan_slides(
    deck: PresentationContent, include_sources_slide: bool = True, lang: str = "en"
) -> list[Planned]:
    """Decide the slides to draw: make sure there is a title slide, give the last text
    slide the 'closing' look, split long tables, and add a Sources slide at the end."""
    slides = sorted(deck.slides, key=lambda s: s.slide_number)
    if not slides or _layout_of(slides[0]) != "title":
        slides.insert(
            0,
            SlideContent(
                slide_number=0,
                title=deck.presentation_title,
                layout_type="title",
                subtitle=f"{LABELS[lang]['audience']} {deck.target_audience}",
            ),
        )
 
    planned: list[Planned] = []
    for index, s in enumerate(slides):
        layout = _layout_of(s)
        if layout == "bullet_points" and index == len(slides) - 1 and index > 0:
            layout = "closing"  # the last text slide is the conclusion
        if layout == "table" and len(s.table.rows) > MAX_TABLE_ROWS_PER_SLIDE:
            rows = s.table.rows
            for i in range(0, len(rows), MAX_TABLE_ROWS_PER_SLIDE):
                part = s.table.model_copy(
                    update={"rows": rows[i : i + MAX_TABLE_ROWS_PER_SLIDE]}
                )
                title = s.title if i == 0 else f"{s.title} {LABELS[lang]['cont']}"
                piece = s.model_copy(
                    update={
                        "table": part,
                        "title": title,
                        "bullets": s.bullets if i == 0 else [],
                        "speaker_notes": s.speaker_notes if i == 0 else "",
                    }
                )
                planned.append(Planned(piece, "table", _footer_text(piece, lang)))
        else:
            planned.append(Planned(s, layout, _footer_text(s, lang)))
 
    lines = _sources_lines(slides, lang)
    for slide in slides:
        for data in (slide.chart, slide.table):
            if data is not None and data.source:
                source = data.source.strip()
                if source and source not in lines:
                    lines.append(source)
    if include_sources_slide and lines:
        sources = SlideContent(
            slide_number=999,
            title=LABELS[lang]["sources"],
            layout_type="bullet_points",
            bullets=[{"text": line, "source_ids": []} for line in lines],
        )
        planned.append(Planned(sources, "sources"))
    return planned
