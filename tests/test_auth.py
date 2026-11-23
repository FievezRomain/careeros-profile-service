from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK

from careeros_profile.adapters.auth import JwtTokenVerifier
from careeros_profile.application.ports.authentication import (
    AccountContext,
    TokenValidationError,
)

ACCOUNT_ID = UUID("30000000-0000-0000-0000-000000000001")
TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")


class StaticResolver:
    def __init__(self, key: PyJWK) -> None:
        self._key = key

    def resolve(self, token: str) -> PyJWK:
        return self._key


def verifier_and_key() -> tuple[JwtTokenVerifier, rsa.RSAPrivateKey]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = PyJWK.from_json(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    return (
        JwtTokenVerifier(
            StaticResolver(public_jwk),
            "https://identity.example.invalid/realms/careeros",
            "careeros-api",
        ),
        private_key,
    )


def token(private_key: rsa.RSAPrivateKey, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "aud": "careeros-api",
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "iss": "https://identity.example.invalid/realms/careeros",
        "realm_access": {"roles": ["member", "member"]},
        "scope": "profile:write profile:read profile:read",
        "sub": str(ACCOUNT_ID),
        "tenant_id": str(TENANT_ID),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


def test_oidc_adapter_validates_and_normalizes_trusted_claims() -> None:
    verifier, private_key = verifier_and_key()

    assert verifier.verify(token(private_key)) == AccountContext(
        account_id=ACCOUNT_ID,
        tenant_id=TENANT_ID,
        roles=("member",),
        scopes=("profile:read", "profile:write"),
    )


@pytest.mark.parametrize("overrides", [{"aud": "other"}, {"tenant_id": None}, {"exp": 0}])
def test_oidc_adapter_rejects_untrusted_or_incomplete_tokens(
    overrides: dict[str, object],
) -> None:
    verifier, private_key = verifier_and_key()

    with pytest.raises(TokenValidationError):
        verifier.verify(token(private_key, **overrides))
