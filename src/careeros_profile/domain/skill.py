"""Self-declared professional skill rules."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SkillLevel = Literal["beginner", "intermediate", "advanced", "expert"]


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class SkillDraft(BaseModel):
    """Validated replacement value for a self-declared skill."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
        str_strip_whitespace=True,
    )

    kind: Literal["skill"]
    name: str = Field(min_length=1, max_length=120)
    level: SkillLevel | None = None


class Skill(SkillDraft):
    """Persisted skill whose optional level is explicitly self-declared."""

    item_id: UUID
    created_at: datetime
    updated_at: datetime
    level_source: Literal["selfDeclared"] | None = None

    @model_validator(mode="after")
    def validate_level_provenance(self) -> Self:
        if (self.level is None) != (self.level_source is None):
            raise ValueError("levelSource must be selfDeclared exactly when level is present")
        return self
