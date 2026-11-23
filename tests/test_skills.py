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


def skill_payload(level: str | None = "advanced") -> dict[str, object]:
    payload: dict[str, object] = {"kind": "skill", "name": "Python"}
    if level is not None:
        payload["level"] = level
    return payload


def test_skill_crud_is_owned_and_level_is_explicitly_self_declared(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'skills.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())

    with TestClient(application) as client:
        created = client.post("/v1/profile/items", json=skill_payload(), headers=headers())
        assert created.status_code == 201
        item = created.json()
        item_id = item["itemId"]
        assert (item["kind"], item["level"], item["levelSource"]) == (
            "skill",
            "advanced",
            "selfDeclared",
        )

        assert (
            client.get(f"/v1/profile/items/{item_id}", headers=headers("other")).status_code == 404
        )
        filtered = client.get("/v1/profile/items?kind=skill", headers=headers()).json()
        assert [entry["itemId"] for entry in filtered["items"]] == [item_id]

        replaced = client.put(
            f"/v1/profile/items/{item_id}", json=skill_payload(None), headers=headers()
        )
        assert replaced.status_code == 200
        assert "level" not in replaced.json()
        assert "levelSource" not in replaced.json()

        assert client.delete(f"/v1/profile/items/{item_id}", headers=headers()).status_code == 204


def test_skill_input_rejects_claimed_provenance_and_unknown_levels(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'skill-errors.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())

    with TestClient(application) as client:
        claimed = skill_payload()
        claimed["levelSource"] = "certified"
        rejected_source = client.post("/v1/profile/items", json=claimed, headers=headers())
        rejected_level = client.post(
            "/v1/profile/items", json=skill_payload("guru"), headers=headers()
        )

    assert rejected_source.status_code == 422
    assert rejected_level.status_code == 422
    assert "certified" not in rejected_source.text
    assert "guru" not in rejected_level.text


def test_profile_page_paginates_all_three_v1_kinds(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'all-kinds.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())
    payloads = (
        {
            "kind": "experience",
            "title": "Platform Engineer",
            "employer": "Example Labs",
            "startDate": "2024-01-01",
            "current": True,
        },
        {
            "kind": "education",
            "institution": "Example Institute",
            "qualification": "Synthetic Diploma",
            "startDate": "2020-09-01",
            "endDate": "2022-06-30",
            "current": False,
        },
        skill_payload(),
    )

    with TestClient(application) as client:
        for payload in payloads:
            assert (
                client.post("/v1/profile/items", json=payload, headers=headers()).status_code == 201
            )

        first = client.get("/v1/profile/items?pageSize=2", headers=headers()).json()
        second = client.get(
            f"/v1/profile/items?pageSize=2&cursor={first['page']['nextCursor']}",
            headers=headers(),
        ).json()

    assert {item["kind"] for item in first["items"] + second["items"]} == {
        "experience",
        "education",
        "skill",
    }
    assert "nextCursor" not in second["page"]
