"""Closed V1 profile-item unions used by application ports."""

from typing import Annotated, Literal

from pydantic import Field

from careeros_profile.domain.education import Education, EducationDraft
from careeros_profile.domain.experience import Experience, ExperienceDraft
from careeros_profile.domain.skill import Skill, SkillDraft

ProfileItemKind = Literal["experience", "education", "skill"]
ProfileItemDraft = Annotated[
    ExperienceDraft | EducationDraft | SkillDraft, Field(discriminator="kind")
]
ProfileItem = Experience | Education | Skill
