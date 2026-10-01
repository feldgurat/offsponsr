"""Downloads the media of the library's posts in the background: pictures, audio, attachments, video."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlsplit

import requests
from sqlalchemy import select, update

from offsponsr.auth.errors import AuthError
from offsponsr.auth.session import SITE, USER_AGENT
from offsponsr.library.models import Media, MediaKind, MediaMode, MediaState, Post, Project
from offsponsr.library.paths import (
    ATTACHMENTS_DIR,
    AUDIO_DIR,
    IMAGES_DIR,
    MAX_MEDIA_NAME_CHARS,
    VIDEO_DIR,
    post_folder,
    project_assets_folder,
    safe_name,
    unique_name,
)
from offsponsr.media import kinescope
from offsponsr.media.ffmpeg import FfmpegError, find_ffmpeg
from offsponsr.media.files import DownloadCancelled, DownloadError, fetch

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sqlalchemy.orm import Session

    from offsponsr.auth import AccountService
    from offsponsr.library import Library, LibraryManager
    from offsponsr.sync.events import EventBus

log = logging.getLogger(__name__)

# Where the site serves pictures and files from.
MEDIA_HOST = 'https://media.sponsr.ru'

# How many files are downloaded at the same time.
WORKERS = 2
# The UI hears about bytes arriving no more often than this, in seconds.
PROGRESS_INTERVAL = 0.5

_IMAGE_ID = re.compile(r'/image/(\d+)/')

_SUBFOLDERS = {
    MediaKind.IMAGE: IMAGES_DIR,
    MediaKind.AUDIO: AUDIO_DIR,
    MediaKind.VIDEO: VIDEO_DIR,
    MediaKind.ATTACH: ATTACHMENTS_DIR,
}
# States a file can be picked up from: never tried, left over from a run that was cut short, failed.
_WAITING = (MediaState.PENDING, MediaState.QUEUED, MediaState.DOWNLOADING, MediaState.ERROR)

MEDIA = 'media'
POST_COVER = 'post_cover'
PROJECT_LOGO = 'project_logo'
PROJECT_COVER = 'project_cover'

# The error of a video that could not be put together for the lack of ffmpeg.
NO_FFMPEG = 'no_ffmpeg'


@dataclass(frozen=True)
class Task:
    # MEDIA, POST_COVER, PROJECT_LOGO or PROJECT_COVER.
    kind: str
    # The id of the media row, the post or the project.
    id: int

    @property
    def key(self) -> str:
        return f'{self.kind}-{self.id}'


@dataclass(frozen=True)
class ActiveDownload:
    key: str
    title: str
    bytes_done: int = 0
    # None while the size is not known.
    bytes_total: int | None = None


@dataclass(frozen=True)
class DownloadState:
    active: tuple[ActiveDownload, ...] = ()
    queued: int = 0
    # Since the queue last started from empty.
    done: int = 0
    failed: int = 0
    cancelling: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            'active': [asdict(download) for download in self.active],
            'queued': self.queued,
            'done': self.done,
            'failed': self.failed,
            'cancelling': self.cancelling,
        }


def file_url(project_id: int, post_id: int, file_id: str) -> str:
    """Where the site serves a post's audio or attachment from (only to a signed-in account)."""
    return f'{MEDIA_HOST}/project/{project_id}/post/{post_id}/file/{file_id}/'


def site_url(path: str) -> str:
    """A full address from what the site gives for logos and covers: a path on its media host."""
    return path if '://' in path else f'{MEDIA_HOST}{path}'


def picture_url(address: str) -> str:
    """The full address of a picture in a post's text; one without a host belongs to the site."""
    url = urljoin(f'{SITE}/', address)
    if urlsplit(url).scheme not in ('http', 'https'):
        raise DownloadError('not_found', f'Not an address to download from: {address[:80]}')
    return url


def _suffix(url: str, default: str = '') -> str:
    suffix = PurePosixPath(urlsplit(url).path).suffix.lower()
    return suffix if 1 < len(suffix) <= 6 else default


def _media_name(media: Media, post_title: str) -> str:
    url = media.source_url or ''
    if media.kind == MediaKind.IMAGE:
        image_id = _IMAGE_ID.search(url)
        stem = image_id.group(1) if image_id else PurePosixPath(urlsplit(url).path).stem
        return safe_name(f'{stem}{_suffix(url, ".jpg")}', MAX_MEDIA_NAME_CHARS)
    if media.kind == MediaKind.VIDEO:
        return safe_name(f'{post_title}.mp4', MAX_MEDIA_NAME_CHARS)
    suffix = _suffix(url)
    title = media.title or PurePosixPath(urlsplit(url).path).stem
    name = title if suffix and title.lower().endswith(suffix) else f'{title}{suffix}'
    return safe_name(name, MAX_MEDIA_NAME_CHARS)


class DownloadService:
    def __init__(
        self,
        libraries: LibraryManager,
        account: AccountService,
        events: EventBus,
        *,
        workers: int = WORKERS,
        ffmpeg: Callable[[], Path | None] = find_ffmpeg,
    ) -> None:
        self._libraries = libraries
        self._account = account
        self._events = events
        self._max_workers = workers
        self._find_ffmpeg = ffmpeg
        # For what anybody may fetch: pictures, logos, video. Files of posts go by the account's session.
        self._public = requests.Session()
        self._public.headers['User-Agent'] = USER_AGENT

        self._lock = threading.Lock()
        self._queue: deque[Task] = deque()
        self._queued_keys: set[str] = set()
        self._active: dict[str, ActiveDownload] = {}
        self._done = 0
        self._failed = 0
        self._stop = threading.Event()
        self._workers: list[threading.Thread] = []
        self._last_announced = 0.0
        # Destinations of the downloads in flight (lower-cased), so that two files being fetched
        # at the same time never settle on the same name.
        self._paths_lock = threading.Lock()
        self._reserved: set[str] = set()

    def state(self) -> DownloadState:
        with self._lock:
            return self._state_locked()

    def _state_locked(self) -> DownloadState:
        return DownloadState(
            active=tuple(self._active.values()),
            queued=len(self._queue),
            done=self._done,
            failed=self._failed,
            cancelling=self._stop.is_set() and bool(self._active),
        )

    def is_busy(self) -> bool:
        with self._lock:
            return bool(self._queue or self._active)

    def enqueue_project(self, project_id: int) -> int:
        """Queue what the project should have on disk and hasn't: pictures always, the rest by its settings."""
        library = self._libraries.current
        if library is None:
            return 0

        tasks: list[Task] = []
        with library.session() as db:
            project = db.get(Project, project_id)
            if project is None:
                return 0
            if project.logo_url and not project.logo_path:
                tasks.append(Task(PROJECT_LOGO, project_id))
            if project.cover_url and not project.cover_path:
                tasks.append(Task(PROJECT_COVER, project_id))
            covers = select(Post.id).where(
                Post.project_id == project_id, Post.cover_url.is_not(None), Post.cover_path.is_(None)
            )
            tasks += [Task(POST_COVER, post_id) for post_id in db.scalars(covers)]

            kinds = [MediaKind.IMAGE]
            if project.media_mode_audio == MediaMode.AUTO:
                kinds.append(MediaKind.AUDIO)
            if project.media_mode_attach == MediaMode.AUTO:
                kinds.append(MediaKind.ATTACH)
            if project.media_mode_video == MediaMode.AUTO:
                kinds.append(MediaKind.VIDEO)
            wanted = (
                select(Media.id)
                .join(Post, Media.post_id == Post.id)
                .where(Post.project_id == project_id, Media.kind.in_(kinds), Media.state.in_(_WAITING))
                .order_by(Post.date.desc(), Media.id)
            )
            media_ids = list(db.scalars(wanted))
            tasks += [Task(MEDIA, media_id) for media_id in media_ids]
            self._mark_queued(db, media_ids)
            db.commit()
        return self._enqueue(library, tasks)

    def enqueue_media(self, media_id: int) -> int:
        """Queue one file, whatever its project's settings say: the user asked for it."""
        library = self._libraries.current
        if library is None:
            return 0
        with library.session() as db:
            media = db.get(Media, media_id)
            if media is None or media.kind == MediaKind.EMBED or media.state == MediaState.DONE:
                return 0
            self._mark_queued(db, [media_id])
            db.commit()
        return self._enqueue(library, [Task(MEDIA, media_id)])

    def enqueue_failed(self, error: str | None = None) -> int:
        """Queue again every file whose download failed, or only those that failed with `error`."""
        library = self._libraries.current
        if library is None:
            return 0
        with library.session() as db:
            failed = select(Media.id).where(Media.state == MediaState.ERROR, Media.kind != MediaKind.EMBED)
            if error is not None:
                failed = failed.where(Media.error == error)
            media_ids = list(db.scalars(failed.order_by(Media.id)))
            self._mark_queued(db, media_ids)
            db.commit()
        for media_id in media_ids:
            # A page showing the file as failed reads its row again.
            self._events.publish({'type': 'file', 'kind': MEDIA, 'id': media_id})
        return self._enqueue(library, [Task(MEDIA, media_id) for media_id in media_ids])

    @staticmethod
    def _mark_queued(db: Session, media_ids: list[int]) -> None:
        # In portions: SQLite takes a limited number of values in one statement.
        for start in range(0, len(media_ids), 500):
            portion = media_ids[start : start + 500]
            db.execute(update(Media).where(Media.id.in_(portion)).values(state=MediaState.QUEUED, error=None))

    def _enqueue(self, library: Library, tasks: list[Task]) -> int:
        if not tasks:
            return 0
        with self._lock:
            if not self._queue and not self._active:
                # A new batch: the counters start over.
                self._done = self._failed = 0
                self._stop.clear()
            added = 0
            for task in tasks:
                if task.key not in self._queued_keys and task.key not in self._active:
                    self._queue.append(task)
                    self._queued_keys.add(task.key)
                    added += 1
            self._workers = [worker for worker in self._workers if worker.is_alive()]
            while self._queue and len(self._workers) < min(self._max_workers, len(self._queue)):
                worker = threading.Thread(
                    target=self._work, args=(library,), name=f'offsponsr-download-{len(self._workers)}', daemon=True
                )
                self._workers.append(worker)
                worker.start()
        self._announce(force=True)
        return added

    def cancel(self) -> DownloadState:
        """Stop the downloads in flight and drop the queue. What is half-done continues next time."""
        library = self._libraries.current
        with self._lock:
            dropped = [task.id for task in self._queue if task.kind == MEDIA]
            self._queue.clear()
            self._queued_keys.clear()
            if self._active:
                self._stop.set()
        if library is not None and dropped:
            with library.session() as db:
                for start in range(0, len(dropped), 500):
                    portion = dropped[start : start + 500]
                    db.execute(update(Media).where(Media.id.in_(portion)).values(state=MediaState.PENDING))
                db.commit()
        self._announce(force=True)
        return self.state()

    def shutdown(self, timeout: float = 10) -> None:
        """Stop the workers and wait for them; called before the library is closed."""
        with self._lock:
            self._queue.clear()
            self._queued_keys.clear()
            self._stop.set()
            workers = list(self._workers)
        for worker in workers:
            worker.join(timeout)

    def _announce(self, *, force: bool = False) -> None:
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_announced < PROGRESS_INTERVAL:
                return
            self._last_announced = now
            state = self._state_locked()
        self._events.publish({'type': 'downloads', 'state': state.to_json()})

    def _work(self, library: Library) -> None:
        while True:
            with self._lock:
                if self._stop.is_set() or not self._queue:
                    return
                task = self._queue.popleft()
                self._queued_keys.discard(task.key)
                self._active[task.key] = ActiveDownload(task.key, '')
            try:
                succeeded = self._run(library, task)
            except Exception:
                log.exception('Download %s failed', task.key)
                succeeded = False
            with self._lock:
                del self._active[task.key]
                if succeeded is True:
                    self._done += 1
                elif succeeded is False:
                    self._failed += 1
                if not self._active and not self._queue:
                    # The last one out clears the stop flag, so the next batch can start.
                    self._stop.clear()
            # Whoever shows this very file (a post's page, a feed) learns that its state has changed.
            self._events.publish({'type': 'file', 'kind': task.kind, 'id': task.id})
            self._announce(force=True)

    def _progress(self, task: Task, title: str) -> Callable[[int, int | None], None]:
        def report(done: int, total: int | None, *, force: bool = False) -> None:
            with self._lock:
                if task.key in self._active:
                    self._active[task.key] = ActiveDownload(task.key, title, done, total)
            self._announce(force=force)

        # The start of a download is always announced; the bytes arriving, only now and then.
        report(0, None, force=True)
        return report

    def _run(self, library: Library, task: Task) -> bool | None:
        """Download one thing. True: done, False: failed, None: cancelled."""
        if task.kind == MEDIA:
            return self._run_media(library, task)
        return self._run_asset(library, task)

    def _run_media(self, library: Library, task: Task) -> bool | None:
        with self._paths_lock, library.session() as db:
            media = db.get(Media, task.id)
            if media is None or media.state == MediaState.DONE:
                return None
            post = media.post
            project = post.project
            relative = self._media_path(db, media, post, project)
            self._reserved.add(str(relative).lower())
            kind, source_url, source_id = media.kind, media.source_url or '', media.source_id or ''
            title = media.title or post.title
            project_id, post_id, max_height = project.id, post.id, project.video_quality
            media.state = MediaState.DOWNLOADING
            db.commit()
        try:
            return self._download_media(
                library, task, relative, kind, source_url, title, file_url(project_id, post_id, source_id), max_height
            )
        finally:
            # By now the name is either in the database or free again.
            self._reserved.discard(str(relative).lower())

    def _download_media(
        self,
        library: Library,
        task: Task,
        relative: PurePosixPath,
        kind: MediaKind,
        source_url: str,
        title: str,
        file_address: str,
        max_height: int | None,
    ) -> bool | None:
        report = self._progress(task, title)
        dest = library.file(relative)
        part = library.tmp_dir / f'{task.key}.part'
        error = None
        try:
            if kind == MediaKind.VIDEO:
                ffmpeg = self._find_ffmpeg()
                if ffmpeg is None:
                    raise DownloadError(NO_FFMPEG)
                kinescope.download(
                    self._public,
                    source_url,
                    dest,
                    work_dir=library.tmp_dir,
                    work_name=task.key,
                    ffmpeg=ffmpeg,
                    max_height=max_height,
                    on_progress=report,
                    should_stop=self._stop.is_set,
                )
            else:
                if kind == MediaKind.IMAGE:
                    http, url = self._public, picture_url(source_url)
                else:
                    http, url = self._account.http(), file_address
                self._fetch_to(http, url, part, dest, report)
        except DownloadCancelled:
            self._finish_media(library, task.id, MediaState.PENDING)
            return None
        except DownloadError as failure:
            error = failure.code
            log.warning('Download %s failed: %s', task.key, failure)
        except AuthError as failure:
            error = failure.code
        except FfmpegError as failure:
            error = 'ffmpeg_failed'
            log.warning('ffmpeg failed on %s: %s', task.key, failure)
        except OSError as failure:
            error = 'disk_error'
            log.warning('Could not write %s: %s', task.key, failure)

        if error is not None:
            self._finish_media(library, task.id, MediaState.ERROR, error=error)
            return False
        self._finish_media(library, task.id, MediaState.DONE, local_path=str(relative), size=dest.stat().st_size)
        return True

    def _fetch_to(
        self,
        http: requests.Session,
        url: str,
        part: Path,
        dest: Path,
        report: Callable[[int, int | None], None],
        total: int | None = None,
    ) -> None:
        got = part.stat().st_size if part.exists() else 0

        def on_bytes(count: int) -> None:
            nonlocal got
            got += count
            report(got, total)

        part.parent.mkdir(parents=True, exist_ok=True)
        fetch(http, url, part, on_bytes=on_bytes, should_stop=self._stop.is_set)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part.replace(dest)

    @staticmethod
    def _finish_media(library: Library, media_id: int, state: MediaState, **fields: object) -> None:
        with library.session() as db:
            media = db.get(Media, media_id)
            if media is None:
                return
            media.state = state
            media.error = None
            for name, value in fields.items():
                setattr(media, name, value)
            db.commit()

    @staticmethod
    def _post_folder(db: Session, post: Post, project: Project) -> PurePosixPath:
        """The post's folder: the one it has files in already, or a new one named after it."""
        if post.cover_path:
            return PurePosixPath(post.cover_path).parent
        existing = db.scalars(select(Media.local_path).where(Media.post == post, Media.local_path.is_not(None))).first()
        if existing:
            return PurePosixPath(existing).parent.parent
        return post_folder(project.url, post.id, post.date, post.title)

    def _media_path(self, db: Session, media: Media, post: Post, project: Project) -> PurePosixPath:
        folder = self._post_folder(db, post, project) / _SUBFOLDERS[media.kind]
        others = db.scalars(
            select(Media.local_path).where(Media.post == post, Media.id != media.id, Media.local_path.is_not(None))
        )
        taken = {PurePosixPath(path).name.lower() for path in others if PurePosixPath(path).parent == folder}
        prefix = f'{str(folder).lower()}/'
        taken |= {path.removeprefix(prefix) for path in self._reserved if path.startswith(prefix)}
        return folder / unique_name(_media_name(media, post.title), taken)

    def _run_asset(self, library: Library, task: Task) -> bool | None:
        """A post's cover, or a project's logo or cover."""
        with library.session() as db:
            if task.kind == POST_COVER:
                post = db.get(Post, task.id)
                if post is None or not post.cover_url or post.cover_path:
                    return None
                url, title = post.cover_url, post.title
                relative = self._post_folder(db, post, post.project) / f'cover{_suffix(url, ".jpg")}'
            else:
                project = db.get(Project, task.id)
                url = project and (project.logo_url if task.kind == PROJECT_LOGO else project.cover_url)
                if project is None or not url:
                    return None
                name = 'logo' if task.kind == PROJECT_LOGO else 'cover'
                title = project.title
                relative = project_assets_folder(project.url) / f'{name}{_suffix(url, ".webp")}'

        report = self._progress(task, title)
        try:
            self._fetch_to(
                self._public, site_url(url), library.tmp_dir / f'{task.key}.part', library.file(relative), report
            )
        except DownloadCancelled:
            return None
        except (DownloadError, OSError) as failure:
            log.warning('Download %s failed: %s', task.key, failure)
            return False

        with library.session() as db:
            if task.kind == POST_COVER:
                row = db.get(Post, task.id)
                if row is not None:
                    row.cover_path = str(relative)
            else:
                row = db.get(Project, task.id)
                if row is not None:
                    setattr(row, 'logo_path' if task.kind == PROJECT_LOGO else 'cover_path', str(relative))
            db.commit()
        return True


__all__ = ['DownloadService', 'DownloadState', 'Task', 'file_url']
