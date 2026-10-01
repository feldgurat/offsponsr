"""The library database schema. Changing it needs a migration, see migrations/."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, MetaData, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Aware datetimes in Python, naive UTC in the database: SQLite keeps no time zone."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Any) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError('A naive datetime was passed where an aware one is required')
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Any) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def _values(enum: type[StrEnum]) -> Enum:
    """A column type that stores the enum's values (not its member names) as plain text."""
    return Enum(enum, native_enum=False, length=32, values_callable=lambda members: [m.value for m in members])


class AddedVia(StrEnum):
    SUBSCRIPTION = 'subscription'
    URL = 'url'


class MediaMode(StrEnum):
    # Download with the sync.
    AUTO = 'auto'
    # Download when the user presses the button in the post.
    MANUAL = 'manual'


class PostStatus(StrEnum):
    ACTIVE = 'active'
    DELETED_ON_SITE = 'deleted_on_site'
    # Was readable, isn't any more (the subscription ended or its level dropped).
    UNAVAILABLE = 'unavailable'


class MediaKind(StrEnum):
    IMAGE = 'image'
    AUDIO = 'audio'
    VIDEO = 'video'
    ATTACH = 'attach'
    # A third-party player (YouTube etc.); shown online, never downloaded.
    EMBED = 'embed'


class MediaState(StrEnum):
    PENDING = 'pending'
    QUEUED = 'queued'
    DOWNLOADING = 'downloading'
    DONE = 'done'
    ERROR = 'error'
    SKIPPED = 'skipped'


class Base(DeclarativeBase):
    # Named constraints, so migrations can refer to them.
    metadata = MetaData(
        naming_convention={
            'ix': 'ix_%(column_0_label)s',
            'uq': 'uq_%(table_name)s_%(column_0_name)s',
            'ck': 'ck_%(table_name)s_%(constraint_name)s',
            'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
            'pk': 'pk_%(table_name)s',
        }
    )
    type_annotation_map = {  # noqa: RUF012
        datetime: UtcDateTime,
        dict[str, Any]: JSON,
    }


# Projects, levels, posts and tags use the ids sponsr.ru gives them as primary keys.
# All *_path columns are relative to the library root, so the library can be moved.
#
# The relationships to the parent row are there for more than navigation: they tell the
# session to insert parents before children, which the foreign keys require.


class Account(Base):
    __tablename__ = 'account'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None]
    nickname: Mapped[str | None] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None]


class Project(Base):
    __tablename__ = 'project'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    # The project's address on the site: sponsr.ru/{url}/
    url: Mapped[str] = mapped_column(String(255), unique=True)
    title: Mapped[str] = mapped_column(String(1024))
    intent: Mapped[str | None] = mapped_column(Text)
    description_html: Mapped[str | None] = mapped_column(Text)
    # Where the site keeps the logo and the cover (paths on its media host), and the copies
    # in the library once they are downloaded.
    logo_url: Mapped[str | None] = mapped_column(String(2048))
    cover_url: Mapped[str | None] = mapped_column(String(2048))
    logo_path: Mapped[str | None] = mapped_column(String(1024))
    cover_path: Mapped[str | None] = mapped_column(String(1024))
    added_via: Mapped[AddedVia] = mapped_column(_values(AddedVia))
    sync_enabled: Mapped[bool] = mapped_column(default=True)
    media_mode_audio: Mapped[MediaMode] = mapped_column(_values(MediaMode))
    media_mode_video: Mapped[MediaMode] = mapped_column(_values(MediaMode))
    media_mode_attach: Mapped[MediaMode] = mapped_column(_values(MediaMode))
    # The tallest video to download, in pixels; None means the best there is.
    video_quality: Mapped[int | None]
    # Not a foreign key: the user's level may be one the project no longer lists.
    subscription_level_id: Mapped[int | None]
    last_paid: Mapped[datetime | None]
    last_synced_at: Mapped[datetime | None]
    raw_json: Mapped[dict[str, Any] | None]


class Level(Base):
    __tablename__ = 'level'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    project_id: Mapped[int] = mapped_column(ForeignKey('project.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(1024))
    price: Mapped[int | None]
    description_html: Mapped[str | None] = mapped_column(Text)
    visible: Mapped[bool] = mapped_column(default=True)

    project: Mapped[Project] = relationship()


class Post(Base):
    __tablename__ = 'post'
    __table_args__ = (Index('ix_post_project_id_date', 'project_id', 'date'),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    project_id: Mapped[int] = mapped_column(ForeignKey('project.id', ondelete='CASCADE'))
    # Not a foreign key: a post may point at a level the project no longer lists.
    level_id: Mapped[int | None]
    date: Mapped[datetime]
    title: Mapped[str] = mapped_column(String(1024))
    teaser: Mapped[str | None] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    # False while `html` holds only the truncated text from the post list.
    html_is_full: Mapped[bool] = mapped_column(default=False)
    # Whether the account could read the post at the last sync.
    available: Mapped[bool]
    status: Mapped[PostStatus] = mapped_column(_values(PostStatus), default=PostStatus.ACTIVE)
    updated_at_site: Mapped[datetime | None]
    # When the full text was last downloaded.
    fetched_at: Mapped[datetime | None]
    views: Mapped[int | None]
    duration_text: Mapped[int | None]
    duration_audio: Mapped[int | None]
    duration_video: Mapped[int | None]
    content_type: Mapped[str | None] = mapped_column(String(64))
    pinned: Mapped[bool] = mapped_column(default=False)
    # The post's cover picture: where the site keeps it, and the copy in the library.
    cover_url: Mapped[str | None] = mapped_column(String(2048))
    cover_path: Mapped[str | None] = mapped_column(String(1024))
    raw_json: Mapped[dict[str, Any] | None]

    project: Mapped[Project] = relationship()


class Tag(Base):
    """A tag; the site shows tags as collections."""

    __tablename__ = 'tag'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    project_id: Mapped[int] = mapped_column(ForeignKey('project.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(1024))
    count: Mapped[int] = mapped_column(default=0)
    image_path: Mapped[str | None] = mapped_column(String(1024))

    project: Mapped[Project] = relationship()


class PostTag(Base):
    __tablename__ = 'post_tag'

    post_id: Mapped[int] = mapped_column(ForeignKey('post.id', ondelete='CASCADE'), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey('tag.id', ondelete='CASCADE'), primary_key=True, index=True)

    post: Mapped[Post] = relationship()
    tag: Mapped[Tag] = relationship()


class Media(Base):
    __tablename__ = 'media'

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey('post.id', ondelete='CASCADE'), index=True)
    kind: Mapped[MediaKind] = mapped_column(_values(MediaKind))
    # What the site calls it: a file id, an image id, a Kinescope video UUID.
    source_id: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(1024))
    size: Mapped[int | None]
    duration: Mapped[int | None]
    state: Mapped[MediaState] = mapped_column(_values(MediaState), default=MediaState.PENDING)
    local_path: Mapped[str | None] = mapped_column(String(1024))
    error: Mapped[str | None] = mapped_column(Text)

    post: Mapped[Post] = relationship()


class SyncRun(Base):
    __tablename__ = 'sync_run'

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime | None]
    scope: Mapped[str] = mapped_column(String(255))
    stats_json: Mapped[dict[str, Any] | None]
    error: Mapped[str | None] = mapped_column(Text)
