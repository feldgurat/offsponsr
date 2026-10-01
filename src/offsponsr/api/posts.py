"""Reading the library: a project's feed and a single post."""

from datetime import datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import ColumnElement, and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session

from offsponsr.api.urls import media_url, post_cover_url
from offsponsr.auth import NoLibraryError
from offsponsr.library import Library, LibraryManager
from offsponsr.library.models import Level, Media, MediaKind, MediaState, Post, PostStatus, PostTag, Project, Tag
from offsponsr.library.text import plain_text
from offsponsr.shell import is_openable
from offsponsr.sync.media import mark_media

# As many posts on a page as the site shows.
PER_PAGE = 20
# How much of a post's text the feed shows under its title.
EXCERPT_CHARS = 400

# A post the account can't read and the library has no text of.
CLOSED = and_(not_(Post.available), not_(Post.html_is_full))


class LevelInfo(BaseModel):
    id: int
    name: str
    # Roubles a month.
    price: int | None


class TagInfo(BaseModel):
    id: int
    name: str


class MediaInfo(BaseModel):
    id: int
    kind: str
    # What the site calls it: for audio and attachments, the id of the file.
    source_id: str | None
    # Where it lives on the web: the address of a picture or of a player frame.
    source_url: str | None
    title: str | None
    size: int | None
    duration: int | None
    state: str
    # The code of what went wrong, if the download failed.
    error: str | None
    # Where the UI loads the file from once it is in the library; never set for attachments.
    url: str | None
    file_name: str | None
    # Whether the downloaded file is of a kind the system may be asked to open (a document, not a program).
    can_open: bool


class PostCard(BaseModel):
    """A post as the feeds show it."""

    id: int
    project_id: int
    title: str
    date: datetime
    # The beginning of the text without markup.
    excerpt: str
    cover: str | None
    # The account can't read it and the library has no text of it.
    closed: bool
    # active, deleted_on_site, or unavailable for a text that was kept after the access was lost.
    status: str
    # False while the library has only the beginning of the text.
    text_is_full: bool
    level: LevelInfo | None
    # Seconds.
    duration_text: int | None
    duration_audio: int | None
    duration_video: int | None
    has_audio: bool
    has_video: bool
    pinned: bool
    tags: list[TagInfo]
    # The text with its pictures and players labelled (`data-media`), and what they are.
    # In the feeds only the stream view asks for these.
    html: str | None = None
    media: list[MediaInfo] = []


class FeedPage(BaseModel):
    total: int
    page: int
    per_page: int
    posts: list[PostCard]


class PostLink(BaseModel):
    id: int
    title: str


class ProjectLink(BaseModel):
    id: int
    url: str
    title: str


class PostDetails(PostCard):
    project: ProjectLink
    # The neighbours by date within the project.
    newer: PostLink | None
    older: PostLink | None


def _media_info(media: Media) -> MediaInfo:
    downloaded = media.state == MediaState.DONE and bool(media.local_path)
    return MediaInfo(
        id=media.id,
        kind=media.kind,
        source_id=media.source_id,
        source_url=media.source_url,
        title=media.title,
        size=media.size,
        duration=media.duration,
        state=media.state,
        error=media.error,
        url=media_url(media),
        file_name=PurePosixPath(media.local_path).name if downloaded else None,
        can_open=downloaded and is_openable(PurePosixPath(media.local_path or '')),
    )


def _has(kind: MediaKind) -> ColumnElement[bool]:
    return exists().where(Media.post_id == Post.id, Media.kind == kind)


def _cards(db: Session, posts: list[Post], *, with_text: bool) -> list[PostCard]:
    """Cards for the posts, with what they need looked up in a few queries for all of them."""
    if not posts:
        return []
    ids = [post.id for post in posts]

    levels = {level.id: level for level in db.scalars(select(Level).where(Level.id.in_({p.level_id for p in posts})))}
    tags: dict[int, list[TagInfo]] = {}
    tagged = select(PostTag.post_id, Tag.id, Tag.name).join(Tag, Tag.id == PostTag.tag_id)
    for post_id, tag_id, name in db.execute(tagged.where(PostTag.post_id.in_(ids)).order_by(Tag.name)):
        tags.setdefault(post_id, []).append(TagInfo(id=tag_id, name=name))
    media: dict[int, list[Media]] = {}
    for item in db.scalars(select(Media).where(Media.post_id.in_(ids)).order_by(Media.id)):
        media.setdefault(item.post_id, []).append(item)

    cards = []
    for post in posts:
        level = levels.get(post.level_id) if post.level_id is not None else None
        items = media.get(post.id, [])
        kinds = {item.kind for item in items}
        closed = not post.available and not post.html_is_full
        html = None
        if with_text and post.html and not closed:
            html = mark_media(post.html, {(item.kind, item.source_id or ''): item.id for item in items})
        cards.append(
            PostCard(
                id=post.id,
                project_id=post.project_id,
                title=post.title,
                date=post.date,
                excerpt=post.teaser or plain_text(post.html, EXCERPT_CHARS),
                cover=post_cover_url(post),
                closed=closed,
                status=post.status,
                text_is_full=post.html_is_full,
                level=LevelInfo(id=level.id, name=level.name, price=level.price) if level else None,
                duration_text=post.duration_text,
                duration_audio=post.duration_audio,
                duration_video=post.duration_video,
                has_audio=MediaKind.AUDIO in kinds or bool(post.duration_audio),
                has_video=MediaKind.VIDEO in kinds or bool(post.duration_video),
                pinned=post.pinned,
                tags=tags.get(post.id, []),
                html=html,
                media=[_media_info(item) for item in items] if with_text else [],
            )
        )
    return cards


def posts_router(libraries: LibraryManager) -> APIRouter:
    router = APIRouter()

    def open_library() -> Library:
        library = libraries.current
        if library is None:
            raise NoLibraryError
        return library

    @router.get('/projects/{project_id}/posts')
    def feed(
        project_id: int,
        *,
        page: Annotated[int, Query(ge=1)] = 1,
        order: Literal['desc', 'asc'] = 'desc',
        date_from: AwareDatetime | None = None,
        date_to: AwareDatetime | None = None,
        content: Literal['audio', 'video'] | None = None,
        hide_closed: bool = False,
        hide_deleted: bool = False,
        with_text: bool = False,
    ) -> FeedPage:
        """A page of the project's posts by date. `with_text` adds the texts, for the stream view."""
        conditions = [Post.project_id == project_id]
        if date_from is not None:
            conditions.append(Post.date >= date_from)
        if date_to is not None:
            conditions.append(Post.date <= date_to)
        if content == 'audio':
            conditions.append(or_(Post.duration_audio > 0, _has(MediaKind.AUDIO)))
        elif content == 'video':
            conditions.append(or_(Post.duration_video > 0, _has(MediaKind.VIDEO)))
        if hide_closed:
            conditions.append(not_(CLOSED))
        if hide_deleted:
            conditions.append(Post.status != PostStatus.DELETED_ON_SITE)

        by_date = (Post.date.desc(), Post.id.desc()) if order == 'desc' else (Post.date, Post.id)
        with open_library().session() as db:
            if db.get(Project, project_id) is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND)
            total = db.scalar(select(func.count()).select_from(Post).where(*conditions)) or 0
            rows = db.scalars(
                select(Post).where(*conditions).order_by(*by_date).limit(PER_PAGE).offset((page - 1) * PER_PAGE)
            ).all()
            cards = _cards(db, list(rows), with_text=with_text)
            return FeedPage(total=total, page=page, per_page=PER_PAGE, posts=cards)

    @router.get('/posts/{post_id}')
    def post(post_id: int) -> PostDetails:
        with open_library().session() as db:
            row = db.get(Post, post_id)
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND)
            [card] = _cards(db, [row], with_text=True)

            same_project = Post.project_id == row.project_id
            after = or_(Post.date > row.date, and_(Post.date == row.date, Post.id > row.id))
            before = or_(Post.date < row.date, and_(Post.date == row.date, Post.id < row.id))
            neighbour = select(Post.id, Post.title).where(same_project).limit(1)
            newer = db.execute(neighbour.where(after).order_by(Post.date, Post.id)).first()
            older = db.execute(neighbour.where(before).order_by(Post.date.desc(), Post.id.desc())).first()
            project = row.project
            return PostDetails(
                **card.model_dump(),
                project=ProjectLink(id=project.id, url=project.url, title=project.title),
                newer=PostLink(id=newer.id, title=newer.title) if newer else None,
                older=PostLink(id=older.id, title=older.title) if older else None,
            )

    return router
