import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect

from careeros_profile.adapters.http import CORRELATION_HEADER, Settings, create_app
from careeros_profile.adapters.migrations.runner import AlembicMigrationRunner
from careeros_profile.adapters.persistence.sqlalchemy import (
    SqlAlchemyPersistenceProbe,
    create_profile_engine,
)
from careeros_profile.application.ports.persistence import (
    MigrationState,
    PersistenceHealth,
)
from careeros_profile.application.use_cases.operations import MigrationStateError


class StubProbe:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    def check(self) -> PersistenceHealth:
        return PersistenceHealth(available=self._ready)


class StubMigrationRunner:
    def __init__(self, latest: bool = True) -> None:
        self.calls = 0
        self._latest = latest

    def ensure_latest(self) -> MigrationState:
        self.calls += 1
        current = ("head",) if self._latest else ()
        return MigrationState(current_heads=current, expected_heads=("head",))


SETTINGS = Settings(
    app_env="test",
    log_level="info",
    database_url="sqlite+pysqlite:///:memory:",
    oidc_issuer="https://identity.example.invalid/realms/careeros",
    oidc_audience="careeros-api",
    oidc_jwks_url="https://identity.example.invalid/realms/careeros/certs",
)


def client(ready: bool = True, migrations: StubMigrationRunner | None = None) -> TestClient:
    return TestClient(create_app(SETTINGS, StubProbe(ready), migrations or StubMigrationRunner()))


def tables(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.parametrize(("path", "expected"), [("/health", "ok"), ("/ready", "ready")])
def test_operational_endpoints(path: str, expected: str) -> None:
    with client() as test_client:
        response = test_client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": expected, "service": "profile-service"}
    assert response.headers[CORRELATION_HEADER]


def test_readiness_reports_owned_database_failure_without_details() -> None:
    with client(False) as test_client:
        response = test_client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "service": "profile-service"}
    assert "database" not in response.text.lower()


def test_startup_injects_runner_and_rejects_incomplete_schema() -> None:
    migrations = StubMigrationRunner()
    with client(migrations=migrations):
        pass
    assert migrations.calls == 1

    with pytest.raises(MigrationStateError), client(migrations=StubMigrationRunner(False)):
        pass


def test_persistence_probe_checks_an_isolated_database(tmp_path: Path) -> None:
    engine = create_profile_engine(f"sqlite+pysqlite:///{tmp_path / 'probe.db'}")
    try:
        assert SqlAlchemyPersistenceProbe(engine).check().available
    finally:
        engine.dispose()


def test_structured_logs_redact_query_values(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="careeros.profile.http"), client() as test_client:
        test_client.get("/ready?token=do-not-log", headers={CORRELATION_HEADER: "profile-7"})

    payload = json.loads(caplog.records[-1].message)
    assert set(payload) == {"correlation_id", "event", "method", "path", "status_code"}
    assert (payload["correlation_id"], payload["path"], payload["status_code"]) == (
        "profile-7",
        "/ready",
        200,
    )
    assert "do-not-log" not in caplog.text


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"app_env": "test", "log_level": "info", "database_url": ""},
        {
            "app_env": "staging",
            "log_level": "info",
            "database_url": "sqlite+pysqlite:///:memory:",
        },
    ],
)
def test_rejects_missing_or_invalid_configuration(values: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


def test_openapi_documents_operational_and_versioned_profile_endpoints() -> None:
    with client() as test_client:
        document = test_client.get("/openapi.json").json()

    assert set(document["paths"]) == {
        "/health",
        "/ready",
        "/v1/profile/items",
        "/v1/profile/items/{itemId}",
        "/v1/profile/items/{itemId}/confirmation",
        "/v1/profile/snapshots",
        "/v1/profile/snapshots/{snapshotId}",
        "/v1/profile/search-criteria",
        "/v1/profile/search-criteria/{action}",
        "/v1/profile/search-criteria/versions/{versionId}",
    }
    confirmation = document["paths"]["/v1/profile/items/{itemId}/confirmation"]["put"]
    create_snapshot = document["paths"]["/v1/profile/snapshots"]["post"]
    assert confirmation["responses"]["200"]["content"]["application/json"]["schema"]
    assert create_snapshot["responses"]["201"]["content"]["application/json"]["schema"]
    idempotency_header = next(
        parameter
        for parameter in create_snapshot["parameters"]
        if parameter["name"] == "Idempotency-Key"
    )
    assert idempotency_header["required"] is True


def test_migrations_apply_and_roll_back_all_adapter_owned_tables(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"
    migrations = AlembicMigrationRunner(database_url)

    assert migrations.ensure_latest().at_latest
    owned_tables = {
        "alembic_version",
        "profiles",
        "experiences",
        "educations",
        "skills",
        "profile_snapshots",
        "snapshot_idempotency",
        "search_criteria_versions",
        "profile_outbox_events",
    }
    assert owned_tables <= tables(database_url)
    migrations.downgrade_base()
    assert not (owned_tables - {"alembic_version"}) & tables(database_url)
