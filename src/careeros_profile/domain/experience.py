"""Professional experience rules independent from delivery and persistence."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from careeros_profile.domain.dated_item import DatedItemDraft


class ExperienceDraft(DatedItemDraft):
    """Validated replacement value for an experience item."""

    kind: Literal["experience"]
    title: str = Field(min_length=1, max_length=200)
    employer: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class Experience(ExperienceDraft):
    """Persisted experience returned through the public boundary."""

    item_id: UUID
    created_at: datetime
    updated_at: datetime
