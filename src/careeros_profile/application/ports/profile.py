"""Technology-neutral profile persistence capabilities."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from careeros_profile.domain.education import Education, EducationDraft
from careeros_profile.domain.experience import Experience, ExperienceDraft
from careeros_profile.domain.profile_item import ProfileItem, ProfileItemKind
from careeros_profile.domain.skill import Skill, SkillDraft
from careeros_profile.domain.snapshot import ProfileSnapshot

if TYPE_CHECKING:
    from careeros_profile.application.use_cases.search import (
        MatchRelevantChangeEvent,
        SearchCriteriaSnapshot,
        SearchCriteriaWriteResult,
    )


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


class ProfileFactRepository(Protocol):
    """Outbound port for mutations shared by every material fact kind."""

    def confirm(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> ProfileItem | None: ...


class ExperienceRepository(Protocol):
    """Outbound port for owner-scoped experience mutations."""

    def create(
        self,
        owner: ProfileOwner,
        draft: ExperienceDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Experience: ...

    def replace(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        draft: ExperienceDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Experience | None: ...

    def delete(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> bool: ...


class EducationRepository(Protocol):
    """Outbound port for owner-scoped education mutations."""

    def create(
        self,
        owner: ProfileOwner,
        draft: EducationDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Education: ...

    def replace(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        draft: EducationDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Education | None: ...

    def delete(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> bool: ...


class SkillRepository(Protocol):
    """Outbound port for owner-scoped skill mutations."""

    def create(
        self,
        owner: ProfileOwner,
        draft: SkillDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Skill: ...

    def replace(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        draft: SkillDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Skill | None: ...

    def delete(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> bool: ...


class ProfileItemPage(BaseModel):
    """Application result using an opaque continuation cursor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[ProfileItem, ...]
    next_cursor: str | None = None


class SnapshotCreationResult(BaseModel):
    """Adapter-neutral result of an idempotent snapshot command."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: Literal["created", "replayed", "conflict"]
    snapshot: ProfileSnapshot | None = None


class ProfileSnapshotRepository(Protocol):
    """Outbound port for atomic, owner-scoped immutable snapshots."""

    def create(
        self,
        owner: ProfileOwner,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> SnapshotCreationResult: ...

    def get(self, owner: ProfileOwner, snapshot_id: UUID) -> ProfileSnapshot | None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class IdentifierFactory(Protocol):
    def new(self) -> UUID: ...


class SearchCriteriaRepository(Protocol):
    def write(
        self,
        owner: ProfileOwner,
        snapshot: SearchCriteriaSnapshot,
        event: MatchRelevantChangeEvent,
        *,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> SearchCriteriaWriteResult: ...

    def current(self, owner: ProfileOwner) -> SearchCriteriaSnapshot | None: ...

    def get(self, owner: ProfileOwner, version_id: UUID) -> SearchCriteriaSnapshot | None: ...
