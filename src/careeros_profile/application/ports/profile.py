"""Technology-neutral profile persistence capabilities."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from careeros_profile.domain.experience import Experience, ExperienceDraft


class ProfileOwner(BaseModel):
    """Opaque owner scope applied to every persistence operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: UUID
    tenant_id: UUID


class ExperienceSlice(BaseModel):
    """Stable page fragment independent from database pagination details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[Experience, ...]
    has_more: bool


class ExperienceRepository(Protocol):
    """Outbound port for owner-scoped experience persistence."""

    def list(self, owner: ProfileOwner, *, offset: int, limit: int) -> ExperienceSlice: ...

    def get(self, owner: ProfileOwner, item_id: UUID) -> Experience | None: ...

    def create(self, owner: ProfileOwner, draft: ExperienceDraft) -> Experience: ...

    def replace(
        self, owner: ProfileOwner, item_id: UUID, draft: ExperienceDraft
    ) -> Experience | None: ...

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool: ...


class ExperiencePage(BaseModel):
    """Application result using an opaque continuation cursor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[Experience, ...]
    next_cursor: str | None = Field(default=None)
