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
        return AccountContext(
            account_id=account_id,
            tenant_id=TENANT_ID,
            scopes=("profile:read", "profile:write"),
        )


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


def education_payload(qualification: str = "Synthetic Diploma") -> dict[str, object]:
    return {
        "kind": "education",
        "institution": "Example Institute",
        "qualification": qualification,
        "fieldOfStudy": "Distributed Systems",
        "startDate": "2020-09-01",
        "endDate": "2022-06-30",
        "current": False,
    }


def experience_payload() -> dict[str, object]:
    return {
        "kind": "experience",
        "title": "Platform Engineer",
        "employer": "Example Labs",
        "startDate": "2024-01-01",
        "current": True,
    }


def test_education_crud_is_owner_scoped_and_contract_shaped(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'education.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())

    with TestClient(application) as client:
        created = client.post("/v1/profile/items", json=education_payload(), headers=headers())
        assert created.status_code == 201
        item = created.json()
        item_id = item["itemId"]
        assert item["kind"] == "education"
        assert item["fieldOfStudy"] == "Distributed Systems"

        assert (
            client.get(f"/v1/profile/items/{item_id}", headers=headers("other")).status_code == 404
        )

        replaced = client.put(
            f"/v1/profile/items/{item_id}",
            json=education_payload("Synthetic Advanced Diploma"),
            headers=headers(),
        )
        assert replaced.status_code == 200
        assert replaced.json()["qualification"] == "Synthetic Advanced Diploma"

        deleted = client.delete(f"/v1/profile/items/{item_id}", headers=headers())
        assert deleted.status_code == 204
        assert client.get(f"/v1/profile/items/{item_id}", headers=headers()).status_code == 404


def test_mixed_item_list_has_one_cursor_and_kind_filter(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'mixed-page.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())

    with TestClient(application) as client:
        experience = client.post(
            "/v1/profile/items", json=experience_payload(), headers=headers()
        ).json()
        education = client.post(
            "/v1/profile/items", json=education_payload(), headers=headers()
        ).json()

        first = client.get("/v1/profile/items?pageSize=1", headers=headers()).json()
        second = client.get(
            f"/v1/profile/items?pageSize=1&cursor={first['page']['nextCursor']}",
            headers=headers(),
        ).json()
        assert {first["items"][0]["itemId"], second["items"][0]["itemId"]} == {
            experience["itemId"],
            education["itemId"],
        }
        assert "nextCursor" not in second["page"]

        filtered = client.get("/v1/profile/items?kind=education", headers=headers()).json()
        assert [item["kind"] for item in filtered["items"]] == ["education"]
