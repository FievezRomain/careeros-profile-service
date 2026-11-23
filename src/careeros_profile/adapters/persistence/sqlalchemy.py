"""SQLAlchemy implementation of Profile persistence ports."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Engine,
    ForeignKey,
    String,
    create_engine,
    select,
    text,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from careeros_profile.application.ports.persistence import PersistenceHealth
from careeros_profile.application.ports.profile import (
    ExperienceSlice,
    ProfileOwner,
)
from careeros_profile.domain.experience import Experience, ExperienceDraft


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
    """SQLAlchemy representation kept inside the persistence adapter."""

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


class SqlAlchemyExperienceRepository:
    """Persist experiences while applying tenant and owner scope in every query."""

    def __init__(self, engine: Engine) -> None:
        self._sessions = sessionmaker(engine, expire_on_commit=False)

    def list(self, owner: ProfileOwner, *, offset: int, limit: int) -> ExperienceSlice:
        with self._sessions() as session:
            statement = (
                self._owned_query(owner)
                .order_by(ExperienceRow.created_at, ExperienceRow.item_id)
                .offset(offset)
                .limit(limit + 1)
            )
            rows = tuple(session.scalars(statement))
            return ExperienceSlice(
                items=tuple(self._to_domain(row) for row in rows[:limit]),
                has_more=len(rows) > limit,
            )

    def get(self, owner: ProfileOwner, item_id: UUID) -> Experience | None:
        with self._sessions() as session:
            row = session.scalar(
                self._owned_query(owner).where(ExperienceRow.item_id == str(item_id))
            )
            return self._to_domain(row) if row is not None else None

    def create(self, owner: ProfileOwner, draft: ExperienceDraft) -> Experience:
        with self._sessions.begin() as session:
            now = datetime.now(UTC)
            row = ExperienceRow(
                item_id=str(uuid4()),
                profile_id=self._profile_id(session, owner),
                created_at=now,
                updated_at=now,
                **draft.model_dump(exclude={"kind"}, by_alias=False),
            )
            session.add(row)
        return self._to_domain(row)

    def replace(
        self, owner: ProfileOwner, item_id: UUID, draft: ExperienceDraft
    ) -> Experience | None:
        with self._sessions.begin() as session:
            row = session.scalar(
                self._owned_query(owner).where(ExperienceRow.item_id == str(item_id))
            )
            if row is None:
                return None
            for field, value in draft.model_dump(exclude={"kind"}, by_alias=False).items():
                setattr(row, field, value)
            row.updated_at = datetime.now(UTC)
        return self._to_domain(row)

    def delete(self, owner: ProfileOwner, item_id: UUID) -> bool:
        with self._sessions.begin() as session:
            row = session.scalar(
                self._owned_query(owner).where(ExperienceRow.item_id == str(item_id))
            )
            if row is None:
                return False
            session.delete(row)
            return True

    @staticmethod
    def _owned_query(owner: ProfileOwner):  # type: ignore[no-untyped-def]
        return (
            select(ExperienceRow)
            .join(ProfileRow, ExperienceRow.profile_id == ProfileRow.profile_id)
            .where(
                ProfileRow.tenant_id == str(owner.tenant_id),
                ProfileRow.owner_account_id == str(owner.account_id),
            )
        )

    @staticmethod
    def _profile_id(session: Session, owner: ProfileOwner) -> str:
        statement = select(ProfileRow).where(
            ProfileRow.tenant_id == str(owner.tenant_id),
            ProfileRow.owner_account_id == str(owner.account_id),
        )
        profile = session.scalar(statement)
        if profile is None:
            profile = ProfileRow(
                profile_id=str(uuid4()),
                tenant_id=str(owner.tenant_id),
                owner_account_id=str(owner.account_id),
            )
            session.add(profile)
            session.flush()
        return profile.profile_id

    @staticmethod
    def _to_domain(row: ExperienceRow) -> Experience:
        created_at = row.created_at.replace(tzinfo=row.created_at.tzinfo or UTC)
        updated_at = row.updated_at.replace(tzinfo=row.updated_at.tzinfo or UTC)
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
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )


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
