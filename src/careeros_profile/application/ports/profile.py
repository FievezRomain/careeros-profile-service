"""Technology-neutral profile persistence capabilities."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from careeros_profile.domain.education import Education, EducationDraft
from careeros_profile.domain.experience import Experience, ExperienceDraft
from careeros_profile.domain.profile_item import ProfileItem, ProfileItemKind


class ProfileOwner(BaseModel):
    """Opaque owner scope applied to every persistence operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: UUID
    tenant_id: UUID


class ProfileItemSlice(BaseModel):
    """Stable page fragment independent from database pagination details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ProfileItem, ...]
    has_more: bool


class ProfileItemReader(Protocol):
    """Outbound port for owner-scoped reads across profile item kinds."""

    def list(
        self,
        owner: ProfileOwner,
        *,
        offset: int,
        limit: int,
        kind: ProfileItemKind | None,
    ) -> ProfileItemSlice: ...

    def get(self, owner: ProfileOwner, item_id: UUID) -> ProfileItem | None: ...


class ExperienceRepository(Protocol):
    """Outbound port for owner-scoped experience mutations."""

    def create(self, owner: ProfileOwner, draft: ExperienceDraft) -> Experience: ...

    def replace(
        self, owner: ProfileOwner, item_id: UUID, draft: ExperienceDraft
    ) -> Experience | None: ...

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool: ...


class EducationRepository(Protocol):
    """Outbound port for owner-scoped education mutations."""

    def create(self, owner: ProfileOwner, draft: EducationDraft) -> Education: ...

    def replace(
        self, owner: ProfileOwner, item_id: UUID, draft: EducationDraft
    ) -> Education | None: ...

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool: ...


class ProfileItemPage(BaseModel):
    """Application result using an opaque continuation cursor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ProfileItem, ...]
    next_cursor: str | None = None
