"""Prompt for writing the content of ONE slide (Task 2).

The JSON schema is added by the Ollama client, so this text only has to explain the job.
Sources are shown to the model under short ids (S1, S2 ...) so it can cite them reliably.
"""
from typing import Dict, Optional, Sequence

from app.schemas.slide_content import SourceChunk
from app.tools.chart_tool import SourceCatalog

LAYOUT_RULES: Dict[str, str] = {
    "title": (
        "Write only a one-line \"subtitle\" that says what the presentation is about. "
        "Leave \"bullets\" and \"right_bullets\" empty."
    ),
    "bullet_points": "Write 3 to 5 bullets in \"bullets\". Leave \"right_bullets\" empty.",
    "two_columns": (
        "Write 2 to 4 bullets in \"bullets\" (left column) and 2 to 4 in \"right_bullets\" (right column). "
        "The two columns should complement or contrast each other."
    ),
    "chart": (
        "Write 1 to 3 bullets in \"bullets\" that explain what the chart shows, and fill \"chart\". "
        "Choose document_id, sheet and column names ONLY from DATA FILES. "
        "Never write the numbers yourself: they are computed from the file. "
        "Example of the \"chart\" field: {\"chart_type\": \"bar\", \"title\": \"Revenue by region\", "
        "\"document_id\": 1, \"sheet\": null, \"x_column\": \"Region\", \"y_columns\": [\"Revenue\"], "
        "\"aggregation\": \"sum\"}. chart_type is bar, line or pie; aggregation is sum, mean, count or none."
    ),
    "table": (
        "Write 1 to 3 bullets in \"bullets\" that explain the table, and fill \"table\". "
        "Choose document_id, sheet and column names ONLY from DATA FILES. "
        "Never write the cell values yourself: they are read from the file. "
        "Example of the \"table\" field: {\"title\": \"Sample rows\", \"document_id\": 1, \"sheet\": null, "
        "\"columns\": [\"Region\", \"Quarter\", \"Revenue\"], \"max_rows\": 8}."
    ),
}

TEMPLATE = """You write the content of ONE slide of a presentation, using only the SOURCES below.

PRESENTATION: {presentation_title}
AUDIENCE: {audience}
STYLE: {style}
SLIDE {slide_number}: {title}
PURPOSE: {purpose}
LAYOUT: {layout}

LAYOUT RULES:
{layout_rules}

GENERAL RULES:
- Use only facts that appear in the SOURCES. Do not invent facts, names or numbers.
- For every bullet, list in "source_ids" the ids of the sources that support it (for example ["S1"]). Use only ids shown below.
- Keep each bullet short: one idea, at most 18 words.
- Write in the same language as the SOURCES.
- "speaker_notes": 2 to 4 sentences the presenter can say aloud for this slide.
- Leave every field the layout does not use empty (or null).

SOURCES:
{sources}
{data_files}{feedback}"""

NO_SOURCES = (
    "(No source text was found for this slide. Write short, cautious, general content "
    "and leave every source_ids list empty.)"
)


def render_sources(sources: Dict[str, SourceChunk]) -> str:
    if not sources:
        return NO_SOURCES
    lines = []
    for alias, chunk in sources.items():
        where = chunk.filename + (f", page {chunk.page}" if chunk.page else "")
        lines.append(f"[{alias}] ({where})\n{chunk.text.strip()}")
    return "\n\n".join(lines)


def render_data_files(catalog: Sequence[SourceCatalog]) -> str:
    if not catalog:
        return ""
    lines = ["", "DATA FILES (spreadsheets you may use; column kinds are in brackets):"]
    for source in catalog:
        lines.append(f"- document_id={source.document_id}, file \"{source.filename}\"")
        for sheet in source.sheets:
            columns = ", ".join(f"{name} ({kind})" for name, kind in sheet.columns)
            label = f"sheet \"{sheet.name}\"" if sheet.name else "(single table)"
            lines.append(f"    {label}: {columns}")
    return "\n".join(lines) + "\n"


def build_slide_prompt(
    *,
    presentation_title: str,
    audience: str,
    style: Optional[str],
    slide_number: int,
    title: str,
    purpose: str,
    layout: str,
    sources: Dict[str, SourceChunk],
    catalog: Sequence[SourceCatalog] = (),
    feedback: str = "",
) -> str:
    return TEMPLATE.format(
        presentation_title=presentation_title,
        audience=audience,
        style=style or "clear and professional",
        slide_number=slide_number,
        title=title,
        purpose=purpose,
        layout=layout,
        layout_rules=LAYOUT_RULES[layout],
        sources=render_sources(sources),
        data_files=render_data_files(catalog),
        feedback=feedback,
    )
