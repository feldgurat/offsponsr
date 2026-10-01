from __future__ import annotations

import base64
import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookiejar import DefaultCookiePolicy
from typing import TYPE_CHECKING, Any

import requests

from offsponsr.auth.cookies import SESSION_COOKIES, SiteCookie, is_site_domain, session_cookies
from offsponsr.auth.errors import SessionExpiredError, SiteUnavailableError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from http.cookiejar import Cookie

log = logging.getLogger(__name__)

SITE = 'https://sponsr.ru'
REFRESH_URL = f'{SITE}/api/v2/auth/refresh-token'

# sponsr.ru is built for browsers; a browser-like agent is what sponsrdump has always sent it.
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
)
# Seconds to connect, seconds to wait for data.
TIMEOUT = (10, 30)

# Tokens live for an hour; get a new one this long before the old one runs out.
REFRESH_MARGIN = timedelta(minutes=5)
# What to assume when a token doesn't say when it expires.
DEFAULT_LIFETIME = timedelta(minutes=55)


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_at: datetime
    email: str | None
    # The account's id on sponsr.ru.
    user_id: int | None = None

    def is_fresh(self, now: datetime) -> bool:
        return now < self.expires_at - REFRESH_MARGIN


class _SessionCookiesOnly(DefaultCookiePolicy):
    """Takes from sponsr.ru only the cookies that make up the session.

    The site's answers also set analytics cookies; a client that isn't a browser has no use
    for them and no reason to send them back. Other hosts (Kinescope) are left alone.
    """

    def set_ok(self, cookie: Cookie, request: Any) -> bool:
        if is_site_domain(cookie.domain) and cookie.name not in SESSION_COOKIES:
            return False
        return super().set_ok(cookie, request)


def new_http(cookies: Iterable[SiteCookie] = ()) -> requests.Session:
    http = requests.Session()
    http.headers['User-Agent'] = USER_AGENT
    http.cookies.set_policy(_SessionCookiesOnly())
    for cookie in cookies:
        http.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
    return http


def site_cookies(http: requests.Session) -> list[SiteCookie]:
    return [
        SiteCookie(name=cookie.name, value=cookie.value or '', domain=cookie.domain, path=cookie.path)
        for cookie in http.cookies
        if is_site_domain(cookie.domain)
    ]


def _claims(token: str) -> dict[str, Any]:
    """What a JWT says about itself; empty if the token isn't a JWT we can read."""
    try:
        payload = token.split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
    except (IndexError, ValueError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _expiry(claims: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromtimestamp(claims['exp'], UTC)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return None


def refresh_access_token(http: requests.Session) -> AccessToken:
    """Trade the session cookies for a short-lived access token."""
    try:
        response = http.get(REFRESH_URL, timeout=TIMEOUT, headers={'Accept': 'application/json'})
    except requests.RequestException as error:
        raise SiteUnavailableError(str(error)) from error

    # Names only, never values: this is what tells us how the site's session works.
    log.info(
        'refresh-token answered %s and set cookies %s',
        response.status_code,
        sorted(cookie.name for cookie in response.cookies),
    )
    if response.status_code in (401, 403):
        raise SessionExpiredError
    if not response.ok:
        raise SiteUnavailableError(f'refresh-token answered {response.status_code}')

    try:
        data = response.json()['data']
        value = data['access_token']
        email = data.get('email')
    except (ValueError, KeyError, TypeError, AttributeError):
        raise SiteUnavailableError('refresh-token answered with an unexpected body') from None
    if not isinstance(value, str) or not value:
        raise SiteUnavailableError('refresh-token answered without a token')

    claims = _claims(value)
    user_id = claims.get('userId')
    return AccessToken(
        value=value,
        expires_at=_expiry(claims) or datetime.now(UTC) + DEFAULT_LIFETIME,
        email=email if isinstance(email, str) else None,
        user_id=user_id if isinstance(user_id, int) else None,
    )


class SponsrSession:
    """A signed-in sponsr.ru session: the cookies, and access tokens made from them on demand."""

    def __init__(
        self,
        cookies: Iterable[SiteCookie],
        email: str | None = None,
        on_change: Callable[[SponsrSession], None] | None = None,
    ) -> None:
        self.http = new_http(session_cookies(cookies))
        self._email = email
        self._on_change = on_change
        self._token: AccessToken | None = None
        self._lock = threading.Lock()
        self._saved = self._snapshot()

    @property
    def cookies(self) -> list[SiteCookie]:
        """The session's cookies as they are now; the site may have replaced them."""
        return session_cookies(site_cookies(self.http))

    @property
    def email(self) -> str | None:
        """The account's email as of the latest token, or as remembered from an earlier run."""
        return self._email

    def token(self, *, force: bool = False) -> AccessToken:
        """A token good for at least the next few minutes; `force` gets a new one regardless.

        Raises SessionExpiredError when sponsr.ru no longer accepts the cookies.
        """
        with self._lock:
            if force or self._token is None or not self._token.is_fresh(datetime.now(UTC)):
                if not self.cookies:
                    # No session cookie, nothing to ask the site about.
                    raise SessionExpiredError
                self._token = refresh_access_token(self.http)
                self._email = self._token.email or self._email
                self._notify_if_changed()
            return self._token

    def _snapshot(self) -> tuple[frozenset[SiteCookie], str | None]:
        return frozenset(self.cookies), self.email

    def _notify_if_changed(self) -> None:
        # The site may hand out new cookies with a token; they have to outlive this run.
        snapshot = self._snapshot()
        if snapshot != self._saved:
            self._saved = snapshot
            if self._on_change:
                self._on_change(self)
