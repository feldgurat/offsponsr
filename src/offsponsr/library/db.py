from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import URL, create_engine, event

if TYPE_CHECKING:
    from sqlalchemy import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parent / 'migrations'


class UnknownRevisionError(Exception):
    """The database is at a schema revision this version of the app doesn't have."""


def open_engine(db_path: Path) -> Engine:
    engine = create_engine(URL.create('sqlite', database=str(db_path)))

    @event.listens_for(engine, 'connect')
    def configure(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        # SQLite leaves foreign keys unenforced unless asked, per connection.
        cursor.execute('PRAGMA foreign_keys=ON')
        # The UI reads while a sync writes; wait for the other side instead of failing at once.
        cursor.execute('PRAGMA busy_timeout=5000')
        cursor.close()

    return engine


def migrate(engine: Engine) -> None:
    """Bring the database schema up to what this version of the app expects."""
    config = Config()
    config.set_main_option('script_location', str(MIGRATIONS_DIR))
    known = {script.revision for script in ScriptDirectory.from_config(config).walk_revisions()}

    with engine.begin() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
        if current is not None and current not in known:
            raise UnknownRevisionError(current)

        # migrations/env.py picks the connection up from here.
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
