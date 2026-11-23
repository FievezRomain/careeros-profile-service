"""Persistence capabilities required by Profile use cases."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class PersistenceHealth(BaseModel):
    """Technology-neutral availability result from the persistence port."""

    model_config = ConfigDict(frozen=True)

    available: bool


class MigrationState(BaseModel):
    """Technology-neutral comparison of applied and expected migrations."""

    model_config = ConfigDict(frozen=True)

    current_heads: tuple[str, ...]
    expected_heads: tuple[str, ...]

    @property
    def at_latest(self) -> bool:
        return bool(self.expected_heads) and set(self.current_heads) == set(self.expected_heads)


class PersistenceProbe(Protocol):
    """Port for checking the service-owned persistence resource."""

    def check(self) -> PersistenceHealth: ...


class MigrationRunner(Protocol):
    """Port for bringing the owned schema to the application-required version."""

    def ensure_latest(self) -> MigrationState: ...
