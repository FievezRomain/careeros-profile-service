"""Provenance and validation rules shared by material profile facts."""

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FactOrigin = Literal[
    "directEntry",
    "resumeImport",
    "generatedSuggestion",
    "userCorrection",
]
FactValidationStatus = Literal["unconfirmed", "userConfirmed"]


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class FactProvenanceInput(BaseModel):
    """Caller-supplied origin for a newly materialized fact."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )

    origin: FactOrigin = "directEntry"
    source_id: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_source(self) -> Self:
        source_required = self.origin in {"resumeImport", "generatedSuggestion", "userCorrection"}
        if source_required != (self.source_id is not None):
            raise ValueError("sourceId is required exactly when the origin references a source")
        return self


class FactProvenance(FactProvenanceInput):
    """Server-recorded immutable provenance of the current fact value."""

    recorded_at: datetime


def initial_validation_status(origin: FactOrigin) -> FactValidationStatus:
    """Only direct user entry starts confirmed; every derived fact needs approval."""

    return "userConfirmed" if origin == "directEntry" else "unconfirmed"
