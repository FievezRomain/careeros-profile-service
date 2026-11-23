"""Trusted identity facts required by Profile use cases."""

from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AccountContext(BaseModel):
    """Normalized identity established by the configured OIDC provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: UUID
    tenant_id: UUID
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()


class TokenValidationError(Exception):
    """A bearer token cannot establish a trusted account context."""


class TokenVerifier(Protocol):
    """Port implemented by the OIDC adapter."""

    def verify(self, token: str) -> AccountContext: ...
