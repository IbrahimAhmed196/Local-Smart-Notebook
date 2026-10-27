"""Presentation outline generation and deterministic repairs."""

from collections.abc import Sequence

from app.core.config import settings
from app.llm.base import LlmClient
from app.llm.prompts.outline import OUTLINE_PROMPT
# Week 6 presentation edits (ARC-06): which layouts need a spreadsheet comes from the layout registry.
from app.schemas.layouts import DATA_LAYOUTS, SLIDE_LAYOUTS
from app.schemas.slide_content import SourceChunk
from app.schemas.slides import PresentationOutlineResponse


def generate_outline(
    client: LlmClient,
    options: dict,
    chunks: Sequence[SourceChunk],
    data_names: Sequence[str],
) -> PresentationOutlineResponse:
    """Generate an outline and apply the existing deterministic repairs."""
    layouts = [
        layout
        for layout in SLIDE_LAYOUTS
        if data_names or layout not in DATA_LAYOUTS
    ]

    if data_names:
        data_note = (
            f"- Use chart or table only to show numbers from: "
            f"{', '.join(data_names)}."
        )
    else:
        data_note = "- There are no spreadsheets, so do not use chart or table."

    excerpts = (
        "\n".join(
            f"- ({chunk.filename}"
            f"{f', page {chunk.page}' if chunk.page else ''}) "
            f"{chunk.text[:300]}"
            for chunk in chunks[:6]
        )
        or "(No document text was found. Use the topic only.)"
    )

    prompt = OUTLINE_PROMPT.format(
        topic=options["topic"],
        count=_outline_slide_count(options),
        audience=options["audience"],
        style=options["style"],
        layouts=", ".join(layouts),
        data_note=data_note,
        excerpts=excerpts,
    )

    outline = client.generate_json(
        prompt,
        PresentationOutlineResponse,
        # Week 6 presentation edits (ARC-07): both values come from core/config.py (.env).
        temperature=settings.outline_temperature,
        num_ctx=settings.presentation_num_ctx,
    )

    return clean_outline(
        outline,
        options,
        has_data=bool(data_names),
    )


def clean_outline(
    outline: PresentationOutlineResponse,
    options: dict,
    has_data: bool,
) -> PresentationOutlineResponse:
    """Repair slide count, numbering, title and spreadsheet-only layouts."""
    expected = _outline_slide_count(options)

    slides = sorted(
        outline.slides,
        key=lambda slide: slide.slide_number,
    )[:expected]

    if not slides:
        raise ValueError("The model returned an outline without any slides.")

    if len(slides) != expected:
        raise ValueError(
            f"Expected {expected} outline slides, received {len(slides)}."
        )

    fixed = []

    for number, slide in enumerate(slides, start=1):
        layout = (
            (slide.layout_type or "")
            .strip()
            .lower()
            .replace(" ", "_")
        )

        if number == 1:
            layout = "title"
        elif layout in DATA_LAYOUTS and not has_data:
            layout = "bullet_points"

        updates = {
            "slide_number": number,
            "layout_type": layout,
        }

        if number == 1:
            updates["title"] = (
                options.get("title") or outline.presentation_title
            )

        fixed.append(slide.model_copy(update=updates))

    return PresentationOutlineResponse(
        presentation_title=(
            options.get("title") or outline.presentation_title
        ),
        target_audience=(
            outline.target_audience or options["audience"]
        ),
        slides=fixed,
    )


def _outline_slide_count(options: dict) -> int:
    """Reserve one slide for Sources when that option is enabled."""
    total = int(options["num_slides"])
    reserved = 1 if options.get("include_sources_slide", True) else 0
    count = total - reserved

    if count < 2:
        raise ValueError(
            "Allow at least two content slides plus the optional Sources slide."
        )

    return count