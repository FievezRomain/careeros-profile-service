from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from careeros_profile.application.ports.profile import ProfileItemSlice, ProfileOwner
from careeros_profile.application.use_cases.profile_items import (
    InvalidCursor,
    ManageProfileItems,
)
from careeros_profile.domain.education import Education, EducationDraft
from careeros_profile.domain.experience import Experience, ExperienceDraft
from careeros_profile.domain.profile_item import ProfileItemKind

OWNER = ProfileOwner(
    account_id=UUID("20000000-0000-0000-0000-000000000001"),
    tenant_id=UUID("10000000-0000-0000-0000-000000000001"),
)


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


class UnusedExperienceRepository:
    def create(self, owner: ProfileOwner, draft: ExperienceDraft) -> Experience:
        raise AssertionError("education must not use the experience repository")

    def replace(
        self, owner: ProfileOwner, item_id: UUID, draft: ExperienceDraft
    ) -> Experience | None:
        raise AssertionError("education must not use the experience repository")

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool:
        raise AssertionError("education must not use the experience repository")


class RecordingEducationRepository:
    def __init__(self) -> None:
        self.created: EducationDraft | None = None

    def create(self, owner: ProfileOwner, draft: EducationDraft) -> Education:
        self.created = draft
        return Education(
            **draft.model_dump(by_alias=False),
            item_id=UUID("40000000-0000-0000-0000-000000000001"),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    def replace(
        self, owner: ProfileOwner, item_id: UUID, draft: EducationDraft
    ) -> Education | None:
        return None

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool:
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
    use_case = ManageProfileItems(EmptyReader(), UnusedExperienceRepository(), educations)

    created = use_case.create(OWNER, education_draft())

    assert created.kind == "education"
    assert educations.created is not None


def test_dated_item_rules_and_cursor_fail_before_adapters() -> None:
    with pytest.raises(ValidationError):
        education_draft(end_date=date(2019, 1, 1))
    with pytest.raises(ValidationError):
        education_draft(current=True)

    use_case = ManageProfileItems(
        EmptyReader(), UnusedExperienceRepository(), RecordingEducationRepository()
    )
    with pytest.raises(InvalidCursor):
        use_case.list(OWNER, cursor="not-a-cursor")
