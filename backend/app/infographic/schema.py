

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class Metric(StrictModel):
    name: str = Field(min_length=1)
    value: bool | int | float | str | None
    unit: str | None


class InfographicItem(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1)
    description: str
    date: date | None
    metrics: list[Metric]
    source_refs: list[str]

    @field_validator("source_refs")
    @classmethod
    def source_refs_must_be_unique(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("source_refs must contain unique values")

        for value in values:
            if not value.startswith("src_"):
                raise ValueError("source_refs must start with 'src_'")
            suffix = value[4:]
            if not suffix or not all(
                char.isalnum() or char in "_-" for char in suffix
            ):
                raise ValueError("Invalid source reference format")

        return values


class SourceReference(StrictModel):
    id: str = Field(pattern=r"^src_[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1)
    page: int | None = Field(ge=1)
    excerpt: str


class InfographicPlan(StrictModel):
    schema_version: Literal["1.0"]
    title: str = Field(min_length=1)
    subtitle: str
    type: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    items: list[InfographicItem]
    sources: list[SourceReference]
