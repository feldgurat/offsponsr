"""cover and logo addresses

Revision ID: e3147a69c07b
Revises: 81a777da39a3
Create Date: 2026-10-01 22:24:22.566406
"""

import sqlalchemy as sa
from alembic import op

revision = 'e3147a69c07b'
down_revision = '81a777da39a3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cover_url', sa.String(length=2048), nullable=True))

    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.add_column(sa.Column('logo_url', sa.String(length=2048), nullable=True))
        batch_op.add_column(sa.Column('cover_url', sa.String(length=2048), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('project', schema=None) as batch_op:
        batch_op.drop_column('cover_url')
        batch_op.drop_column('logo_url')

    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.drop_column('cover_url')
