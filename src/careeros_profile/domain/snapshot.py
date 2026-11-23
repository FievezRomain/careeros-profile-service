"""Immutable owner-scoped profile snapshots."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from careeros_profile.domain.profile_item import ProfileItem


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class ProfileSnapshot(BaseModel):
    """A point-in-time copy that cannot be rewritten by live-profile mutations."""

    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    snapshot_id: UUID
    created_at: datetime
    items: tuple[ProfileItem, ...]
