from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext

from offsponsr.library.db import migrate, open_engine
from offsponsr.library.models import Base


def test_migrations_produce_the_schema_the_models_describe(tmp_path):
    """Fails when models.py is changed without a migration to match."""
    engine = open_engine(tmp_path / 'offsponsr.db')
    try:
        migrate(engine)
        with engine.connect() as connection:
            context = MigrationContext.configure(connection, opts={'compare_type': True})
            differences = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert differences == []


def test_migrating_twice_changes_nothing(tmp_path):
    engine = open_engine(tmp_path / 'offsponsr.db')
    try:
        migrate(engine)
        migrate(engine)
        with engine.connect() as connection:
            revision = MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()

    assert revision is not None
