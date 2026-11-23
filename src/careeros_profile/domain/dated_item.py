"""Shared date rules for dated professional profile items."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class DatedItemDraft(BaseModel):
    """Validated date range shared by experience and education inputs."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )

    start_date: date
    end_date: date | None = None
    current: bool

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("endDate must not precede startDate")
        if self.current and self.end_date is not None:
            raise ValueError("a current item cannot have an endDate")
        return self
