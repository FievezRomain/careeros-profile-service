"""Operational use cases independent from infrastructure frameworks."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from careeros_profile.application.ports.persistence import (
    MigrationRunner,
    MigrationState,
    PersistenceProbe,
)


class OperationalStatus(BaseModel):
    """Immutable operational result exposed through inbound ports."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "ready", "unavailable"]
    service: Literal["profile-service"] = "profile-service"


class MigrationStateError(RuntimeError):
    """The application cannot start on an incomplete schema."""


class GetHealth:
    def execute(self) -> OperationalStatus:
        return OperationalStatus(status="ok")


class GetReadiness:
    def __init__(self, persistence: PersistenceProbe) -> None:
        self._persistence = persistence

    def execute(self) -> OperationalStatus:
        health = self._persistence.check()
        return OperationalStatus(status="ready" if health.available else "unavailable")


class StartApplication:
    def __init__(self, migrations: MigrationRunner) -> None:
        self._migrations = migrations

    def execute(self) -> MigrationState:
        state = self._migrations.ensure_latest()
        if not state.at_latest:
            raise MigrationStateError("database schema is not at the required migration head")
        return state
