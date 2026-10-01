"""Runs syncs in the background, one project at a time, and adds projects to the library."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from sqlalchemy import select

from offsponsr.auth.cookies import is_site_domain
from offsponsr.auth.errors import AuthError, NoLibraryError
from offsponsr.library.models import AddedVia, MediaMode, Project
from offsponsr.sponsr import SponsrApiError, SponsrClient, SponsrError, SponsrFormatError
from offsponsr.sync.engine import ProjectSync, SyncCancelled, SyncProgress

if TYPE_CHECKING:
    from collections.abc import Callable

    from offsponsr.auth import AccountService
    from offsponsr.library import Library, LibraryManager
    from offsponsr.sponsr.models import Subscription
    from offsponsr.sync.events import EventBus

log = logging.getLogger(__name__)

# What a newly added project downloads by itself, besides texts and pictures (the user's choice).
DEFAULT_AUDIO = MediaMode.AUTO
DEFAULT_VIDEO = MediaMode.MANUAL
DEFAULT_ATTACH = MediaMode.AUTO

_PROJECT_ADDRESS = re.compile(r'[A-Za-z0-9_.-]+')


class SyncError(Exception):
    """A request to the sync service that can't be carried out. `code` is what the UI keys its message on."""

    code = 'sync_error'


class InvalidAddressError(SyncError):
    """What was typed in is not the address of a project on sponsr.ru."""

    code = 'invalid_address'


class ProjectNotFoundError(SyncError):
    """sponsr.ru has no project at this address."""

    code = 'project_not_found'


class SyncRunningError(SyncError):
    """The library can't be changed from under a running sync."""

    code = 'sync_running'


@dataclass(frozen=True)
class RunningSync:
    project_id: int
    title: str
    posts_done: int = 0
    # None until the site has told how many posts there are.
    posts_total: int | None = None


@dataclass(frozen=True)
class SyncFailure:
    project_id: int
    title: str
    code: str


@dataclass(frozen=True)
class SyncState:
    running: RunningSync | None = None
    # Projects waiting for their turn.
    queue: tuple[int, ...] = ()
    # What went wrong since the queue last started from empty.
    failures: tuple[SyncFailure, ...] = ()
    cancelling: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            'running': asdict(self.running) if self.running else None,
            'queue': list(self.queue),
            'failures': [asdict(failure) for failure in self.failures],
            'cancelling': self.cancelling,
        }


@dataclass(frozen=True)
class SubscriptionChoice:
    """A subscription as offered in the "add projects" list."""

    id: int
    url: str
    title: str
    owner_name: str | None
    level_name: str | None
    in_library: bool


@dataclass
class _Batch:
    """What the worker thread keeps while it works through the queue."""

    # The account's subscriptions, read once per batch; None until read.
    subscriptions: dict[int, Subscription] | None = None


def project_address(text: str) -> str:
    """The project's address on the site from whatever the user pasted: a link or the bare name."""
    text = text.strip()
    if '://' in text or text.lower().startswith(('sponsr.ru', 'www.sponsr.ru')):
        parts = urlsplit(text if '://' in text else f'https://{text}')
        if not is_site_domain(parts.hostname or ''):
            raise InvalidAddressError
        text = parts.path
    name = text.strip('/').split('/', 1)[0]
    if not _PROJECT_ADDRESS.fullmatch(name):
        raise InvalidAddressError
    return name


def failure_code(error: BaseException) -> str:
    if isinstance(error, AuthError):
        return error.code
    if isinstance(error, SponsrFormatError):
        return 'site_changed'
    if isinstance(error, SponsrApiError):
        return 'site_refused'
    return 'unknown'


class SyncService:
    def __init__(
        self,
        libraries: LibraryManager,
        account: AccountService,
        events: EventBus,
        make_client: Callable[[AccountService], SponsrClient] = SponsrClient,
        on_synced: Callable[[int], object] | None = None,
    ) -> None:
        self._libraries = libraries
        self._events = events
        # Told the id of every project whose sync went through; the downloads take it from there.
        self._on_synced = on_synced
        # One client for everything, so the pause between requests holds across projects.
        self._client = make_client(account)
        self._lock = threading.Lock()
        self._state = SyncState()
        # Titles of the projects that are or were in the queue, for showing what is going on.
        self._titles: dict[int, str] = {}
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    def state(self) -> SyncState:
        with self._lock:
            return self._state

    def is_busy(self) -> bool:
        state = self.state()
        return state.running is not None or bool(state.queue)

    def subscriptions(self) -> list[SubscriptionChoice]:
        """The account's subscriptions on the site, each marked if it is in the library already."""
        library = self._library()
        with library.session() as db:
            present = set(db.scalars(select(Project.id)))
        return [
            SubscriptionChoice(
                id=subscription.id,
                url=subscription.url,
                title=subscription.title,
                owner_name=subscription.owner_name,
                level_name=subscription.level.name if subscription.level else None,
                in_library=subscription.id in present,
            )
            for subscription in self._client.subscriptions()
        ]

    def add_projects(self, subscription_ids: list[int], address: str | None = None) -> list[int]:
        """Add subscriptions and/or a project by its address, and queue their first sync.

        Returns the ids of the projects that were not in the library before.
        """
        library = self._library()
        name = project_address(address) if address and address.strip() else None

        new: list[Project] = []
        if subscription_ids:
            by_id = {subscription.id: subscription for subscription in self._client.subscriptions()}
            for subscription_id in subscription_ids:
                subscription = by_id.get(subscription_id)
                if subscription is not None:
                    new.append(
                        self._new_project(
                            subscription.id,
                            subscription.url,
                            subscription.title,
                            AddedVia.SUBSCRIPTION,
                            subscription_level_id=subscription.level.id if subscription.level else None,
                            last_paid=subscription.last_paid,
                        )
                    )
        if name is not None:
            try:
                card = self._client.project(name).project
            except SponsrApiError as error:
                if error.status == 404:
                    raise ProjectNotFoundError from None
                raise
            new.append(self._new_project(card.id, card.url, card.title, AddedVia.URL))

        added = []
        with library.session() as db:
            for project in new:
                if db.get(Project, project.id) is None and project.id not in added:
                    db.add(project)
                    added.append(project.id)
            db.commit()

        if added:
            self._events.publish({'type': 'projects'})
            self.start(added)
        return added

    @staticmethod
    def _new_project(project_id: int, url: str, title: str, added_via: AddedVia, **fields: object) -> Project:
        return Project(
            id=project_id,
            url=url,
            title=title,
            added_via=added_via,
            media_mode_audio=DEFAULT_AUDIO,
            media_mode_video=DEFAULT_VIDEO,
            media_mode_attach=DEFAULT_ATTACH,
            **fields,
        )

    def start(self, project_ids: list[int] | None = None) -> SyncState:
        """Queue projects for a sync; with no ids, every project that has syncing switched on."""
        library = self._library()
        with library.session() as db:
            if project_ids is None:
                rows = db.execute(select(Project.id, Project.title).where(Project.sync_enabled).order_by(Project.title))
            else:
                rows = db.execute(select(Project.id, Project.title).where(Project.id.in_(project_ids)))
            titles: dict[int, str] = dict(rows.all())
        wanted = [project_id for project_id in (titles if project_ids is None else project_ids) if project_id in titles]

        with self._lock:
            idle = self._state.running is None and not self._state.queue
            busy_with = {self._state.running.project_id} if self._state.running else set()
            queue = list(self._state.queue)
            queue += [project_id for project_id in wanted if project_id not in queue and project_id not in busy_with]
            self._state = replace(
                self._state,
                queue=tuple(queue),
                failures=() if idle else self._state.failures,
            )
            self._titles.update(titles)
            if queue and (self._worker is None or not self._worker.is_alive()):
                self._stop.clear()
                self._worker = threading.Thread(target=self._work, args=(library,), name='offsponsr-sync', daemon=True)
                self._worker.start()
            state = self._state
        self._announce(state)
        return state

    def cancel(self) -> SyncState:
        """Stop after the request in flight; what has been saved stays."""
        with self._lock:
            if self._state.running is None and not self._state.queue:
                return self._state
            self._stop.set()
            self._state = replace(self._state, queue=(), cancelling=True)
            state = self._state
        self._announce(state)
        return state

    def shutdown(self, timeout: float = 10) -> None:
        """Stop the worker and wait for it; called before the library is closed."""
        self._stop.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout)

    def _library(self) -> Library:
        library = self._libraries.current
        if library is None:
            raise NoLibraryError
        return library

    def _announce(self, state: SyncState) -> None:
        self._events.publish({'type': 'sync', 'state': state.to_json()})

    def _update(self, **changes: object) -> None:
        with self._lock:
            self._state = replace(self._state, **changes)
            state = self._state
        self._announce(state)

    def _work(self, library: Library) -> None:
        batch = _Batch()
        while True:
            with self._lock:
                if self._stop.is_set() or not self._state.queue:
                    self._state = replace(self._state, running=None, queue=(), cancelling=False)
                    state = self._state
                    self._worker = None
                    break
                project_id, *rest = self._state.queue
                title = self._titles.get(project_id, '')
                self._state = replace(self._state, running=RunningSync(project_id, title), queue=tuple(rest))
                state = self._state
            self._announce(state)

            give_up = self._sync_one(library, batch, project_id, title)
            self._events.publish({'type': 'projects'})
            if give_up:
                self._stop.set()
        self._announce(state)

    def _sync_one(self, library: Library, batch: _Batch, project_id: int, title: str) -> bool:
        """Sync one project. Returns True if there is no point in going on with the queue."""

        def on_progress(progress: SyncProgress) -> None:
            self._update(running=RunningSync(project_id, title, progress.posts_done, progress.posts_total))

        try:
            if batch.subscriptions is None:
                batch.subscriptions = {subscription.id: subscription for subscription in self._client.subscriptions()}
            sync = ProjectSync(library, self._client, on_progress=on_progress, should_stop=self._stop.is_set)
            sync.run(project_id, batch.subscriptions.get(project_id))
            if self._on_synced:
                self._on_synced(project_id)
        except SyncCancelled:
            return True
        except (AuthError, SponsrError) as error:
            log.warning('Sync of project %s failed: %s', project_id, error)
            self._fail(project_id, title, failure_code(error))
            # Without a session or without the site the rest of the queue would fail the same way.
            return isinstance(error, AuthError)
        except Exception:
            log.exception('Sync of project %s failed', project_id)
            self._fail(project_id, title, 'unknown')
        return False

    def _fail(self, project_id: int, title: str, code: str) -> None:
        with self._lock:
            self._state = replace(self._state, failures=(*self._state.failures, SyncFailure(project_id, title, code)))


__all__ = [
    'InvalidAddressError',
    'ProjectNotFoundError',
    'SubscriptionChoice',
    'SyncError',
    'SyncRunningError',
    'SyncService',
    'SyncState',
    'project_address',
]
