"""Versioned active-search policy and use cases."""

import hashlib
import json
import unicodedata
from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from careeros_profile.application.ports.profile import (
    Clock,
    IdentifierFactory,
    ProfileOwner,
    SearchCriteriaRepository,
)


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(part.title() for part in rest)


class SearchModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class SearchSchedule(SearchModel):
    timezone: str = "Europe/Paris"
    window_start: str = Field(default="08:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    window_end: str = Field(default="10:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be an IANA timezone") from error
        return value

    @model_validator(mode="after")
    def ordered_window(self) -> SearchSchedule:
        if self.window_start >= self.window_end:
            raise ValueError("windowStart must precede windowEnd")
        return self


def _clean(values: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(
        " ".join(unicodedata.normalize("NFKC", value).strip().split()) for value in values
    )
    if any(not value for value in cleaned):
        raise ValueError("search dimensions cannot contain blank values")
    return cleaned


class SearchCriteria(SearchModel):
    target_roles: tuple[str, ...] = Field(min_length=1, max_length=20)
    locations: tuple[str, ...] = Field(min_length=1, max_length=20)
    remote_policy: Literal["remote", "hybrid", "onsite", "any"]
    contract_types: tuple[str, ...] = Field(min_length=1, max_length=10)
    exclusions: tuple[str, ...] = Field(default=(), max_length=30)
    minimum_score: int = Field(ge=0, le=100)

    @field_validator("target_roles", "locations", "contract_types", "exclusions")
    @classmethod
    def clean_dimensions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return _clean(values)


class SearchCriteriaDraft(SearchCriteria):
    schedule: SearchSchedule = Field(default_factory=SearchSchedule)


class SearchSignature(SearchModel):
    signature_id: str = Field(min_length=64, max_length=64)
    target_roles: tuple[str, ...]
    locations: tuple[str, ...]
    remote_policy: Literal["remote", "hybrid", "onsite", "any"]
    contract_types: tuple[str, ...]
    exclusions: tuple[str, ...]


class SearchCriteriaSnapshot(SearchModel):
    criteria_version_id: UUID
    version: int = Field(ge=1)
    state: Literal["active", "paused"]
    criteria: SearchCriteria
    schedule: SearchSchedule
    search_signature: SearchSignature
    created_at: datetime


class SearchCriteriaWriteResult(SearchModel):
    outcome: Literal["created", "replayed", "conflict"]
    snapshot: SearchCriteriaSnapshot | None = None


class MatchRelevantChangeEvent(SearchModel):
    event_id: UUID
    event_type: Literal["profile.match-relevant-change.v1"] = "profile.match-relevant-change.v1"
    schema_version: Literal["1.0"] = "1.0"
    occurred_at: datetime
    correlation_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=200)
    tenant_id: UUID
    account_id: UUID
    changed_fields: tuple[str, ...]
    criteria_version_id: UUID | None = None
    state: Literal["active", "paused"] | None = None
    schedule: SearchSchedule | None = None
    search_signature: SearchSignature | None = None


MATCH_RELEVANT_FIELDS = frozenset(
    {"targetRoles", "skills", "experiences", "locations", "workPreferences", "searchCriteria"}
)


def requests_rematch(changed_fields: tuple[str, ...]) -> bool:
    return bool(MATCH_RELEVANT_FIELDS.intersection(changed_fields))


def provider_signature(criteria: SearchCriteria) -> SearchSignature:
    def normalized(values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({value.casefold() for value in values}))

    dimensions = {
        "target_roles": normalized(criteria.target_roles),
        "locations": normalized(criteria.locations),
        "remote_policy": criteria.remote_policy,
        "contract_types": normalized(criteria.contract_types),
        "exclusions": normalized(criteria.exclusions),
    }
    fingerprint = hashlib.sha256(
        json.dumps(dimensions, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return SearchSignature(signature_id=fingerprint, **dimensions)


class SearchCriteriaNotFound(Exception):
    """The owned criteria resource or version does not exist."""


class SearchCriteriaIdempotencyConflict(Exception):
    """An idempotency key was reused for a different command."""


class MatchRelevantEvents:
    def __init__(self, clock: Clock, identifiers: IdentifierFactory) -> None:
        self._clock = clock
        self._identifiers = identifiers

    def build(
        self,
        owner: ProfileOwner,
        *,
        changed_fields: tuple[str, ...],
        correlation_id: str,
        idempotency_key: str,
        snapshot: SearchCriteriaSnapshot | None = None,
    ) -> MatchRelevantChangeEvent:
        return MatchRelevantChangeEvent(
            event_id=self._identifiers.new(),
            occurred_at=self._clock.now(),
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            tenant_id=owner.tenant_id,
            account_id=owner.account_id,
            changed_fields=changed_fields,
            criteria_version_id=snapshot.criteria_version_id if snapshot else None,
            state=snapshot.state if snapshot else None,
            schedule=snapshot.schedule if snapshot else None,
            search_signature=snapshot.search_signature if snapshot else None,
        )


class ManageSearchCriteria:
    def __init__(
        self,
        repository: SearchCriteriaRepository,
        events: MatchRelevantEvents,
        clock: Clock,
        identifiers: IdentifierFactory,
    ) -> None:
        self._repository = repository
        self._events = events
        self._clock = clock
        self._identifiers = identifiers

    def update(
        self,
        owner: ProfileOwner,
        draft: SearchCriteriaDraft,
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> SearchCriteriaSnapshot:
        current = self._repository.current(owner)
        return self._write(
            owner,
            criteria=SearchCriteria.model_validate(
                draft.model_dump(exclude={"schedule"}, by_alias=False)
            ),
            schedule=draft.schedule,
            state="active",
            version=(current.version + 1 if current else 1),
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def transition(
        self,
        owner: ProfileOwner,
        state: Literal["active", "paused"],
        *,
        idempotency_key: str,
        correlation_id: str,
    ) -> SearchCriteriaSnapshot:
        current = self.current(owner)
        return self._write(
            owner,
            criteria=current.criteria,
            schedule=current.schedule,
            state=state,
            version=current.version + 1,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
        )

    def current(self, owner: ProfileOwner) -> SearchCriteriaSnapshot:
        snapshot = self._repository.current(owner)
        if snapshot is None:
            raise SearchCriteriaNotFound
        return snapshot

    def get(self, owner: ProfileOwner, version_id: UUID) -> SearchCriteriaSnapshot:
        snapshot = self._repository.get(owner, version_id)
        if snapshot is None:
            raise SearchCriteriaNotFound
        return snapshot

    def _write(
        self,
        owner: ProfileOwner,
        *,
        criteria: SearchCriteria,
        schedule: SearchSchedule,
        state: Literal["active", "paused"],
        version: int,
        idempotency_key: str,
        correlation_id: str,
    ) -> SearchCriteriaSnapshot:
        snapshot = SearchCriteriaSnapshot(
            criteria_version_id=self._identifiers.new(),
            version=version,
            state=state,
            criteria=criteria,
            schedule=schedule,
            search_signature=provider_signature(criteria),
            created_at=self._clock.now(),
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "criteria": criteria.model_dump(mode="json"),
                    "schedule": schedule.model_dump(mode="json"),
                    "state": state,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        event = self._events.build(
            owner,
            changed_fields=("searchCriteria",),
            correlation_id=correlation_id,
            idempotency_key=f"search-criteria:{idempotency_key}",
            snapshot=snapshot,
        )
        result = self._repository.write(
            owner,
            snapshot,
            event,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
        )
        if result.outcome == "conflict" or result.snapshot is None:
            raise SearchCriteriaIdempotencyConflict
        return result.snapshot
