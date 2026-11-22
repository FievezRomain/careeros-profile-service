"""Operational use cases and persistence readiness port."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict


class PersistenceProbe(Protocol):
    """Narrow application port for checking owned persistence."""

    def is_ready(self) -> bool: ...


class OperationalStatus(BaseModel):
    """Immutable operational status exposed through inbound adapters."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "ready", "unavailable"]
    service: Literal["profile-service"] = "profile-service"


def health_status() -> OperationalStatus:
    """Report process liveness without consulting infrastructure."""
    return OperationalStatus(status="ok")


def readiness_status(probe: PersistenceProbe) -> OperationalStatus:
    """Report whether the service-owned database is reachable."""
    return OperationalStatus(status="ready" if probe.is_ready() else "unavailable")
