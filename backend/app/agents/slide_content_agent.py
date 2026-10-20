"""Task 2: writes the content of every slide, one slide at a time (Stage 2).

Input : the outline from Task 1 (title, purpose and layout per slide) and, for each slide,
        the source chunks it may use plus the notebook's spreadsheets.
Output: PresentationContent, a validated slide JSON that Task 3 renders into a .pptx.

What the LLM does : writes bullets, a subtitle and speaker notes, cites sources by id,
                    and NAMES the sheet and columns for a chart or table.
What the code does: checks every cited id, computes every chart / table value with pandas
                    from the real file, trims the lists and repairs or drops anything invalid.
"""
import logging
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from app.agents.citation_validator import (
    collect_source_ids,
    find_invalid_source_ids,
    strip_invalid_source_ids,
)
from app.llm.ollama_client import OllamaJSONClient
from app.llm.prompts.slide_content import build_slide_prompt
from app.schemas.slide_content import (
    DEFAULT_LAYOUT,
    SLIDE_LAYOUTS,
    Bullet,
    Citation,
    PresentationContent,
    SlideContent,
    SlideContentDraft,
    SourceChunk,
)
from app.schemas.slides import PresentationOutlineResponse, SlideOutlineItem
from app.tools.chart_tool import (
    ChartToolError,
    DataSource,
    build_chart_data,
    build_table_data,
    describe_sources,
)

log = logging.getLogger(__name__)

TEMPERATURE = 0.1  # low: slides must follow the sources, not be creative
NUM_CTX = 8192  # Ollama's default window is small; sources + schema + instructions need more
MAX_ATTEMPTS = 2  # one retry when the model cites ids that do not exist
MAX_SOURCES_PER_SLIDE = 6
MAX_SOURCE_CHARS = 900
MAX_BULLETS = {"title": 0, "bullet_points": 6, "two_columns": 4, "chart": 3, "table": 3}  # per column
DATA_LAYOUTS = ("chart", "table")
LAYOUT_ALIASES = {
    "bullets": "bullet_points",
    "bullet_point": "bullet_points",
    "bullet": "bullet_points",
    "two_column": "two_columns",
    "two_cols": "two_columns",
}

ChunksForSlide = Callable[[SlideOutlineItem], Sequence[SourceChunk]]


def generate_presentation_content(
    outline: PresentationOutlineResponse,
    *,
    chunks_for_slide: Optional[ChunksForSlide] = None,
    data_files: Sequence[DataSource] = (),
    style: Optional[str] = None,
    client=None,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> PresentationContent:
    """Write every slide of the outline, one LLM call per slide, in slide order."""
    client = client or OllamaJSONClient()
    items = sorted(outline.slides, key=lambda s: s.slide_number)
    slides: List[SlideContent] = []
    for done, item in enumerate(items, start=1):
        chunks = chunks_for_slide(item) if chunks_for_slide else []
        slides.append(
            generate_slide_content(
                item,
                presentation_title=outline.presentation_title,
                audience=outline.target_audience,
                style=style,
                chunks=chunks,
                data_files=data_files,
                client=client,
            )
        )
        if on_progress:
            on_progress(done, len(items))
    return PresentationContent(
        presentation_title=outline.presentation_title,
        target_audience=outline.target_audience,
        slides=slides,
    )


def generate_slide_content(
    item: SlideOutlineItem,
    *,
    presentation_title: str,
    audience: str,
    style: Optional[str] = None,
    chunks: Sequence[SourceChunk] = (),
    data_files: Sequence[DataSource] = (),
    client=None,
) -> SlideContent:
    """Content for ONE slide. Never raises because of the LLM: a failed slide gets a placeholder."""
    client = client or OllamaJSONClient()
    layout, warnings = _normalise_layout(item.layout_type)

    catalog = []
    if layout in DATA_LAYOUTS:
        catalog = describe_sources(data_files)
        if not catalog:
            warnings.append(f"No spreadsheet is available for a {layout} slide, so bullet_points was used.")
            layout = DEFAULT_LAYOUT

    shown = _prepare_sources(chunks)  # {"S1": chunk, "S2": chunk ...}: the only ids that may be cited

    def prompt_with(feedback: str) -> str:
        return build_slide_prompt(
            presentation_title=presentation_title,
            audience=audience,
            style=style,
            slide_number=item.slide_number,
            title=item.title,
            purpose=item.purpose,
            layout=layout,
            sources=shown,
            catalog=catalog,
            feedback=feedback,
        )

    draft: Optional[SlideContentDraft] = None
    feedback = ""
    for _ in range(MAX_ATTEMPTS):
        try:
            draft = client.generate_json(
                prompt_with(feedback), SlideContentDraft, temperature=TEMPERATURE, num_ctx=NUM_CTX
            )
        except Exception as exc:  # the client raises RuntimeError when it gets no valid JSON
            log.exception("Slide %s: the LLM call failed", item.slide_number)
            if draft is None:
                return _fallback_slide(item, layout, warnings, str(exc))
            break  # keep the draft from the first attempt
        invalid = find_invalid_source_ids(draft.bullets + draft.right_bullets, shown.keys())
        if not invalid:
            break
        feedback = _correction(invalid, list(shown.keys()))

    return _finish_slide(item, layout, draft, shown, data_files, warnings)


# ---------------------------------------------------------------------------
# checking and finishing the LLM's draft (all deterministic)
# ---------------------------------------------------------------------------

def _finish_slide(
    item: SlideOutlineItem,
    layout: str,
    draft: SlideContentDraft,
    shown: Dict[str, SourceChunk],
    data_files: Sequence[DataSource],
    warnings: List[str],
) -> SlideContent:
    warnings = list(warnings)
    valid_ids = list(shown.keys())

    invalid = find_invalid_source_ids(draft.bullets + draft.right_bullets, valid_ids)
    if invalid:
        warnings.append("Removed source ids that were not supplied for this slide: " + ", ".join(invalid))

    limit = MAX_BULLETS[layout]
    bullets = _clean_bullets(strip_invalid_source_ids(draft.bullets, valid_ids), limit)
    right_bullets = _clean_bullets(strip_invalid_source_ids(draft.right_bullets, valid_ids), limit)
    if layout != "two_columns":
        right_bullets = []

    chart = table = None
    problem = None
    if layout == "chart":
        if draft.chart is None:
            problem = "The model did not choose any data for the chart."
        else:
            try:
                chart = build_chart_data(draft.chart, data_files)
            except ChartToolError as exc:
                problem = f"Chart dropped: {exc}"
    elif layout == "table":
        if draft.table is None:
            problem = "The model did not choose any data for the table."
        else:
            try:
                table = build_table_data(draft.table, data_files)
            except ChartToolError as exc:
                problem = f"Table dropped: {exc}"
    if problem:
        warnings.append(problem)
        layout = DEFAULT_LAYOUT
        if not bullets:
            bullets = [Bullet(text=item.purpose)]

    if shown:
        uncited = sum(1 for b in bullets + right_bullets if not b.source_ids)
        if uncited:
            warnings.append(f"{uncited} bullet(s) have no citation.")

    citations = [
        Citation(source_id=chunk.chunk_id, document_id=chunk.document_id, filename=chunk.filename, page=chunk.page)
        for chunk in (shown[alias] for alias in collect_source_ids(bullets + right_bullets))
    ]
    return SlideContent(
        slide_number=item.slide_number,
        title=item.title,
        layout_type=layout,
        subtitle=(draft.subtitle or "").strip() or None,
        bullets=_real_ids(bullets, shown),
        right_bullets=_real_ids(right_bullets, shown),
        speaker_notes=draft.speaker_notes.strip(),
        chart=chart,
        table=table,
        citations=citations,
        warnings=[_tag(item, w) for w in warnings],
    )


def _tag(item: SlideOutlineItem, message: str) -> str:
    """Prefix a warning with the slide it belongs to, so a deck-level log is readable."""
    return f"Slide {item.slide_number} ('{item.title}'): {message}"


def _fallback_slide(item: SlideOutlineItem, layout: str, warnings: List[str], reason: str) -> SlideContent:
    """A minimal valid slide, so one failed LLM call does not lose the whole deck."""
    layout = "title" if layout == "title" else DEFAULT_LAYOUT
    return SlideContent(
        slide_number=item.slide_number,
        title=item.title,
        layout_type=layout,
        bullets=[] if layout == "title" else [Bullet(text=item.purpose)],
        warnings=[_tag(item, w) for w in warnings]
        + [_tag(item, f"The model call failed after {MAX_ATTEMPTS} attempt(s), so a placeholder slide was used. Reason: {reason}")],
    )


def _normalise_layout(raw: str) -> Tuple[str, List[str]]:
    layout = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    layout = LAYOUT_ALIASES.get(layout, layout)
    if layout in SLIDE_LAYOUTS:
        return layout, []
    return DEFAULT_LAYOUT, [f"Unknown layout '{raw}', so {DEFAULT_LAYOUT} was used."]


def _prepare_sources(chunks: Sequence[SourceChunk]) -> Dict[str, SourceChunk]:
    """Give the chunks short ids (S1, S2 ...): a 7B model copies these far more reliably than real ids."""
    shown: Dict[str, SourceChunk] = {}
    for number, chunk in enumerate(list(chunks)[:MAX_SOURCES_PER_SLIDE], start=1):
        shown[f"S{number}"] = chunk.model_copy(update={"text": chunk.text[:MAX_SOURCE_CHARS]})
    return shown


def _clean_bullets(bullets: Sequence[Bullet], limit: int) -> List[Bullet]:
    cleaned = []
    for bullet in bullets:
        text = bullet.text.strip().lstrip("•").strip()
        if text:
            cleaned.append(Bullet(text=text, source_ids=bullet.source_ids))
    return cleaned[:limit]


def _real_ids(bullets: Sequence[Bullet], shown: Dict[str, SourceChunk]) -> List[Bullet]:
    """Swap the short ids back for the real chunk ids, so the JSON points at real chunks."""
    return [Bullet(text=b.text, source_ids=[shown[a].chunk_id for a in b.source_ids]) for b in bullets]


def _correction(invalid: List[str], valid: List[str]) -> str:
    allowed = ", ".join(valid) if valid else "none (there are no sources, so leave every source_ids list empty)"
    return (
        f"\nCORRECTION: your previous answer cited ids that do not exist ({', '.join(invalid)}). "
        f"Cite only these ids: {allowed}. Write the whole answer again."
    )
