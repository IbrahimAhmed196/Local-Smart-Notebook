from typing import List, Literal, Optional
 
from pydantic import BaseModel, Field, field_validator
 
from app.presentations.schemas.layouts import SLIDE_LAYOUTS, find_layout
 
 
class DataHint(BaseModel):
    """What a chart or table slide intends to show. Names only; the numbers are computed from the spreadsheet."""
 
    kind: Literal["chart", "table"]
    chart_type: Optional[Literal["bar", "line", "pie"]] = None
    x: Optional[str] = Field(None, description="Column for the categories / x axis")
    y: List[str] = Field(default_factory=list, description="Numeric column(s) to plot")
    aggregation: Optional[Literal["sum", "mean", "count", "none"]] = None
    columns: List[str] = Field(default_factory=list, description="Table columns, in order")
    rows: Optional[int] = Field(None, description="How many table rows")
    document_id: Optional[int] = Field(None, description="document_id of the spreadsheet from DATA FILES")
    sheet: Optional[str] = None
 
 
class ImageIntent(BaseModel):
    """Placeholder for IMG-01, which replaces it with the full ImageSpec."""
 
    wanted: bool = False
    description: str = ""
 
 
class SlideOutlineItem(BaseModel):
    slide_number: int = Field(..., description="The sequential number of the slide")
    title: str = Field(..., description="The title of the slide")
    purpose: str = Field(..., description="The core purpose or objective of this slide")
    # Strict, and built from the layout registry: the enum below is what Ollama sees in the JSON schema, and the
    # validator rejects any other name. Adding a layout to the registry changes both. (A plain str is used on
    # purpose: Literal[SLIDE_LAYOUTS] works at runtime but editors and mypy refuse a computed Literal.)
    layout_type: str = Field(
        ...,
        description="The layout of the slide: one of the listed layout names",
        json_schema_extra={"enum": list(SLIDE_LAYOUTS)},
    )
    # --- v2 (OUT-01) ---
    section: Optional[str] = Field(None, description="The section of the presentation this slide belongs to")
    key_points: List[str] = Field(default_factory=list, description="Planned talking points, short phrases")
    source_hints: List[str] = Field(
        default_factory=list,
        description='Where the facts come from: fact ids ("doc2-f3"), a document ("doc2") or a page ("doc2:p5")',
    )
    data_hint: Optional[DataHint] = None
    image_intent: Optional[ImageIntent] = None
 
    @field_validator("layout_type", mode="before")
    @classmethod
    def _layout_name(cls, value):
        """Spelling variants ("bullets", "Two Column") become the real name; anything else is an error."""
        spec = find_layout(value if isinstance(value, str) else None, selectable_only=True)
        if spec is None:
            raise ValueError(f"layout_type must be one of: {', '.join(SLIDE_LAYOUTS)}")
        return spec.name
 
 
class PresentationOutlineResponse(BaseModel):
    presentation_title: str = Field(..., description="The overall title of the presentation")
    target_audience: str = Field(..., description="The target audience for the presentation")
    slides: List[SlideOutlineItem] = Field(..., description="The list of slides forming the presentation outline")
    # --- v2 (OUT-01) ---
    language: Optional[str] = Field(None, description="Language of the presentation, for example en or ar")
    sections: List[str] = Field(default_factory=list, description="The section names, in order")
