"""SQLAlchemy adapter for the Profile Service-owned database."""

from datetime import datetime

from sqlalchemy import DateTime, Engine, String, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative mapping base owned by the persistence adapter."""


class ProfileRow(Base):
    """Persistence representation reserved for upcoming profile use cases."""

    __tablename__ = "profiles"

    profile_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    owner_account_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class SqlAlchemyPersistenceProbe:
    """Check database reachability without exposing connection details."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_ready(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return False
        return True


def create_profile_engine(database_url: str) -> Engine:
    """Create the engine for this service's isolated database."""
    return create_engine(database_url, pool_pre_ping=True)
