"""Write presentation slide content, validate citations, and resolve spreadsheet data."""
import logging
import re
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
# Week 6 presentation edits (DAT-02 / DAT-06): check_chart / check_table return issues, and the data facts come
# from the tool.
from app.tools.chart_tool import (
    DataFact, DataSource, Issue, check_chart, check_table, clear_sheet_cache,
    compute_chart_facts, compute_table_facts, describe_sources,
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

    def prompt_with(feedback: str, facts: Sequence[DataFact] = ()) -> str:
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
            facts=facts,
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

    # Week 6 presentation edits (DAT-06): the model chose the chart / table without seeing it. Now that Python can
    # build it, compute the facts and let the model write the bullets again from them (a second, short model call).
    facts: List[DataFact] = []
    if layout in DATA_LAYOUTS and settings.slide_data_facts:
        facts = _data_facts(layout, draft, data_files)
        if facts:
            raise_if_cancelled(cancel_event)
            try:
                again = client.generate_json(
                    prompt_with("", facts),
                    SlideContentDraft,
                    temperature=TEMPERATURE,
                    num_ctx=NUM_CTX,
                    cancel_event=cancel_event,
                )
            except GenerationCancelled:
                raise
            except Exception as exc:  # keep the first bullets rather than lose the slide
                log.exception("Slide %s: the LLM call with the data facts failed", item.slide_number)
                warnings.append(f"The data facts could not be used ({exc}); the first bullets were kept.")
                facts = []
            else:  # only the words change: the chart / table choice and the layout stay as they were
                draft = draft.model_copy(update={
                    "bullets": again.bullets or draft.bullets,
                    "speaker_notes": again.speaker_notes or draft.speaker_notes,
                })

    return _finish_slide(item, layout, draft, shown, data_files, warnings, facts)

def _finish_slide(
    item: SlideOutlineItem,
    layout: str,
    draft: SlideContentDraft,
    shown: Dict[str, SourceChunk],
    data_files: Sequence[DataSource],
    warnings: List[str],
    facts: Sequence[DataFact] = (),  # Week 6 presentation edits (DAT-06): the data facts the bullets may cite
) -> SlideContent:
    warnings = list(warnings)
    valid_ids = list(shown.keys()) + [fact.fact_id for fact in facts]  # DAT-06: a bullet may cite D1, D2 ...
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
            result = check_chart(draft.chart, data_files)  # DAT-02: a list of issues, not only an exception
            if result.ok:
                chart = result.data
                warnings.extend(_issue_text(issue) for issue in result.warnings)
            else:
                problem = f"Chart dropped: {_issue_text(result.errors[0])}"
    elif layout == "table":
        if draft.table is None:
            problem = "The model did not choose any data for the table."
        else:
            result = check_table(draft.table, data_files)
            if result.ok:
                table = result.data
                warnings.extend(_issue_text(issue) for issue in result.warnings)
            else:
                problem = f"Table dropped: {_issue_text(result.errors[0])}"
    if problem:
        warnings.append(problem)
        layout = DEFAULT_LAYOUT
        facts = []  # no chart or table, so there is nothing for a fact to describe ...
        bullets = strip_invalid_source_ids(bullets, shown.keys())  # ... and no bullet may cite one
        right_bullets = strip_invalid_source_ids(right_bullets, shown.keys())
        if not bullets:
            bullets = [Bullet(text=item.purpose)]
    if shown:
        uncited = sum(1 for b in bullets + right_bullets if not b.source_ids)
        if uncited:
            warnings.append(f"{uncited} bullet(s) have no citation.")

    facts_by_id = {fact.fact_id: fact for fact in facts}
    warnings.extend(_numbers_not_in_facts(bullets + right_bullets, shown, facts_by_id))
    data = chart or table
    citations = []
    for alias in collect_source_ids(bullets + right_bullets):
        if alias in facts_by_id:  # DAT-06: a data fact is cited like a source; its text travels with the citation
            fact = facts_by_id[alias]
            citations.append(Citation(
                source_id=_fact_real_id(item, fact), document_id=_data_document_id(draft, chart),
                filename=data.source, text=fact.text,
            ))
        else:
            chunk = shown[alias]
            citations.append(Citation(
                source_id=chunk.chunk_id, document_id=chunk.document_id, filename=chunk.filename, page=chunk.page,
            ))
    real_ids = {alias: chunk.chunk_id for alias, chunk in shown.items()}
    real_ids.update({fact.fact_id: _fact_real_id(item, fact) for fact in facts})
    return SlideContent(
        slide_number=item.slide_number,
        title=item.title,
        layout_type=layout,
        subtitle=(draft.subtitle or "").strip() or None,
        bullets=_real_ids(bullets, real_ids),
        right_bullets=_real_ids(right_bullets, real_ids),
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

def _real_ids(bullets: Sequence[Bullet], real_ids: Dict[str, str]) -> List[Bullet]:
    """Swap the short ids (S1, D1 ...) back for the real ids, so the JSON points at real chunks and facts."""
    return [Bullet(text=b.text, source_ids=[real_ids[a] for a in b.source_ids]) for b in bullets]


# Week 6 presentation edits (DAT-02): a chart / table issue becomes the text of a slide warning.
def _issue_text(issue: Issue) -> str:
    return f"{issue.message} {issue.hint}".strip()


# Week 6 presentation edits (DAT-06): facts about the chart / table the model just chose.
def _data_facts(layout: str, draft: SlideContentDraft, data_files: Sequence[DataSource]) -> List[DataFact]:
    if layout == "chart" and draft.chart is not None:
        result = check_chart(draft.chart, data_files)
        return compute_chart_facts(result.data, draft.chart.aggregation) if result.ok else []
    if layout == "table" and draft.table is not None:
        result = check_table(draft.table, data_files)
        return compute_table_facts(result.data) if result.ok else []
    return []


def _fact_real_id(item: SlideOutlineItem, fact: DataFact) -> str:
    """Ids D1, D2 ... repeat on every slide, so the real id says which slide the fact belongs to: 's4-D2'."""
    return f"s{item.slide_number}-{fact.fact_id}"


def _data_document_id(draft: SlideContentDraft, chart) -> int:
    """The spreadsheet of the chart or table that was built (a model may fill both specs)."""
    return (draft.chart if chart is not None else draft.table).document_id


def _numbers(text: str) -> set:
    return {round(float(found.replace(",", "")), 2) for found in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def _numbers_not_in_facts(
    bullets: Sequence[Bullet], shown: Dict[str, SourceChunk], facts_by_id: Dict[str, DataFact]
) -> List[str]:
    """Warnings for a bullet that cites a data fact but quotes a number that is in none of its cited sources."""
    found: List[str] = []
    for bullet in bullets:
        if not any(a in facts_by_id for a in bullet.source_ids):
            continue
        allowed = set()
        for alias in bullet.source_ids:
            allowed |= _numbers(facts_by_id[alias].text if alias in facts_by_id else shown[alias].text)
        extra = sorted(_numbers(bullet.text) - allowed)
        if extra:
            numbers = ", ".join(f"{number:g}" for number in extra)
            found.append(f'A bullet quotes numbers that are not in its data facts ({numbers}): "{bullet.text[:60]}"')
    return found

def _correction(invalid: List[str], valid: List[str]) -> str:
    allowed = ", ".join(valid) if valid else "none (there are no sources, so leave every source_ids list empty)"
    return (
        f"\nCORRECTION: your previous answer cited ids that do not exist ({', '.join(invalid)}). "
        f"Cite only these ids: {allowed}. Write the whole answer again."
    )