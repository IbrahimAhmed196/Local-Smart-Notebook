"""Write presentation slide content, validate citations, and resolve spreadsheet data."""
import logging
from threading import Event
from typing import Callable, Dict, List, Optional, Sequence, Tuple
from app.agents.citation_validator import (
    collect_source_ids, find_invalid_source_ids, strip_invalid_source_ids,
)
from app.core.config import settings
from app.llm.ollama_client import OllamaJSONClient
from app.llm.prompts.slide_content import build_slide_prompt
from app.schemas.layouts import DATA_LAYOUTS, DEFAULT_LAYOUT, find_layout, get_layout
from app.schemas.slide_content import (
    Bullet, Citation, PresentationContent, SlideContent, SlideContentDraft, SourceChunk,
)
from app.schemas.slides import PresentationOutlineResponse, SlideOutlineItem
from app.tools.chart_tool import (
    ChartToolError, DataSource, build_chart_data, build_table_data,
    clear_sheet_cache, describe_sources,
)
from app.core.exceptions import GenerationCancelled
from app.llm.cancellation import raise_if_cancelled

log = logging.getLogger(__name__)
TEMPERATURE = settings.slide_temperature
NUM_CTX = settings.presentation_num_ctx
MAX_ATTEMPTS = settings.slide_max_attempts
MAX_SOURCES_PER_SLIDE = 6
MAX_SOURCE_CHARS = 900
ChunksForSlide = Callable[[SlideOutlineItem], Sequence[SourceChunk]]

def generate_presentation_content(
    outline: PresentationOutlineResponse,
    *,
    chunks_for_slide: Optional[ChunksForSlide] = None,
    data_files: Sequence[DataSource] = (),
    style: Optional[str] = None,
    user_request: str = "",
    client=None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    cancel_event: Event | None = None,
) -> PresentationContent:
    """Write every slide in outline order."""
    raise_if_cancelled(cancel_event)
    client = client if client is not None else OllamaJSONClient(
        model_name=settings.presentation_model
    )
    items = sorted(outline.slides, key=lambda s: s.slide_number)
    slides: List[SlideContent] = []
    clear_sheet_cache()
    try:
        for done, item in enumerate(items, start=1):
            raise_if_cancelled(cancel_event)
            chunks = chunks_for_slide(item) if chunks_for_slide else []
            slides.append(
                generate_slide_content(
                    item,
                    presentation_title=outline.presentation_title,
                    audience=outline.target_audience,
                    style=style,
                    user_request=user_request,
                    chunks=chunks,
                    data_files=data_files,
                    client=client,
                    cancel_event=cancel_event,
                )
            )
            if on_progress:
                on_progress(done, len(items))
    finally:
        clear_sheet_cache()
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
    user_request: str = "",
    chunks: Sequence[SourceChunk] = (),
    data_files: Sequence[DataSource] = (),
    client=None,
    cancel_event: Event | None = None,
) -> SlideContent:
    """Write one slide; cancellation propagates to the caller."""
    raise_if_cancelled(cancel_event)
    client = client if client is not None else OllamaJSONClient(
        model_name=settings.presentation_model
    )
    layout, warnings = _normalise_layout(item.layout_type)
    catalog = []
    if layout in DATA_LAYOUTS:
        catalog = describe_sources(data_files)
        if not catalog:
            warnings.append(
                f"No spreadsheet is available for a {layout} slide, so bullet_points was used."
            )
            layout = DEFAULT_LAYOUT

    shown = _prepare_sources(chunks)

    def prompt_with(feedback: str) -> str:
        return build_slide_prompt(
            presentation_title=presentation_title,
            audience=audience,
            style=style,
            user_request=user_request,
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
                prompt_with(feedback),
                SlideContentDraft,
                temperature=TEMPERATURE,
                num_ctx=NUM_CTX,
                cancel_event=cancel_event,
            )
        except GenerationCancelled:
            raise
        except Exception as exc:
            log.exception("Slide %s: the LLM call failed", item.slide_number)
            if draft is None:
                return _fallback_slide(item, layout, warnings, str(exc))
            break

        invalid = find_invalid_source_ids(
            draft.bullets + draft.right_bullets, shown.keys()
        )
        if not invalid:
            break
        feedback = _correction(invalid, list(shown.keys()))

    return _finish_slide(item, layout, draft, shown, data_files, warnings)

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
    limit = get_layout(layout).max_bullets
    bullets = _clean_bullets(strip_invalid_source_ids(draft.bullets, valid_ids), limit)
    right_bullets = _clean_bullets(strip_invalid_source_ids(draft.right_bullets, valid_ids), limit)
    if get_layout(layout).columns < 2:
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
    return f"Slide {item.slide_number} ('{item.title}'): {message}"

def _fallback_slide(item: SlideOutlineItem, layout: str, warnings: List[str], reason: str) -> SlideContent:
    layout = "title" if layout == "title" else DEFAULT_LAYOUT
    return SlideContent(
        slide_number=item.slide_number,
        title=item.title,
        layout_type=layout,
        bullets=[] if layout == "title" else [Bullet(text=item.purpose)],
        warnings=[_tag(item, w) for w in warnings] + [
            _tag(item, f"The model call failed after {MAX_ATTEMPTS} attempt(s), so a placeholder slide was used. Reason: {reason}")
        ],
    )

def _normalise_layout(raw: str) -> Tuple[str, List[str]]:
    spec = find_layout(raw, selectable_only=True)
    if spec is not None:
        return spec.name, []
    return DEFAULT_LAYOUT, [f"Unknown layout '{raw}', so {DEFAULT_LAYOUT} was used."]

def _prepare_sources(chunks: Sequence[SourceChunk]) -> Dict[str, SourceChunk]:
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
    return [Bullet(text=b.text, source_ids=[shown[a].chunk_id for a in b.source_ids]) for b in bullets]

def _correction(invalid: List[str], valid: List[str]) -> str:
    allowed = ", ".join(valid) if valid else "none (there are no sources, so leave every source_ids list empty)"
    return (
        f"\nCORRECTION: your previous answer cited ids that do not exist ({', '.join(invalid)}). "
        f"Cite only these ids: {allowed}. Write the whole answer again."
    )