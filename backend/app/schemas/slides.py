"""Task1: in presentation Pydantic schemas for slides (Stage 2).om"""
from pydantic import BaseModel, Field
from typing import List, Optional

from app.schemas.layouts import SLIDE_LAYOUTS

class SlideOutlineItem(BaseModel):
    slide_number: int = Field(..., description="The sequential number of the slide")
    title: str = Field(..., description="The title of the slide")
    purpose: str = Field(..., description="The core purpose or objective of this slide")
    # Week 6 presentation edits (LLM-02): still a plain str here (the cleaning code tolerates other spellings),
    # but the JSON schema sent to Ollama lists the real layouts as an enum, so the model can only pick one of them.
    layout_type: str = Field(
        ...,
        description="The suggested layout type for the slide such as title, bullet_points, two_columns",
        json_schema_extra={"enum": list(SLIDE_LAYOUTS)},
    )

class PresentationOutlineResponse(BaseModel):
    presentation_title: str = Field(..., description="The overall title of the presentation")
    target_audience: str = Field(..., description="The target audience for the presentation")
    slides: List[SlideOutlineItem] = Field(..., description="The list of slides forming the presentation outline")

