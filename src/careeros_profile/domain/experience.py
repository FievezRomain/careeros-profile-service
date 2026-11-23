"""Professional experience rules independent from delivery and persistence."""

from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class ExperienceDraft(BaseModel):
    """Validated replacement value for an experience item."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )

    kind: Literal["experience"]
    title: str = Field(min_length=1, max_length=200)
    employer: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    start_date: date
    end_date: date | None = None
    current: bool

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("endDate must not precede startDate")
        if self.current and self.end_date is not None:
            raise ValueError("a current experience cannot have an endDate")
        return self


class Experience(ExperienceDraft):
    """Persisted experience returned through the public boundary."""

    item_id: UUID
    created_at: datetime
    updated_at: datetime
