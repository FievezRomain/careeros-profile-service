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


SETTINGS = Settings(app_env="test", log_level="info", database_url="sqlite+pysqlite:///:memory:")


def client(ready: bool = True, migrations: StubMigrationRunner | None = None) -> TestClient:
    return TestClient(create_app(SETTINGS, StubProbe(ready), migrations or StubMigrationRunner()))


def profile_table_exists(database_url: str) -> bool:
    engine = create_engine(database_url)
    try:
        return "profiles" in inspect(engine).get_table_names()
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


def test_openapi_documents_only_public_operational_endpoints() -> None:
    with client() as test_client:
        document = test_client.get("/openapi.json").json()

    assert set(document["paths"]) == {"/health", "/ready"}


def test_initial_migration_applies_and_rolls_back(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"
    migrations = AlembicMigrationRunner(database_url)

    assert migrations.ensure_latest().at_latest
    assert profile_table_exists(database_url)
    migrations.downgrade_base()
    assert not profile_table_exists(database_url)
