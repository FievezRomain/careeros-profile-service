"""Alembic implementation of the migration runner port."""

import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from careeros_profile.application.ports.persistence import MigrationState

MIGRATIONS_ROOT = Path(__file__).parent


class AlembicMigrationRunner:
    """Apply every adapter-owned revision and verify all heads are current."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def ensure_latest(self) -> MigrationState:
        configuration = self._configuration()
        command.upgrade(configuration, "heads")
        return self.state()

    def state(self) -> MigrationState:
        configuration = self._configuration()
        expected = tuple(sorted(ScriptDirectory.from_config(configuration).get_heads()))
        engine = create_engine(self._database_url)
        try:
            with engine.connect() as connection:
                current = tuple(sorted(MigrationContext.configure(connection).get_current_heads()))
        finally:
            engine.dispose()
        return MigrationState(current_heads=current, expected_heads=expected)

    def downgrade_base(self) -> None:
        command.downgrade(self._configuration(), "base")

    def _configuration(self) -> Config:
        configuration = Config(str(MIGRATIONS_ROOT / "alembic.ini"))
        configuration.set_main_option("script_location", str(MIGRATIONS_ROOT))
        configuration.set_main_option("sqlalchemy.url", self._database_url.replace("%", "%%"))
        return configuration


def main() -> int:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for migrations")
    runner = AlembicMigrationRunner(database_url)
    action = sys.argv[1] if len(sys.argv) > 1 else "upgrade"
    if action == "upgrade":
        runner.ensure_latest()
    elif action == "downgrade":
        runner.downgrade_base()
    else:
        raise ValueError(f"unsupported migration action: {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
