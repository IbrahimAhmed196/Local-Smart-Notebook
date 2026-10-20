"""Task 2: slide content schemas (what the LLM writes + the finished, renderable slide JSON).

Kept in its own file so Task 1's schemas/slides.py stays untouched.
"""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

# The layouts the slide writer (Task 2) and the renderer (Task 3) both understand.
SLIDE_LAYOUTS = ("title", "bullet_points", "two_columns", "chart", "table")
DEFAULT_LAYOUT = "bullet_points"


# A 7B model often gets small things wrong (a string where a list is expected, "average" for "mean").
# These helpers fix the harmless ones so a whole slide is not thrown away because of them.
_CHART_TYPES = {"bar": "bar", "column": "bar", "columns": "bar", "bar chart": "bar", "histogram": "bar",
                "line": "line", "line chart": "line", "trend": "line", "pie": "pie", "pie chart": "pie",
                "donut": "pie", "doughnut": "pie"}
_AGGREGATIONS = {"sum": "sum", "total": "sum", "add": "sum", "mean": "mean", "average": "mean", "avg": "mean",
                 "count": "count", "none": "none", "": "sum"}


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


def _no_sheet(value):
    if isinstance(value, str) and value.strip().lower() in ("", "none", "null", "n/a", "-"):
        return None
    return value


def _as_int(value):
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    if isinstance(value, float) and value == int(value):
        return int(value)
    return value


class SourceChunk(BaseModel):
    """A piece of a document that is given to the LLM as evidence for ONE slide."""
    chunk_id: str = Field(..., description="Unique id of the chunk (from the retrieval side)")
    document_id: int
    filename: str
    text: str
    page: Optional[int] = None


class Citation(BaseModel):
    """Where a slide's facts come from (always one of the chunks given for that slide)."""
    source_id: str
    document_id: int
    filename: str
    page: Optional[int] = None


class Bullet(BaseModel):
    text: str = Field(..., description="One short bullet point")
    source_ids: List[str] = Field(
        default_factory=list,
        description="Ids of the sources that support this bullet, taken only from the SOURCES list",
    )

    @field_validator("source_ids", mode="before")
    @classmethod
    def _ids_as_list(cls, value):
        return _as_list(value)


class ChartSpec(BaseModel):
    """The LLM only NAMES the data. The numbers are computed by code from the real file."""
    chart_type: Literal["bar", "line", "pie"] = "bar"
    title: str = ""
    document_id: int = Field(..., description="document_id of a spreadsheet from DATA FILES")
    sheet: Optional[str] = Field(None, description="Sheet name (leave empty for a CSV file)")
    x_column: str = Field(..., description="Column used for the categories / x axis")
    y_columns: List[str] = Field(..., description="Numeric column(s) to plot")
    aggregation: Literal["sum", "mean", "count", "none"] = Field(
        "sum", description="How to combine rows that share the same x value; 'none' = use rows as they are"
    )

    @field_validator("chart_type", mode="before")
    @classmethod
    def _chart_type(cls, value):
        return _CHART_TYPES.get(str(value).strip().lower(), value)

    @field_validator("aggregation", mode="before")
    @classmethod
    def _aggregation(cls, value):
        return _AGGREGATIONS.get(str(value if value is not None else "").strip().lower(), value)

    @field_validator("y_columns", mode="before")
    @classmethod
    def _y_columns(cls, value):
        return _as_list(value)

    @field_validator("document_id", mode="before")
    @classmethod
    def _document_id(cls, value):
        return _as_int(value)

    @field_validator("sheet", mode="before")
    @classmethod
    def _sheet(cls, value):
        return _no_sheet(value)


class TableSpec(BaseModel):
    """The LLM only NAMES the columns. The cells are read by code from the real file."""
    title: str = ""
    document_id: int = Field(..., description="document_id of a spreadsheet from DATA FILES")
    sheet: Optional[str] = Field(None, description="Sheet name (leave empty for a CSV file)")
    columns: List[str] = Field(..., description="Columns to show, in order")
    max_rows: int = Field(8, description="How many rows to show")

    @field_validator("columns", mode="before")
    @classmethod
    def _columns(cls, value):
        return _as_list(value)

    @field_validator("document_id", "max_rows", mode="before")
    @classmethod
    def _ints(cls, value):
        return _as_int(value)

    @field_validator("sheet", mode="before")
    @classmethod
    def _sheet(cls, value):
        return _no_sheet(value)

    @field_validator("max_rows", mode="after")
    @classmethod
    def _clamp_rows(cls, value):
        return max(1, min(value, 15))


class SlideContentDraft(BaseModel):
    """What the LLM returns for ONE slide (before the code validates it)."""
    subtitle: Optional[str] = Field(None, description="One line under the title (title layout)")
    bullets: List[Bullet] = Field(default_factory=list, description="Main bullets (left column for two_columns)")
    right_bullets: List[Bullet] = Field(default_factory=list, description="Right column (two_columns only)")
    speaker_notes: str = Field("", description="2-4 sentences the presenter can say for this slide")
    chart: Optional[ChartSpec] = Field(None, description="Only for the chart layout")
    table: Optional[TableSpec] = Field(None, description="Only for the table layout")

    @field_validator("bullets", "right_bullets", mode="before")
    @classmethod
    def _plain_bullets(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [{"text": item} if isinstance(item, str) else item for item in value]

    @field_validator("speaker_notes", mode="before")
    @classmethod
    def _notes(cls, value):
        if isinstance(value, list):
            return " ".join(str(v) for v in value)
        return "" if value is None else value

    @field_validator("chart", "table", mode="before")
    @classmethod
    def _empty_spec_is_none(cls, value):
        return None if value in ({}, [], "", "null", "none") else value


class SeriesData(BaseModel):
    name: str
    values: List[float]


class ChartData(BaseModel):
    """A chart with its numbers already computed, ready for the renderer."""
    chart_type: Literal["bar", "line", "pie"]
    title: str
    categories: List[str]
    series: List[SeriesData]
    source: str = Field(..., description="Which file / sheet the numbers came from")


class TableData(BaseModel):
    """A table with its cells already read from the file, ready for the renderer."""
    title: str
    columns: List[str]
    rows: List[List[Union[str, int, float, None]]]
    source: str


class SlideContent(BaseModel):
    """One finished slide: everything the renderer needs, nothing left to compute."""
    slide_number: int
    title: str
    layout_type: str
    subtitle: Optional[str] = None
    bullets: List[Bullet] = Field(default_factory=list)
    right_bullets: List[Bullet] = Field(default_factory=list)
    speaker_notes: str = ""
    chart: Optional[ChartData] = None
    table: Optional[TableData] = None
    citations: List[Citation] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list, description="Anything the code had to fix or drop")


class PresentationContent(BaseModel):
    """The complete deck JSON (Task 2 output, Task 3 input)."""
    presentation_title: str
    target_audience: str
    slides: List[SlideContent]
