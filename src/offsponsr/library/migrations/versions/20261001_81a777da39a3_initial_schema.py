"""initial schema

Revision ID: 81a777da39a3
Revises:
Create Date: 2026-10-01 11:53:32.141364
"""

import sqlalchemy as sa
from alembic import op

revision = '81a777da39a3'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'account',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('nickname', sa.String(length=255), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_account')),
    )
    op.create_table(
        'project',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('url', sa.String(length=255), nullable=False),
        sa.Column('title', sa.String(length=1024), nullable=False),
        sa.Column('intent', sa.Text(), nullable=True),
        sa.Column('description_html', sa.Text(), nullable=True),
        sa.Column('logo_path', sa.String(length=1024), nullable=True),
        sa.Column('cover_path', sa.String(length=1024), nullable=True),
        sa.Column(
            'added_via', sa.Enum('subscription', 'url', name='addedvia', native_enum=False, length=32), nullable=False
        ),
        sa.Column('sync_enabled', sa.Boolean(), nullable=False),
        sa.Column(
            'media_mode_audio',
            sa.Enum('auto', 'manual', name='mediamode', native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            'media_mode_video',
            sa.Enum('auto', 'manual', name='mediamode', native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            'media_mode_attach',
            sa.Enum('auto', 'manual', name='mediamode', native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column('video_quality', sa.Integer(), nullable=True),
        sa.Column('subscription_level_id', sa.Integer(), nullable=True),
        sa.Column('last_paid', sa.DateTime(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_project')),
        sa.UniqueConstraint('url', name=op.f('uq_project_url')),
    )
    op.create_table(
        'sync_run',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('scope', sa.String(length=255), nullable=False),
        sa.Column('stats_json', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_sync_run')),
    )
    op.create_table(
        'level',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=1024), nullable=False),
        sa.Column('price', sa.Integer(), nullable=True),
        sa.Column('description_html', sa.Text(), nullable=True),
        sa.Column('visible', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ['project_id'], ['project.id'], name=op.f('fk_level_project_id_project'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_level')),
    )
    with op.batch_alter_table('level', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_level_project_id'), ['project_id'], unique=False)

    op.create_table(
        'post',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('level_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('title', sa.String(length=1024), nullable=False),
        sa.Column('teaser', sa.Text(), nullable=True),
        sa.Column('html', sa.Text(), nullable=True),
        sa.Column('html_is_full', sa.Boolean(), nullable=False),
        sa.Column('available', sa.Boolean(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('active', 'deleted_on_site', 'unavailable', name='poststatus', native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column('updated_at_site', sa.DateTime(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), nullable=True),
        sa.Column('views', sa.Integer(), nullable=True),
        sa.Column('duration_text', sa.Integer(), nullable=True),
        sa.Column('duration_audio', sa.Integer(), nullable=True),
        sa.Column('duration_video', sa.Integer(), nullable=True),
        sa.Column('content_type', sa.String(length=64), nullable=True),
        sa.Column('pinned', sa.Boolean(), nullable=False),
        sa.Column('cover_path', sa.String(length=1024), nullable=True),
        sa.Column('raw_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ['project_id'], ['project.id'], name=op.f('fk_post_project_id_project'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_post')),
    )
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.create_index('ix_post_project_id_date', ['project_id', 'date'], unique=False)

    op.create_table(
        'tag',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=1024), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('image_path', sa.String(length=1024), nullable=True),
        sa.ForeignKeyConstraint(
            ['project_id'], ['project.id'], name=op.f('fk_tag_project_id_project'), ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tag')),
    )
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_tag_project_id'), ['project_id'], unique=False)

    op.create_table(
        'media',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('image', 'audio', 'video', 'attach', 'embed', name='mediakind', native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column('source_id', sa.String(length=255), nullable=True),
        sa.Column('source_url', sa.String(length=2048), nullable=True),
        sa.Column('title', sa.String(length=1024), nullable=True),
        sa.Column('size', sa.Integer(), nullable=True),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.Column(
            'state',
            sa.Enum(
                'pending',
                'queued',
                'downloading',
                'done',
                'error',
                'skipped',
                name='mediastate',
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column('local_path', sa.String(length=1024), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['post_id'], ['post.id'], name=op.f('fk_media_post_id_post'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_media')),
    )
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_post_id'), ['post_id'], unique=False)

    op.create_table(
        'post_tag',
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['post.id'], name=op.f('fk_post_tag_post_id_post'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], name=op.f('fk_post_tag_tag_id_tag'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('post_id', 'tag_id', name=op.f('pk_post_tag')),
    )
    with op.batch_alter_table('post_tag', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_post_tag_tag_id'), ['tag_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('post_tag', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_post_tag_tag_id'))

    op.drop_table('post_tag')
    with op.batch_alter_table('media', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_post_id'))

    op.drop_table('media')
    with op.batch_alter_table('tag', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tag_project_id'))

    op.drop_table('tag')
    with op.batch_alter_table('post', schema=None) as batch_op:
        batch_op.drop_index('ix_post_project_id_date')

    op.drop_table('post')
    with op.batch_alter_table('level', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_level_project_id'))

    op.drop_table('level')
    op.drop_table('sync_run')
    op.drop_table('project')
    op.drop_table('account')
