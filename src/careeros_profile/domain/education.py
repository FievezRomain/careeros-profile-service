"""Education rules independent from delivery and persistence."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from careeros_profile.domain.dated_item import DatedItemDraft


class EducationDraft(DatedItemDraft):
    """Validated replacement value for an education item."""

    kind: Literal["education"]
    institution: str = Field(min_length=1, max_length=200)
    qualification: str = Field(min_length=1, max_length=200)
    field_of_study: str | None = Field(default=None, max_length=200)


class Education(EducationDraft):
    """Persisted education returned through the public boundary."""

    item_id: UUID
    created_at: datetime
    updated_at: datetime
