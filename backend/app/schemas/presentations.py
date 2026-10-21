"""API schemas for generating and reading presentations."""
 
from datetime import datetime
from typing import Literal
 
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
 
from app.core.config import settings
from app.database.models import PresentationStatus
from app.tools.pptx_themes import THEMES
 
 
class PresentationCreate(BaseModel):
    topic: str = Field(min_length=3, max_length=300)
    title: str | None = Field(default=None, max_length=150)
    num_slides: int = Field(default=8, ge=3, le=40)
    audience: str = Field(default="general audience", max_length=100)
    style: str = Field(default="professional", max_length=100)
    theme: str = "classic"
    direction: Literal["auto", "ltr", "rtl"] = (
        "auto"  # auto: Arabic/Hebrew decks are mirrored
    )
    include_sources_slide: bool = True
    document_ids: list[int] | None = Field(
        default=None, max_length=50
    )  # None = all documents
 
    @field_validator("theme")
    @classmethod
    def _known_theme(cls, value: str) -> str:
        if value not in THEMES:
            raise ValueError(f"theme must be one of: {', '.join(THEMES)}")
        return value
 
 
class PresentationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
 
    id: int
    notebook_id: int
    title: str
    status: str
    stage: str | None = None
    error: str | None = None
    options: dict
    created_at: datetime
    updated_at: datetime | None = None
    deck: dict | None = Field(default=None, exclude=True)  # read only to build `warnings`
 
    @computed_field
    @property
    def download_url(self) -> str | None:
        if self.status != PresentationStatus.COMPLETED:
            return None
        return f"{settings.api_prefix}/presentations/{self.id}/download"
 
    @computed_field
    @property
    def warnings(self) -> list[str]:
        """What Task 2 had to repair or drop (a chart that could not be built, ...)."""
        slides = (self.deck or {}).get("slides", [])
        return [w for slide in slides for w in slide.get("warnings", [])]
 
 
class PresentationOptionsOut(BaseModel):
    themes: list[str]
    directions: list[str]
    layouts: list[str]
    max_slides: int
    min_slides: int = 3
 
    @classmethod
    def current(cls) -> "PresentationOptionsOut":
        from app.schemas.slide_content import SLIDE_LAYOUTS
 
        return cls(
            themes=list(THEMES),
            directions=["auto", "ltr", "rtl"],
            layouts=list(SLIDE_LAYOUTS),
            max_slides=settings.max_presentation_slides,
        )

