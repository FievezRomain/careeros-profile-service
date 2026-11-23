"""Closed V1 profile-item unions used by application ports."""

from typing import Annotated, Literal

from pydantic import Field

from careeros_profile.domain.education import Education, EducationDraft
from careeros_profile.domain.experience import Experience, ExperienceDraft

ProfileItemKind = Literal["experience", "education", "skill"]
ProfileItemDraft = Annotated[ExperienceDraft | EducationDraft, Field(discriminator="kind")]
ProfileItem = Experience | Education
