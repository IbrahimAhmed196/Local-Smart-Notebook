from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.config import settings


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notebook_id: int
    filename: str
    file_type: str
    mime_type: str | None = None
    file_size: int
    sha256: str | None = None
    description: str | None = None
    status: str
    error: str | None = None
    uploaded_at: datetime

    @computed_field
    @property
    def download_url(self) -> str:
        return f"{settings.api_prefix}/documents/{self.id}/download"


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    limit: int
    offset: int


class DocumentUpdate(BaseModel):
    filename: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class SupportedTypesOut(BaseModel):
    extensions: list[str]
    max_upload_mb: float
