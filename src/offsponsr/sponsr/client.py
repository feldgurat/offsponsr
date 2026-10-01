"""Every request the app makes to sponsr.ru for content goes through here.

The endpoints are unofficial and may change; keeping them in one module keeps the fixing in
one place. The client only reads: there is not a single request in it that changes anything
on the site, including the reader's own view history (see `full_texts`).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import TYPE_CHECKING, Any, TypeVar

import requests
from pydantic import ValidationError

from offsponsr.auth.errors import SiteUnavailableError
from offsponsr.auth.session import SITE, TIMEOUT
from offsponsr.sponsr.models import (
    Collection,
    FullTextsPage,
    Level,
    PostsPage,
    ProjectPage,
    SiteModel,
    Subscription,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from offsponsr.auth import AccountService

log = logging.getLogger(__name__)

API = f'{SITE}/api/v2'

# Both post lists come in pages of this size, in the same order (newest first).
PAGE_SIZE = 20

# Be a polite guest: one request at a time, with a breather in between.
PAUSE = 0.5
# How many times to try again when the site is busy or the connection drops, and how long to
# wait before each new try.
RETRIES = 3
RETRY_DELAYS = (1.0, 3.0, 9.0)
# Never sit out a Retry-After longer than this.
MAX_RETRY_AFTER = 60.0

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
_PROJECT_URL = re.compile(r'[A-Za-z0-9_.-]+')

Model = TypeVar('Model', bound=SiteModel)


class SponsrError(Exception):
    """sponsr.ru answered, but not with what the app asked for."""


class SponsrApiError(SponsrError):
    """An HTTP status that means the request itself was refused: 403, 404 and the like."""

    def __init__(self, status: int, what: str) -> None:
        super().__init__(f'{what}: HTTP {status}')
        self.status = status


class SponsrFormatError(SponsrError):
    """The answer doesn't look the way the client expects; the site has probably changed."""


class SponsrClient:
    def __init__(
        self,
        account: AccountService,
        *,
        pause: float = PAUSE,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._account = account
        self._pause = pause
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._last_request: float | None = None

    def subscriptions(self) -> list[Subscription]:
        """The projects the account pays for."""
        data = self._api('/content/projects/subscribed?withoutPagination=true')
        return self._parse_list(Subscription, data, 'subscriptions')

    def posts(self, project_id: int, page: int = 1) -> PostsPage:
        """One page of a project's posts, newest first.

        Long posts come with only the beginning of their text (`text_truncated`); the rest is
        in `full_texts`.
        """
        data = self._api(
            f'/content/posts/?project_id={project_id}&withText=true&withFiles=true&tags=true'
            f'&limit={PAGE_SIZE}&page={page}&orderBy=date&orderByType=desc'
        )
        return self._parse(PostsPage, data, 'posts')

    def full_texts(self, project_id: int, page: int = 1) -> FullTextsPage:
        """The whole texts of the posts on the same page of `posts`.

        This is the site's older post list. It is used for the texts because it is the one
        way to get them that doesn't mark the posts as visited in the reader's history: both
        the post's page and the API for a single post do (checked on 2026-10-01).
        """
        offset = (page - 1) * PAGE_SIZE
        response = self._get(f'{SITE}/project/{project_id}/more-posts/?offset={offset}', bearer=False)
        data = self._json(response, 'full texts')
        if not isinstance(data, dict) or not isinstance(data.get('response'), dict):
            raise SponsrFormatError('full texts: no "response" in the answer')
        return self._parse(FullTextsPage, data['response'], 'full texts')

    def levels(self, project_id: int) -> list[Level]:
        """A project's subscription levels, hidden and deleted ones included."""
        data = self._api(
            f'/content/levels?project_id={project_id}&orderBy=level_price&orderByType=asc&withoutPagination=true'
        )
        return self._parse_list(Level, data, 'levels')

    def collections(self, project_id: int) -> list[Collection]:
        data = self._api(f'/content/playlist?project_id={project_id}&withoutPagination=true')
        return self._parse_list(Collection, data, 'collections')

    def project(self, url: str) -> ProjectPage:
        """A project by its address on the site (the `name` in sponsr.ru/name/)."""
        if not _PROJECT_URL.fullmatch(url):
            raise ValueError(f'Not a project address: {url!r}')

        response = self._get(f'{SITE}/{url}/', bearer=False, accept='text/html')
        found = _NEXT_DATA.search(response.text)
        if not found:
            raise SponsrFormatError('project page: no page data in it')
        try:
            props = json.loads(found.group(1))['props']['pageProps']
        except (ValueError, KeyError, TypeError):
            raise SponsrFormatError('project page: unreadable page data') from None
        return self._parse(ProjectPage, props, 'project page')

    def _api(self, path: str) -> Any:
        return self._json(self._get(f'{API}{path}', bearer=True), path.split('?', 1)[0])

    def _get(self, url: str, *, bearer: bool, accept: str = 'application/json') -> requests.Response:
        what = url.removeprefix(SITE).split('?', 1)[0]
        with self._lock:
            refreshed = False
            attempt = 0
            while True:
                self._wait_for_turn()
                headers = {'Accept': accept}
                if bearer:
                    headers['Authorization'] = f'Bearer {self._account.token().value}'

                retry_after = None
                try:
                    response = self._account.http().get(url, headers=headers, timeout=TIMEOUT)
                except requests.RequestException as error:
                    failure = SiteUnavailableError(f'{what}: {error}')
                else:
                    status = response.status_code
                    if response.ok:
                        return response
                    if status == 401 and bearer and not refreshed:
                        # The token was withdrawn before its time; one new token, one more try.
                        refreshed = True
                        self._account.token(force=True)
                        continue
                    if status != 429 and status < 500:
                        raise SponsrApiError(status, what)
                    failure = SiteUnavailableError(f'{what}: HTTP {status}')
                    retry_after = _retry_after(response)
                finally:
                    self._last_request = self._clock()

                if attempt >= RETRIES:
                    raise failure
                delay = retry_after if retry_after is not None else RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                log.warning('%s; trying again in %.0f s', failure, delay)
                self._sleep(delay)
                attempt += 1

    def _wait_for_turn(self) -> None:
        if self._last_request is None:
            return
        wait = self._last_request + self._pause - self._clock()
        if wait > 0:
            self._sleep(wait)

    @staticmethod
    def _json(response: requests.Response, what: str) -> Any:
        try:
            return response.json()
        except ValueError:
            raise SponsrFormatError(f'{what}: the answer is not JSON') from None

    @staticmethod
    def _parse(model: type[Model], data: Any, what: str) -> Model:
        try:
            return model.model_validate(data)
        except ValidationError as error:
            # Field names and error kinds only: the input may hold paid texts and stays out of the log.
            problems = '; '.join(
                f'{".".join(map(str, problem["loc"]))}: {problem["type"]}' for problem in error.errors()[:5]
            )
            raise SponsrFormatError(f'{what}: {problems}') from None

    def _parse_list(self, model: type[Model], data: Any, what: str) -> list[Model]:
        if not isinstance(data, dict) or not isinstance(data.get('list'), list):
            raise SponsrFormatError(f'{what}: no "list" in the answer')
        return [self._parse(model, item, what) for item in data['list']]


def _retry_after(response: requests.Response) -> float | None:
    try:
        seconds = float(response.headers.get('Retry-After', ''))
    except ValueError:
        return None
    return min(max(seconds, 0.0), MAX_RETRY_AFTER)
