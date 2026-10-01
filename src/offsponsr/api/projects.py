import json
from collections.abc import Iterator
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, case, func, not_, select
from sqlalchemy.orm import Session

from offsponsr.api.posts import CLOSED
from offsponsr.api.urls import project_cover_url, project_logo_url
from offsponsr.auth import NoLibraryError
from offsponsr.library import Library, LibraryManager
from offsponsr.library.models import Media, MediaKind, MediaMode, MediaState, Post, PostStatus, Project, SyncRun
from offsponsr.media.downloader import DownloadService, DownloadState
from offsponsr.sync.events import Event, EventBus
from offsponsr.sync.service import SyncService, SyncState

# How often to send something down an idle event stream, so a dead connection gets noticed.
KEEPALIVE = 15.0

# How many of the latest sync runs and of the failed downloads the UI is shown.
HISTORY_LIMIT = 30
FAILED_LIMIT = 100


class ProjectInfo(BaseModel):
    id: int
    url: str
    title: str
    intent: str | None
    # Addresses of the pictures: the copies in the library once they are downloaded.
    logo: str | None
    cover: str | None
    added_via: str
    sync_enabled: bool
    media_mode_audio: MediaMode
    media_mode_video: MediaMode
    media_mode_attach: MediaMode
    # The tallest video to download, in pixels; None is the best there is.
    video_quality: int | None
    last_synced_at: datetime | None
    # Posts in the library, the ones deleted on the site included.
    posts: int
    # Readable posts whose whole text hasn't been downloaded yet.
    posts_without_text: int
    posts_deleted: int
    # Posts the account can't read.
    posts_closed: int


class ProjectSettings(BaseModel):
    """What can be changed about a project; a field left out stays as it is."""

    sync_enabled: bool | None = None
    media_mode_audio: MediaMode | None = None
    media_mode_video: MediaMode | None = None
    media_mode_attach: MediaMode | None = None
    # Sent as null, it means the best quality.
    video_quality: Literal[1080, 720, 480, 360] | None = None


class PendingMedia(BaseModel):
    """Known files of the kinds just switched to downloading right away that are not in the library."""

    files: int
    # The sizes that are known added up; videos don't tell theirs in advance.
    bytes: int
    files_without_size: int


class ProjectUpdate(BaseModel):
    project: ProjectInfo
    to_download: PendingMedia


class SyncRunInfo(BaseModel):
    id: int
    project_id: int | None
    title: str | None
    started_at: datetime
    finished_at: datetime | None
    # ok, cancelled, failed, or unfinished for a run the app was closed in the middle of.
    outcome: str
    # Whether the whole list of posts was read, not just its beginning.
    full: bool
    posts_new: int
    posts_changed: int
    posts_deleted: int


class FailedDownload(BaseModel):
    media_id: int
    kind: str
    title: str | None
    # The error's code; the UI has a message for each.
    error: str | None
    post_id: int
    post_title: str
    project_id: int


class FailedDownloads(BaseModel):
    total: int
    # The latest ones, at most FAILED_LIMIT.
    items: list[FailedDownload]


class SubscriptionInfo(BaseModel):
    id: int
    url: str
    title: str
    owner_name: str | None
    level_name: str | None
    in_library: bool


class AddProjects(BaseModel):
    subscription_ids: list[int] = []
    # A link to a project or its name on the site, for projects outside the subscriptions.
    address: str | None = None


class AddedProjects(BaseModel):
    added: list[int]


class StartSync(BaseModel):
    # None: every project that has syncing switched on.
    project_ids: list[int] | None = None


class RunningSyncInfo(BaseModel):
    project_id: int
    title: str
    posts_done: int
    posts_total: int | None


class SyncFailureInfo(BaseModel):
    project_id: int
    title: str
    code: str


class SyncInfo(BaseModel):
    running: RunningSyncInfo | None
    queue: list[int]
    failures: list[SyncFailureInfo]
    cancelling: bool


class ActiveDownloadInfo(BaseModel):
    key: str
    title: str
    bytes_done: int
    bytes_total: int | None


class DownloadsInfo(BaseModel):
    active: list[ActiveDownloadInfo]
    queued: int
    done: int
    failed: int
    cancelling: bool


class QueuedDownloads(BaseModel):
    queued: int


def _sync_info(state: SyncState) -> SyncInfo:
    return SyncInfo.model_validate(state.to_json())


def _downloads_info(state: DownloadState) -> DownloadsInfo:
    return DownloadsInfo.model_validate(state.to_json())


def _sse(event: Event) -> str:
    return f'data: {json.dumps(event, ensure_ascii=False)}\n\n'


def project_infos(db: Session, project_id: int | None = None) -> list[ProjectInfo]:
    """The library's projects with their post counts, by title; or just the one asked for."""
    without_text = and_(Post.available, not_(Post.html_is_full))
    deleted = Post.status == PostStatus.DELETED_ON_SITE
    counts = (
        select(
            Post.project_id,
            func.count().label('posts'),
            func.sum(case((without_text, 1), else_=0)).label('without_text'),
            func.sum(case((deleted, 1), else_=0)).label('deleted'),
            func.sum(case((CLOSED, 1), else_=0)).label('closed'),
        )
        .group_by(Post.project_id)
        .subquery()
    )
    query = (
        select(Project, counts.c.posts, counts.c.without_text, counts.c.deleted, counts.c.closed)
        .outerjoin(counts, counts.c.project_id == Project.id)
        .order_by(Project.title)
    )
    if project_id is not None:
        query = query.where(Project.id == project_id)
    return [
        ProjectInfo(
            id=project.id,
            url=project.url,
            title=project.title,
            intent=project.intent,
            logo=project_logo_url(project),
            cover=project_cover_url(project),
            added_via=project.added_via,
            sync_enabled=project.sync_enabled,
            media_mode_audio=project.media_mode_audio,
            media_mode_video=project.media_mode_video,
            media_mode_attach=project.media_mode_attach,
            video_quality=project.video_quality,
            last_synced_at=project.last_synced_at,
            posts=posts or 0,
            posts_without_text=without or 0,
            posts_deleted=gone or 0,
            posts_closed=closed or 0,
        )
        for project, posts, without, gone, closed in db.execute(query)
    ]


def _outcome(run: SyncRun) -> str:
    if run.finished_at is None:
        return 'unfinished'
    if run.error is None:
        return 'ok'
    return 'cancelled' if run.error == 'SyncCancelled' else 'failed'


def projects_router(
    libraries: LibraryManager,
    sync: SyncService,
    downloads: DownloadService,
    events: EventBus,
    keepalive: float = KEEPALIVE,
) -> APIRouter:
    router = APIRouter()

    def open_library() -> Library:
        library = libraries.current
        if library is None:
            raise NoLibraryError
        return library

    @router.get('/projects')
    def projects() -> list[ProjectInfo]:
        with open_library().session() as db:
            return project_infos(db)

    @router.get('/projects/{project_id}')
    def project(project_id: int) -> ProjectInfo:
        with open_library().session() as db:
            found = project_infos(db, project_id)
        if not found:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return found[0]

    @router.patch('/projects/{project_id}')
    def change_project(project_id: int, body: ProjectSettings) -> ProjectUpdate:
        """Change the project's settings. Nothing is downloaded by this: the UI asks the user first."""
        with open_library().session() as db:
            row = db.get(Project, project_id)
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND)

            if body.sync_enabled is not None:
                row.sync_enabled = body.sync_enabled
            if 'video_quality' in body.model_fields_set:
                row.video_quality = body.video_quality
            switched_on = []
            for kind, name in (
                (MediaKind.AUDIO, 'media_mode_audio'),
                (MediaKind.VIDEO, 'media_mode_video'),
                (MediaKind.ATTACH, 'media_mode_attach'),
            ):
                mode = getattr(body, name)
                if mode is None:
                    continue
                if mode == MediaMode.AUTO and getattr(row, name) != MediaMode.AUTO:
                    switched_on.append(kind)
                setattr(row, name, mode)
            db.commit()

            files, known, sized = 0, 0, 0
            if switched_on:
                waiting = (
                    select(func.count(), func.coalesce(func.sum(Media.size), 0), func.count(Media.size))
                    .join(Post, Media.post_id == Post.id)
                    .where(
                        Post.project_id == project_id,
                        Media.kind.in_(switched_on),
                        Media.state.in_((MediaState.PENDING, MediaState.ERROR)),
                    )
                )
                files, known, sized = db.execute(waiting).one()
            [info] = project_infos(db, project_id)
        events.publish({'type': 'projects'})
        return ProjectUpdate(
            project=info, to_download=PendingMedia(files=files, bytes=known, files_without_size=files - sized)
        )

    @router.get('/subscriptions')
    def subscriptions() -> list[SubscriptionInfo]:
        return [SubscriptionInfo.model_validate(choice, from_attributes=True) for choice in sync.subscriptions()]

    @router.post('/projects')
    def add_projects(body: AddProjects) -> AddedProjects:
        return AddedProjects(added=sync.add_projects(body.subscription_ids, body.address))

    @router.get('/sync')
    def sync_state() -> SyncInfo:
        return _sync_info(sync.state())

    @router.post('/sync')
    def start_sync(body: StartSync) -> SyncInfo:
        return _sync_info(sync.start(body.project_ids))

    @router.post('/sync/cancel')
    def cancel_sync() -> SyncInfo:
        return _sync_info(sync.cancel())

    @router.get('/sync/history')
    def sync_history() -> list[SyncRunInfo]:
        """The latest sync runs, newest first."""
        with open_library().session() as db:
            titles = {row.id: row.title for row in db.execute(select(Project.id, Project.title))}
            runs = db.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(HISTORY_LIMIT)).all()
            history = []
            for run in runs:
                # The scope is `project:<id>`.
                tail = run.scope.rpartition(':')[2]
                project_id = int(tail) if tail.isdigit() else None
                stats = run.stats_json or {}
                history.append(
                    SyncRunInfo(
                        id=run.id,
                        project_id=project_id,
                        title=titles.get(project_id) if project_id is not None else None,
                        started_at=run.started_at,
                        finished_at=run.finished_at,
                        outcome=_outcome(run),
                        full=bool(stats.get('full')),
                        posts_new=stats.get('posts_new', 0),
                        posts_changed=stats.get('posts_changed', 0),
                        posts_deleted=stats.get('posts_deleted', 0),
                    )
                )
            return history

    @router.get('/downloads')
    def downloads_state() -> DownloadsInfo:
        return _downloads_info(downloads.state())

    @router.post('/downloads/cancel')
    def cancel_downloads() -> DownloadsInfo:
        return _downloads_info(downloads.cancel())

    @router.get('/downloads/failed')
    def failed_downloads() -> FailedDownloads:
        """Files whose download failed and hasn't been tried again since."""
        failed = Media.state == MediaState.ERROR
        with open_library().session() as db:
            total = db.scalar(select(func.count()).select_from(Media).where(failed)) or 0
            rows = db.execute(
                select(Media, Post.title, Post.project_id)
                .join(Post, Media.post_id == Post.id)
                .where(failed)
                .order_by(Post.date.desc(), Media.id)
                .limit(FAILED_LIMIT)
            )
            items = [
                FailedDownload(
                    media_id=media.id,
                    kind=media.kind,
                    title=media.title,
                    error=media.error,
                    post_id=media.post_id,
                    post_title=post_title,
                    project_id=project_id,
                )
                for media, post_title, project_id in rows
            ]
        return FailedDownloads(total=total, items=items)

    @router.post('/downloads/retry')
    def retry_downloads() -> QueuedDownloads:
        return QueuedDownloads(queued=downloads.enqueue_failed())

    @router.post('/projects/{project_id}/download')
    def download_project_media(project_id: int) -> QueuedDownloads:
        """Queue what the project is missing on disk; the same thing a sync does when it ends."""
        return QueuedDownloads(queued=downloads.enqueue_project(project_id))

    @router.post('/media/{media_id}/download')
    def download_media(media_id: int) -> QueuedDownloads:
        """Queue one file the user asked for, e.g. a video that isn't downloaded by itself."""
        return QueuedDownloads(queued=downloads.enqueue_media(media_id))

    @router.get('/events')
    def event_stream() -> StreamingResponse:
        """Server-sent events: the sync's state whenever it changes, and a nudge when the projects do."""
        listener = events.subscribe()

        def stream() -> Iterator[str]:
            try:
                # Where things stand right now, so a listener never starts out of date.
                yield _sse({'type': 'sync', 'state': sync.state().to_json()})
                yield _sse({'type': 'downloads', 'state': downloads.state().to_json()})
                while True:
                    try:
                        event = listener.get(keepalive)
                    except EOFError:
                        return
                    yield ': keepalive\n\n' if event is None else _sse(event)
            finally:
                listener.close()

        return StreamingResponse(stream(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache'})

    return router
