"""SQLAlchemy implementation of Profile persistence ports."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Engine,
    ForeignKey,
    Select,
    String,
    create_engine,
    select,
    text,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from careeros_profile.application.ports.persistence import PersistenceHealth
from careeros_profile.application.ports.profile import ProfileItemSlice, ProfileOwner
from careeros_profile.domain.education import Education, EducationDraft
from careeros_profile.domain.experience import Experience, ExperienceDraft
from careeros_profile.domain.profile_item import ProfileItem, ProfileItemKind
from careeros_profile.domain.skill import Skill, SkillDraft


class Base(DeclarativeBase):
    """Declarative mapping base owned by the SQLAlchemy adapter."""


class ProfileRow(Base):
    """Persistence representation of an owner-scoped profile aggregate."""

    __tablename__ = "profiles"

    profile_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    owner_account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ExperienceRow(Base):
    """SQLAlchemy representation of a professional experience."""

    __tablename__ = "experiences"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.profile_id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    employer: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(4000))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    current: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EducationRow(Base):
    """SQLAlchemy representation of an education item."""

    __tablename__ = "educations"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.profile_id", ondelete="CASCADE"), nullable=False, index=True
    )
    institution: Mapped[str] = mapped_column(String(200), nullable=False)
    qualification: Mapped[str] = mapped_column(String(200), nullable=False)
    field_of_study: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    current: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SkillRow(Base):
    """SQLAlchemy representation of a self-declared skill."""

    __tablename__ = "skills"

    item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("profiles.profile_id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    level: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _owned_experiences(owner: ProfileOwner) -> Select[ExperienceRow]:
    return (
        select(ExperienceRow)
        .join(ProfileRow, ExperienceRow.profile_id == ProfileRow.profile_id)
        .where(
            ProfileRow.tenant_id == str(owner.tenant_id),
            ProfileRow.owner_account_id == str(owner.account_id),
        )
    )


def _owned_educations(owner: ProfileOwner) -> Select[EducationRow]:
    return (
        select(EducationRow)
        .join(ProfileRow, EducationRow.profile_id == ProfileRow.profile_id)
        .where(
            ProfileRow.tenant_id == str(owner.tenant_id),
            ProfileRow.owner_account_id == str(owner.account_id),
        )
    )


def _owned_skills(owner: ProfileOwner) -> Select[SkillRow]:
    return (
        select(SkillRow)
        .join(ProfileRow, SkillRow.profile_id == ProfileRow.profile_id)
        .where(
            ProfileRow.tenant_id == str(owner.tenant_id),
            ProfileRow.owner_account_id == str(owner.account_id),
        )
    )


def _profile_id(session: Session, owner: ProfileOwner) -> str:
    profile = session.scalar(
        select(ProfileRow).where(
            ProfileRow.tenant_id == str(owner.tenant_id),
            ProfileRow.owner_account_id == str(owner.account_id),
        )
    )
    if profile is None:
        profile = ProfileRow(
            profile_id=str(uuid4()),
            tenant_id=str(owner.tenant_id),
            owner_account_id=str(owner.account_id),
        )
        session.add(profile)
        session.flush()
    return profile.profile_id


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=value.tzinfo or UTC)


def _experience(row: ExperienceRow) -> Experience:
    return Experience.model_validate(
        {
            "item_id": row.item_id,
            "kind": "experience",
            "title": row.title,
            "employer": row.employer,
            "description": row.description,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "current": row.current,
            "created_at": _aware(row.created_at),
            "updated_at": _aware(row.updated_at),
        }
    )


def _education(row: EducationRow) -> Education:
    return Education.model_validate(
        {
            "item_id": row.item_id,
            "kind": "education",
            "institution": row.institution,
            "qualification": row.qualification,
            "field_of_study": row.field_of_study,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "current": row.current,
            "created_at": _aware(row.created_at),
            "updated_at": _aware(row.updated_at),
        }
    )


def _skill(row: SkillRow) -> Skill:
    return Skill.model_validate(
        {
            "item_id": row.item_id,
            "kind": "skill",
            "name": row.name,
            "level": row.level,
            "level_source": "selfDeclared" if row.level is not None else None,
            "created_at": _aware(row.created_at),
            "updated_at": _aware(row.updated_at),
        }
    )


class SqlAlchemyProfileItemReader:
    """Read all supported item kinds through one stable ordered page."""

    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def list(
        self,
        owner: ProfileOwner,
        *,
        offset: int,
        limit: int,
        kind: ProfileItemKind | None,
    ) -> ProfileItemSlice:
        ceiling = offset + limit + 1
        with self._sessions() as session:
            items: list[ProfileItem] = []
            if kind in (None, "experience"):
                experience_rows = session.scalars(
                    _owned_experiences(owner)
                    .order_by(ExperienceRow.created_at, ExperienceRow.item_id)
                    .limit(ceiling)
                )
                items.extend(_experience(row) for row in experience_rows)
            if kind in (None, "education"):
                education_rows = session.scalars(
                    _owned_educations(owner)
                    .order_by(EducationRow.created_at, EducationRow.item_id)
                    .limit(ceiling)
                )
                items.extend(_education(row) for row in education_rows)
            if kind in (None, "skill"):
                skill_rows = session.scalars(
                    _owned_skills(owner)
                    .order_by(SkillRow.created_at, SkillRow.item_id)
                    .limit(ceiling)
                )
                items.extend(_skill(row) for row in skill_rows)
        items.sort(key=lambda item: (item.created_at, str(item.item_id)))
        window = items[offset : offset + limit + 1]
        return ProfileItemSlice(items=tuple(window[:limit]), has_more=len(window) > limit)

    def get(self, owner: ProfileOwner, item_id: UUID) -> ProfileItem | None:
        with self._sessions() as session:
            experience = session.scalar(
                _owned_experiences(owner).where(ExperienceRow.item_id == str(item_id))
            )
            if experience is not None:
                return _experience(experience)
            education = session.scalar(
                _owned_educations(owner).where(EducationRow.item_id == str(item_id))
            )
            if education is not None:
                return _education(education)
            skill = session.scalar(_owned_skills(owner).where(SkillRow.item_id == str(item_id)))
            return _skill(skill) if skill is not None else None


class SqlAlchemyExperienceRepository:
    """Persist experience mutations inside the trusted owner scope."""

    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create(self, owner: ProfileOwner, draft: ExperienceDraft) -> Experience:
        with self._sessions.begin() as session:
            now = datetime.now(UTC)
            row = ExperienceRow(
                item_id=str(uuid4()),
                profile_id=_profile_id(session, owner),
                created_at=now,
                updated_at=now,
                **draft.model_dump(exclude={"kind"}, by_alias=False),
            )
            session.add(row)
        return _experience(row)

    def replace(
        self, owner: ProfileOwner, item_id: UUID, draft: ExperienceDraft
    ) -> Experience | None:
        with self._sessions.begin() as session:
            row = session.scalar(
                _owned_experiences(owner).where(ExperienceRow.item_id == str(item_id))
            )
            if row is None:
                return None
            for field, value in draft.model_dump(exclude={"kind"}, by_alias=False).items():
                setattr(row, field, value)
            row.updated_at = datetime.now(UTC)
        return _experience(row)

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool:
        with self._sessions.begin() as session:
            row = session.scalar(
                _owned_experiences(owner).where(ExperienceRow.item_id == str(item_id))
            )
            if row is None:
                return False
            session.delete(row)
            return True


class SqlAlchemyEducationRepository:
    """Persist education mutations inside the trusted owner scope."""

    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create(self, owner: ProfileOwner, draft: EducationDraft) -> Education:
        with self._sessions.begin() as session:
            now = datetime.now(UTC)
            row = EducationRow(
                item_id=str(uuid4()),
                profile_id=_profile_id(session, owner),
                created_at=now,
                updated_at=now,
                **draft.model_dump(exclude={"kind"}, by_alias=False),
            )
            session.add(row)
        return _education(row)

    def replace(
        self, owner: ProfileOwner, item_id: UUID, draft: EducationDraft
    ) -> Education | None:
        with self._sessions.begin() as session:
            row = session.scalar(
                _owned_educations(owner).where(EducationRow.item_id == str(item_id))
            )
            if row is None:
                return None
            for field, value in draft.model_dump(exclude={"kind"}, by_alias=False).items():
                setattr(row, field, value)
            row.updated_at = datetime.now(UTC)
        return _education(row)

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool:
        with self._sessions.begin() as session:
            row = session.scalar(
                _owned_educations(owner).where(EducationRow.item_id == str(item_id))
            )
            if row is None:
                return False
            session.delete(row)
            return True


class SqlAlchemySkillRepository:
    """Persist skill mutations while deriving self-declared provenance."""

    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def create(self, owner: ProfileOwner, draft: SkillDraft) -> Skill:
        with self._sessions.begin() as session:
            now = datetime.now(UTC)
            row = SkillRow(
                item_id=str(uuid4()),
                profile_id=_profile_id(session, owner),
                created_at=now,
                updated_at=now,
                **draft.model_dump(exclude={"kind"}, by_alias=False),
            )
            session.add(row)
        return _skill(row)

    def replace(self, owner: ProfileOwner, item_id: UUID, draft: SkillDraft) -> Skill | None:
        with self._sessions.begin() as session:
            row = session.scalar(_owned_skills(owner).where(SkillRow.item_id == str(item_id)))
            if row is None:
                return None
            for field, value in draft.model_dump(exclude={"kind"}, by_alias=False).items():
                setattr(row, field, value)
            row.updated_at = datetime.now(UTC)
        return _skill(row)

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool:
        with self._sessions.begin() as session:
            row = session.scalar(_owned_skills(owner).where(SkillRow.item_id == str(item_id)))
            if row is None:
                return False
            session.delete(row)
            return True


class SqlAlchemyPersistenceProbe:
    """Check database reachability without exposing SQLAlchemy to the core."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def check(self) -> PersistenceHealth:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return PersistenceHealth(available=False)
        return PersistenceHealth(available=True)


def create_profile_engine(database_url: str) -> Engine:
    """Create the engine for this adapter's configured database implementation."""
    return create_engine(database_url, pool_pre_ping=True)
