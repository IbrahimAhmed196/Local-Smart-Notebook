"""Task 2: slide content schemas (what the LLM writes + the finished, renderable slide JSON).

Kept in its own file so Task 1's schemas/slides.py stays untouched.
"""
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

# The layouts the slide writer (Task 2) and the renderer (Task 3) both understand.
SLIDE_LAYOUTS = ("title", "bullet_points", "two_columns", "chart", "table")
DEFAULT_LAYOUT = "bullet_points"


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


class ChartSpec(BaseModel):
    """The LLM only NAMES the data. The numbers are computed by code from the real file."""
    chart_type: Literal["bar", "line", "pie"]
    title: str
    document_id: int = Field(..., description="document_id of a spreadsheet from DATA FILES")
    sheet: Optional[str] = Field(None, description="Sheet name (leave empty for a CSV file)")
    x_column: str = Field(..., description="Column used for the categories / x axis")
    y_columns: List[str] = Field(..., description="Numeric column(s) to plot")
    aggregation: Literal["sum", "mean", "count", "none"] = Field(
        "sum", description="How to combine rows that share the same x value; 'none' = use rows as they are"
    )


class TableSpec(BaseModel):
    """The LLM only NAMES the columns. The cells are read by code from the real file."""
    title: str
    document_id: int = Field(..., description="document_id of a spreadsheet from DATA FILES")
    sheet: Optional[str] = Field(None, description="Sheet name (leave empty for a CSV file)")
    columns: List[str] = Field(..., description="Columns to show, in order")
    max_rows: int = Field(8, description="How many rows to show")


class SlideContentDraft(BaseModel):
    """What the LLM returns for ONE slide (before the code validates it)."""
    subtitle: Optional[str] = Field(None, description="One line under the title (title layout)")
    bullets: List[Bullet] = Field(default_factory=list, description="Main bullets (left column for two_columns)")
    right_bullets: List[Bullet] = Field(default_factory=list, description="Right column (two_columns only)")
    speaker_notes: str = Field("", description="2-4 sentences the presenter can say for this slide")
    chart: Optional[ChartSpec] = Field(None, description="Only for the chart layout")
    table: Optional[TableSpec] = Field(None, description="Only for the table layout")


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
