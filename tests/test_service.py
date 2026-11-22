import json
import logging
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect

from careeros_profile.adapters.http import CORRELATION_HEADER, Settings, create_app
from careeros_profile.adapters.persistence import (
    SqlAlchemyPersistenceProbe,
    create_profile_engine,
)


class StubProbe:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    def is_ready(self) -> bool:
        return self._ready


SETTINGS = Settings(app_env="test", log_level="info", database_url="sqlite+pysqlite:///:memory:")


def client(ready: bool = True) -> TestClient:
    return TestClient(create_app(SETTINGS, StubProbe(ready)))


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


def test_persistence_probe_checks_an_isolated_database(tmp_path: Path) -> None:
    engine = create_profile_engine(f"sqlite+pysqlite:///{tmp_path / 'probe.db'}")
    try:
        assert SqlAlchemyPersistenceProbe(engine).is_ready()
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
    configuration = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    configuration.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(configuration, "head")
    assert profile_table_exists(database_url)
    command.downgrade(configuration, "base")
    assert not profile_table_exists(database_url)
