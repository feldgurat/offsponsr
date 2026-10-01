from alembic import context
from sqlalchemy import create_engine

from offsponsr.library.models import Base, UtcDateTime

# Where the `alembic` command line keeps its scratch database when writing a new migration.
DEV_DATABASE_URL = 'sqlite:///.alembic-dev.db'


def render_item(type_, obj, autogen_context):
    # Migrations are frozen history, so they spell the column out instead of importing app code.
    if type_ == 'type' and isinstance(obj, UtcDateTime):
        return 'sa.DateTime()'
    return False


def run(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_item=render_item,
        # SQLite can't alter most things in place; batch mode rebuilds the table instead.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# The app hands over its own connection (see library/db.py); the command line doesn't.
app_connection = context.config.attributes.get('connection')
if app_connection is not None:
    run(app_connection)
else:
    with create_engine(DEV_DATABASE_URL).begin() as dev_connection:
        run(dev_connection)
