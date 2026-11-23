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
        return AccountContext(
            account_id=OWNER_ID if token == "owner" else OTHER_OWNER_ID,
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


def headers(token: str = "owner", *, idempotency_key: str | None = None) -> dict[str, str]:
    values = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        values["Idempotency-Key"] = idempotency_key
    return values


def experience_payload(title: str = "Platform Engineer") -> dict[str, object]:
    return {
        "kind": "experience",
        "title": title,
        "employer": "Example Labs",
        "startDate": "2024-01-01",
        "current": True,
    }


def test_derived_fact_requires_owner_confirmation_and_records_correction(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'provenance.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())
    imported_payload = experience_payload()
    imported_payload["provenance"] = {
        "origin": "resumeImport",
        "sourceId": "synthetic-resume-001",
    }

    with TestClient(application) as client:
        imported = client.post("/v1/profile/items", json=imported_payload, headers=headers())
        assert imported.status_code == 201
        item = imported.json()
        assert item["provenance"]["origin"] == "resumeImport"
        assert item["provenance"]["sourceId"] == "synthetic-resume-001"
        assert item["provenance"]["recordedAt"]
        assert item["validationStatus"] == "unconfirmed"

        concealed = client.put(
            f"/v1/profile/items/{item['itemId']}/confirmation",
            headers=headers("other"),
        )
        assert concealed.status_code == 404

        confirmed = client.put(
            f"/v1/profile/items/{item['itemId']}/confirmation",
            headers=headers(),
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["validationStatus"] == "userConfirmed"
        replayed_confirmation = client.put(
            f"/v1/profile/items/{item['itemId']}/confirmation",
            headers=headers(),
        )
        assert replayed_confirmation.json() == confirmed.json()

        correction_payload = experience_payload("Senior Platform Engineer")
        correction_payload["provenance"] = {
            "origin": "resumeImport",
            "sourceId": "untrusted-replacement-source",
        }
        corrected = client.put(
            f"/v1/profile/items/{item['itemId']}",
            json=correction_payload,
            headers=headers(),
        )
        assert corrected.status_code == 200
        assert corrected.json()["provenance"] == {
            "origin": "userCorrection",
            "sourceId": item["itemId"],
            "recordedAt": corrected.json()["provenance"]["recordedAt"],
        }
        assert corrected.json()["validationStatus"] == "userConfirmed"


def test_snapshot_is_idempotent_immutable_and_owner_scoped(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'snapshots.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())

    with TestClient(application) as client:
        created = client.post(
            "/v1/profile/items", json=experience_payload(), headers=headers()
        ).json()
        key = "synthetic-snapshot-001"
        first = client.post(
            "/v1/profile/snapshots",
            headers=headers(idempotency_key=key),
        )
        replay = client.post(
            "/v1/profile/snapshots",
            headers=headers(idempotency_key=key),
        )
        assert first.status_code == replay.status_code == 201
        assert first.json() == replay.json()
        snapshot_id = first.json()["snapshotId"]
        assert first.headers["Location"] == f"/v1/profile/snapshots/{snapshot_id}"

        replacement = experience_payload("Senior Platform Engineer")
        assert (
            client.put(
                f"/v1/profile/items/{created['itemId']}",
                json=replacement,
                headers=headers(),
            ).status_code
            == 200
        )
        snapshot = client.get(f"/v1/profile/snapshots/{snapshot_id}", headers=headers())
        assert snapshot.status_code == 200
        assert snapshot.json()["items"][0]["title"] == "Platform Engineer"
        assert snapshot.json()["items"][0]["provenance"]["origin"] == "directEntry"
        assert snapshot.json()["items"][0]["validationStatus"] == "userConfirmed"

        hidden = client.get(f"/v1/profile/snapshots/{snapshot_id}", headers=headers("other"))
        assert hidden.status_code == 404


def test_server_owned_provenance_and_idempotency_key_fail_closed(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'provenance-errors.db'}"
    application = create_app(settings(database_url), token_verifier=StaticTokenVerifier())
    forged = experience_payload()
    forged["provenance"] = {
        "origin": "userCorrection",
        "sourceId": "00000000-0000-4000-8000-000000000001",
    }

    with TestClient(application) as client:
        rejected = client.post("/v1/profile/items", json=forged, headers=headers())
        missing_key = client.post("/v1/profile/snapshots", headers=headers())
        malformed_key = client.post(
            "/v1/profile/snapshots",
            headers=headers(idempotency_key="too short"),
        )

    assert rejected.status_code == 422
    assert missing_key.status_code == 400
    assert malformed_key.status_code == 400
