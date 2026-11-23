"""Keycloak-compatible OIDC token validation adapter."""

from collections.abc import Mapping
from typing import Protocol

import jwt
from jwt import PyJWK, PyJWKClient, PyJWTError
from pydantic import ValidationError

from careeros_profile.application.ports.authentication import (
    AccountContext,
    TokenValidationError,
)


class SigningKeyProvider(Protocol):
    def resolve(self, token: str) -> PyJWK: ...


class SigningKeyResolver:
    """Resolve rotating signing keys through the configured JWKS endpoint."""

    def __init__(self, jwks_url: str) -> None:
        self._client = PyJWKClient(jwks_url, cache_keys=True)

    def resolve(self, token: str) -> PyJWK:
        return self._client.get_signing_key_from_jwt(token)


class JwtTokenVerifier:
    """Validate signature and claims before exposing identity to the core."""

    def __init__(self, resolver: SigningKeyProvider, issuer: str, audience: str) -> None:
        self._resolver = resolver
        self._issuer = issuer
        self._audience = audience

    def verify(self, token: str) -> AccountContext:
        try:
            claims: Mapping[str, object] = jwt.decode(
                token,
                key=self._resolver.resolve(token),
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "sub", "tenant_id"]},
            )
            realm_access = claims.get("realm_access")
            roles_value = realm_access.get("roles", []) if isinstance(realm_access, Mapping) else []
            scope_value = claims.get("scope", "")
            roles = tuple(sorted(set(roles_value))) if isinstance(roles_value, list) else ()
            scopes = tuple(sorted(set(scope_value.split()))) if isinstance(scope_value, str) else ()
            return AccountContext.model_validate(
                {
                    "account_id": claims.get("sub"),
                    "tenant_id": claims.get("tenant_id"),
                    "roles": roles,
                    "scopes": scopes,
                }
            )
        except PyJWTError, ValidationError, TypeError:
            raise TokenValidationError from None
