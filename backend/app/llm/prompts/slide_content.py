"""Prompt for writing the content of ONE slide (Task 2).

The JSON schema is added by the Ollama client, so this text only has to explain the job.
Sources are shown to the model under short ids (S1, S2 ...) so it can cite them reliably.
"""
from typing import Dict, Optional, Sequence

from app.schemas.layouts import get_layout
from app.schemas.slide_content import SourceChunk
from app.tools.chart_tool import SourceCatalog, MAX_TABLE_ROWS, MAX_TABLE_COLUMNS

# Week 6 presentation edits (ARC-06): the bullet counts below are {min} / {max} placeholders that are filled
# from the layout registry (schemas/layouts.py), so the prompt can never ask for a different number than the
# code enforces. Adding a layout needs a rule here too (tests/test_layouts.py checks it).
LAYOUT_RULES: Dict[str, str] = {
    "title": (
        "Write only a one-line \"subtitle\" that says what the presentation is about. "
        "Leave \"bullets\" and \"right_bullets\" empty."
    ),
    "bullet_points": "Write {min} to {max} bullets in \"bullets\". Leave \"right_bullets\" empty.",
    "two_columns": (
        "Write {min} to {max} bullets in \"bullets\" (left column) and {min} to {max} in \"right_bullets\" (right column). "
        "The two columns should complement or contrast each other."
    ),
    "chart": (
        'Fill "chart" using ONLY identifiers from DATA FILES. '
        '"document_id" must match a listed spreadsheet. '
        '"sheet" must exactly match one of its sheet names. '
        '"x_column" and every entry in "y_columns" must exactly match columns from that sheet. '
        'Do not add units, rename columns, or copy column names from PDF headings. '
        'Example: if DATA FILES lists "Revenue", use "y_columns": ["Revenue"], '
        'even when the PDF calls it "Revenue (EGP)". '
        'Put units in "title", for example "Revenue by region (EGP)". '
        'Never generate chart values; Python computes them from the spreadsheet. '
        'Write {min} to {max} supporting bullets in "bullets". Leave "right_bullets" empty.'
    ),
    "table": (
        'Populate the top-level "table" field with a non-null object; do not omit it. '
        'Include "document_id", "sheet", "columns", "max_rows", and "title" inside "table". '
        'Use ONLY identifiers from DATA FILES. '
        '"document_id" must match a listed spreadsheet. '
        '"sheet" must exactly match a sheet in that spreadsheet; use null for CSV files. '
        '"columns" must contain exact column names from that sheet, preserving spelling and punctuation. '
        'Document headings are descriptive text, not spreadsheet identifiers. '
        'Do not append units to column identifiers. Put supported units in the title inside "table". '
        'Choose "max_rows" according to the requested records and the supplied table limits. '
        'Never generate cell values; Python reads them from the spreadsheet. '
        'Write {min} to {max} supporting bullets in "bullets". Leave "right_bullets" empty.'
    ),
}

TEMPLATE = """You write the content of ONE slide of a presentation, using only the SOURCES below.

PRESENTATION: {presentation_title}
AUDIENCE: {audience}
STYLE: {style}
SLIDE {slide_number}: {title}
PURPOSE: {purpose}
LAYOUT: {layout}
ORIGINAL USER REQUEST:
{user_request}

LAYOUT RULES:
{layout_rules}

GENERAL RULES:
- Use only facts that appear in the SOURCES. Do not invent facts, names or numbers.
- For every bullet, list in "source_ids" the ids of the sources that support it (for example ["S1"]). Use only ids shown below.
- Keep each bullet short: one idea, at most {max_words} words.
- Write in the same language as the SOURCES.
- "speaker_notes": 2 to 4 sentences the presenter can say aloud for this slide.
- Leave every field the layout does not use empty (or null).
- For chart and table specifications, copy sheet and column names EXACTLY from DATA FILES (such as csv and xlsx).
- Never use PDF table headings as spreadsheet column names.
- Never append units, explanations, or parentheses to column identifiers.
- Put units in the chart or table title instead. 
- Use the original request to recover requirements relevant to THIS slide. Do not put every requested feature on every slide.
- If the user requested a specific chart type for this slide's subject, use that chart_type exactly: bar, line, or pie.
- For a detailed-records table, preserve every explicitly requested column.
- If the user asks for complete records without naming columns, include all columns listed for the selected sheet, up to {max_table_columns} columns.
- Preserve the requested record count in table.max_rows, up to {max_table_rows} rows.
- Keep bullets and speaker notes focused on this slide's purpose.
- Do not repeat general findings on every slide.
- Every factual statement in speaker notes must be supported by SOURCES, just like the bullets.

SOURCES:
{sources}
{data_files}

FINAL CHECK BEFORE RETURNING JSON:
For chart or table layouts, DATA FILES is the sole authority for spreadsheet identifiers.
Check every selected column against the selected sheet's listed columns.
Copy only the column name, excluding any type annotation shown in the catalog.
If your selected name is absent, replace it with the exact listed name for the intended field.
Example: "Revenue" listed as numeric means the identifier is "Revenue", not "Revenue (number)".
Never append a currency or unit to an identifier. Units belong in the display title.
If the needed field does not exist, leave the chart or table null rather than inventing a column.
Return only the requested JSON. Do not include this checklist in the output.
{feedback}"""

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
    user_request: str = "",
    slide_number: int,
    title: str,
    purpose: str,
    layout: str,
    sources: Dict[str, SourceChunk],
    catalog: Sequence[SourceCatalog] = (),
    feedback: str = "",
) -> str:
    spec = get_layout(layout)
    return TEMPLATE.format(
        presentation_title=presentation_title,
        audience=audience,
        style=style or "clear and professional",
        slide_number=slide_number,
        title=title,
        purpose=purpose,
        layout=layout,
        user_request=user_request,
        layout_rules=LAYOUT_RULES[layout].format(min=spec.min_bullets, max=spec.max_bullets),
        max_words=spec.max_words_per_bullet,
        max_table_columns=MAX_TABLE_COLUMNS,
        max_table_rows=MAX_TABLE_ROWS,
        sources=render_sources(sources),
        data_files=render_data_files(catalog),
        feedback=feedback,
    )
