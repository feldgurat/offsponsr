import json
from collections.abc import Iterator
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, case, func, not_, select

from offsponsr.auth import NoLibraryError
from offsponsr.library import LibraryManager
from offsponsr.library.models import Post, PostStatus, Project
from offsponsr.media.downloader import DownloadService, DownloadState
from offsponsr.sync.events import Event, EventBus
from offsponsr.sync.service import SyncService, SyncState

# How often to send something down an idle event stream, so a dead connection gets noticed.
KEEPALIVE = 15.0


class ProjectInfo(BaseModel):
    id: int
    url: str
    title: str
    added_via: str
    sync_enabled: bool
    last_synced_at: datetime | None
    # Posts in the library, the ones deleted on the site included.
    posts: int
    # Readable posts whose whole text hasn't been downloaded yet.
    posts_without_text: int
    posts_deleted: int


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


def projects_router(
    libraries: LibraryManager,
    sync: SyncService,
    downloads: DownloadService,
    events: EventBus,
    keepalive: float = KEEPALIVE,
) -> APIRouter:
    router = APIRouter()

    @router.get('/projects')
    def projects() -> list[ProjectInfo]:
        library = libraries.current
        if library is None:
            raise NoLibraryError

        without_text = and_(Post.available, not_(Post.html_is_full))
        deleted = Post.status == PostStatus.DELETED_ON_SITE
        counts = (
            select(
                Post.project_id,
                func.count().label('posts'),
                func.sum(case((without_text, 1), else_=0)).label('without_text'),
                func.sum(case((deleted, 1), else_=0)).label('deleted'),
            )
            .group_by(Post.project_id)
            .subquery()
        )
        query = (
            select(Project, counts.c.posts, counts.c.without_text, counts.c.deleted)
            .outerjoin(counts, counts.c.project_id == Project.id)
            .order_by(Project.title)
        )
        with library.session() as db:
            return [
                ProjectInfo(
                    id=project.id,
                    url=project.url,
                    title=project.title,
                    added_via=project.added_via,
                    sync_enabled=project.sync_enabled,
                    last_synced_at=project.last_synced_at,
                    posts=posts or 0,
                    posts_without_text=without or 0,
                    posts_deleted=gone or 0,
                )
                for project, posts, without, gone in db.execute(query)
            ]

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

    @router.get('/downloads')
    def downloads_state() -> DownloadsInfo:
        return _downloads_info(downloads.state())

    @router.post('/downloads/cancel')
    def cancel_downloads() -> DownloadsInfo:
        return _downloads_info(downloads.cancel())

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
