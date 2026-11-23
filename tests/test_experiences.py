from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from careeros_profile.adapters.http import Settings, create_app
from careeros_profile.application.ports.authentication import AccountContext

TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")
OWNER_ID = UUID("20000000-0000-0000-0000-000000000001")
OTHER_OWNER_ID = UUID("20000000-0000-0000-0000-000000000002")


class StaticTokenVerifier:
    def verify(self, token: str) -> AccountContext:
        account_id = OWNER_ID if token == "owner" else OTHER_OWNER_ID
        scopes = ("profile:read", "profile:write") if token != "read-only" else ("profile:read",)
        return AccountContext(account_id=account_id, tenant_id=TENANT_ID, scopes=scopes)


def settings(database_url: str) -> Settings:
    return Settings(
        app_env="test",
        log_level="info",
        database_url=database_url,
        oidc_issuer="https://identity.example.invalid/realms/careeros",
        oidc_audience="careeros-api",
        oidc_jwks_url="https://identity.example.invalid/realms/careeros/certs",
    )


def headers(token: str = "owner") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def experience_payload(title: str = "Platform Engineer") -> dict[str, object]:
    return {
        "kind": "experience",
        "title": title,
        "employer": "Example Labs",
        "startDate": "2024-01-01",
        "current": True,
    }


def test_experience_crud_is_owner_scoped_and_contract_shaped(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'profile.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())

    with TestClient(application) as client:
        created = client.post("/v1/profile/items", json=experience_payload(), headers=headers())
        assert created.status_code == 201
        item = created.json()
        item_id = item["itemId"]
        assert created.headers["Location"] == f"/v1/profile/items/{item_id}"
        assert item["startDate"] == "2024-01-01"
        assert {"createdAt", "updatedAt"} <= item.keys()

        listed = client.get("/v1/profile/items?pageSize=1", headers=headers())
        assert listed.status_code == 200
        assert [entry["itemId"] for entry in listed.json()["items"]] == [item_id]

        hidden = client.get(f"/v1/profile/items/{item_id}", headers=headers("other"))
        assert hidden.status_code == 404
        assert hidden.headers["content-type"].startswith("application/problem+json")

        replaced = client.put(
            f"/v1/profile/items/{item_id}",
            json=experience_payload("Senior Platform Engineer"),
            headers=headers(),
        )
        assert replaced.status_code == 200
        assert replaced.json()["title"] == "Senior Platform Engineer"

        deleted = client.delete(f"/v1/profile/items/{item_id}", headers=headers())
        assert deleted.status_code == 204
        assert client.get(f"/v1/profile/items/{item_id}", headers=headers()).status_code == 404


def test_experience_validation_authentication_and_scope_fail_closed(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'profile-errors.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())
    invalid = experience_payload()
    invalid.update({"current": False, "endDate": "2023-01-01"})

    with TestClient(application) as client:
        unauthenticated = client.get("/v1/profile/items")
        assert unauthenticated.status_code == 401
        assert unauthenticated.headers["WWW-Authenticate"] == "Bearer"

        forbidden = client.post(
            "/v1/profile/items", json=experience_payload(), headers=headers("read-only")
        )
        assert forbidden.status_code == 403

        rejected = client.post("/v1/profile/items", json=invalid, headers=headers())
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "VALIDATION_FAILED"
        assert "2023" not in rejected.text

        invalid_cursor = client.get("/v1/profile/items?cursor=not-a-cursor", headers=headers())
        assert invalid_cursor.status_code == 422
