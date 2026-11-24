from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from careeros_profile.adapters.http import Settings, create_app
from careeros_profile.application.ports.authentication import AccountContext
from careeros_profile.application.ports.profile import ProfileItemSlice, ProfileOwner
from careeros_profile.application.use_cases.profile_items import (
    InvalidCursor,
    ManageProfileItems,
)
from careeros_profile.application.use_cases.search import (
    MatchRelevantChangeEvent,
    MatchRelevantEvents,
    requests_rematch,
)
from careeros_profile.domain.education import Education, EducationDraft
from careeros_profile.domain.experience import Experience, ExperienceDraft
from careeros_profile.domain.fact import FactProvenance, initial_validation_status
from careeros_profile.domain.profile_item import ProfileItemKind
from careeros_profile.domain.skill import Skill, SkillDraft

OWNER = ProfileOwner(
    account_id=UUID("20000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("10000000-0000-0000-0000-000000000001"),
)


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 1, 1, 8, 0, tzinfo=UTC)


class FixedIdentifiers:
    def __init__(self) -> None:
        self._sequence = 0

    def new(self) -> UUID:
        self._sequence += 1
        return UUID(f"60000000-0000-4000-8000-{self._sequence:012d}")


def match_events() -> MatchRelevantEvents:
    return MatchRelevantEvents(FixedClock(), FixedIdentifiers())


class EmptyReader:
    def list(
        self,
        owner: ProfileOwner,
        *,
        offset: int,
        limit: int,
        kind: ProfileItemKind | None,
    ) -> ProfileItemSlice:
        return ProfileItemSlice(items=(), has_more=False)

    def get(self, owner: ProfileOwner, item_id: UUID) -> None:
        return None


class UnusedFactRepository:
    def confirm(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> None:
        return None


def persisted_provenance(draft: EducationDraft | SkillDraft) -> FactProvenance:
    return FactProvenance(
        **draft.provenance.model_dump(by_alias=False),
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class UnusedExperienceRepository:
    def create(
        self,
        owner: ProfileOwner,
        draft: ExperienceDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Experience:
        raise AssertionError("education must not use the experience repository")

    def replace(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        draft: ExperienceDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Experience | None:
        raise AssertionError("education must not use the experience repository")

    def delete(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> bool:
        raise AssertionError("education must not use the experience repository")


class RecordingEducationRepository:
    def __init__(self) -> None:
        self.created: EducationDraft | None = None

    def create(
        self,
        owner: ProfileOwner,
        draft: EducationDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Education:
        self.created = draft
        return Education(
            **draft.model_dump(exclude={"provenance"}, by_alias=False),
            item_id=UUID("40000000-0000-0000-0000-000000000001"),
            provenance=persisted_provenance(draft),
            validation_status=initial_validation_status(draft.provenance.origin),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def replace(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        draft: EducationDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Education | None:
        return None

    def delete(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> bool:
        return False


class RecordingSkillRepository:
    def __init__(self) -> None:
        self.created: SkillDraft | None = None
        self.events: list[MatchRelevantChangeEvent] = []

    def create(
        self,
        owner: ProfileOwner,
        draft: SkillDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Skill:
        self.created = draft
        if event is not None:
            self.events.append(event)
        return Skill(
            **draft.model_dump(exclude={"provenance"}, by_alias=False),
            item_id=UUID("50000000-0000-0000-0000-000000000001"),
            provenance=persisted_provenance(draft),
            validation_status=initial_validation_status(draft.provenance.origin),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            level_source="selfDeclared" if draft.level is not None else None,
        )

    def replace(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        draft: SkillDraft,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> Skill | None:
        return None

    def delete(
        self,
        owner: ProfileOwner,
        item_id: UUID,
        *,
        event: MatchRelevantChangeEvent | None = None,
    ) -> bool:
        return False


def education_draft(**changes: object) -> EducationDraft:
    values: dict[str, object] = {
        "kind": "education",
        "institution": "Example Institute",
        "qualification": "Synthetic Diploma",
        "start_date": date(2020, 9, 1),
        "end_date": date(2022, 6, 30),
        "current": False,
    }
    values.update(changes)
    return EducationDraft.model_validate(values)


def test_use_case_dispatches_education_through_its_explicit_port() -> None:
    educations = RecordingEducationRepository()
    use_case = ManageProfileItems(
        EmptyReader(),
        UnusedExperienceRepository(),
        educations,
        RecordingSkillRepository(),
        UnusedFactRepository(),
        match_events(),
    )

    created = use_case.create(OWNER, education_draft(), correlation_id="test-correlation")

    assert created.kind == "education"
    assert educations.created is not None


def test_use_case_derives_self_declared_skill_provenance() -> None:
    skills = RecordingSkillRepository()
    use_case = ManageProfileItems(
        EmptyReader(),
        UnusedExperienceRepository(),
        RecordingEducationRepository(),
        skills,
        UnusedFactRepository(),
        match_events(),
    )

    created = use_case.create(
        OWNER,
        SkillDraft(kind="skill", name="Python", level="advanced"),
        correlation_id="test-correlation",
    )

    assert isinstance(created, Skill)
    assert created.level_source == "selfDeclared"
    assert skills.created is not None
    assert skills.events[0].changed_fields == ("skills",)
    assert skills.events[0].correlation_id == "test-correlation"


def test_dated_item_rules_and_cursor_fail_before_adapters() -> None:
    with pytest.raises(ValidationError):
        education_draft(end_date=date(2019, 1, 1))
    with pytest.raises(ValidationError):
        education_draft(current=True)

    use_case = ManageProfileItems(
        EmptyReader(),
        UnusedExperienceRepository(),
        RecordingEducationRepository(),
        RecordingSkillRepository(),
        UnusedFactRepository(),
        match_events(),
    )
    with pytest.raises(InvalidCursor):
        use_case.list(OWNER, cursor="not-a-cursor")


class StaticTokenVerifier:
    def verify(self, token: str) -> AccountContext:
        return AccountContext(
            account_id=(
                OWNER.account_id
                if token == "owner"
                else UUID("20000000-0000-0000-0000-000000000002")
            ),
            tenant_id=OWNER.tenant_id,
            scopes=("profile:read", "profile:write"),
        )


def search_headers(
    token: str = "owner",
    *,
    key: str = "synthetic-search-0001",
    correlation_id: str = "synthetic-correlation-001",
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": key,
        "X-Correlation-ID": correlation_id,
    }


def search_payload(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "targetRoles": ["Platform Engineer"],
        "locations": ["Paris", "Remote Europe"],
        "remotePolicy": "hybrid",
        "contractTypes": ["CDI"],
        "exclusions": ["internship"],
        "minimumScore": 72,
    }
    values.update(changes)
    return values


def service_settings(database_url: str) -> Settings:
    return Settings(
        app_env="test",
        log_level="info",
        database_url=database_url,
        oidc_issuer="https://identity.example.invalid/realms/careeros",
        oidc_audience="careeros-api",
        oidc_jwks_url="https://identity.example.invalid/realms/careeros/certs",
    )


def test_active_search_is_versioned_owned_idempotent_and_minimal(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'active-search.db'}"
    application = create_app(service_settings(database_url), token_verifier=StaticTokenVerifier())

    with TestClient(application) as client:
        first = client.put(
            "/v1/profile/search-criteria",
            json=search_payload(),
            headers=search_headers(),
        )
        replay = client.put(
            "/v1/profile/search-criteria",
            json=search_payload(),
            headers=search_headers(),
        )
        conflict = client.put(
            "/v1/profile/search-criteria",
            json=search_payload(minimumScore=90),
            headers=search_headers(),
        )
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json()
        assert conflict.status_code == 409
        assert first.json()["schedule"] == {
            "timezone": "Europe/Paris",
            "windowStart": "08:00",
            "windowEnd": "10:00",
        }
        signature = first.json()["searchSignature"]
        assert signature["targetRoles"] == ["platform engineer"]
        assert "minimumScore" not in signature

        second = client.put(
            "/v1/profile/search-criteria",
            json=search_payload(targetRoles=["Senior Platform Engineer"]),
            headers=search_headers(key="synthetic-search-0002"),
        )
        previous = client.get(
            f"/v1/profile/search-criteria/versions/{first.json()['criteriaVersionId']}",
            headers=search_headers(),
        )
        concealed = client.get(
            f"/v1/profile/search-criteria/versions/{first.json()['criteriaVersionId']}",
            headers=search_headers("other"),
        )
        assert second.json()["version"] == 2
        assert previous.json()["criteria"]["targetRoles"] == ["Platform Engineer"]
        assert concealed.status_code == 404

        paused = client.post(
            "/v1/profile/search-criteria/pause",
            headers=search_headers(key="synthetic-search-0003"),
        )
        resumed = client.post(
            "/v1/profile/search-criteria/resume",
            headers=search_headers(key="synthetic-search-0004"),
        )
        invalid = client.put(
            "/v1/profile/search-criteria",
            json=search_payload(
                schedule={
                    "timezone": "Invalid/Zone",
                    "windowStart": "10:00",
                    "windowEnd": "08:00",
                }
            ),
            headers=search_headers(key="synthetic-search-0005"),
        )
        anonymous = client.get("/v1/profile/search-criteria")
        skill = client.post(
            "/v1/profile/items",
            json={"kind": "skill", "name": "Python", "level": "advanced"},
            headers={
                "Authorization": "Bearer owner",
                "X-Correlation-ID": "skill-change-correlation",
            },
        )
        assert paused.json()["state"] == "paused"
        assert resumed.json()["state"] == "active"
        assert invalid.status_code == 422
        assert anonymous.status_code == 401
        assert skill.status_code == 201

    with create_engine(database_url).connect() as connection:
        raw_payloads: list[object] = list(
            connection.execute(
                text("SELECT payload FROM profile_outbox_events ORDER BY occurred_at")
            ).scalars()
        )
        serialized = [str(payload) for payload in raw_payloads]
    assert any("profile.match-relevant-change.v1" in payload for payload in serialized)
    assert any("synthetic-correlation-001" in payload for payload in serialized)
    assert any("skill-change-correlation" in payload for payload in serialized)
    assert any("skills" in payload for payload in serialized)
    assert all("minimumScore" not in payload for payload in serialized)
    assert all("contact" not in payload.lower() for payload in serialized)


def test_match_relevance_policy_excludes_contact_and_presentation_changes() -> None:
    assert requests_rematch(
        ("targetRoles", "skills", "experiences", "locations", "workPreferences")
    )
    assert not requests_rematch(("contactDetails", "displayName", "avatar"))
