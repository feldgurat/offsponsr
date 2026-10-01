from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable
    from http.cookies import SimpleCookie

SITE_DOMAIN = 'sponsr.ru'

# What sponsr.ru tells a signed-in browser by: `SESS` is the session itself (the site also
# gives one to anonymous visitors), `user_id` is the account's id. Checked on a live session
# on 2026-10-01; everything else the site sets is analytics and is not kept.
SITE_SESSION_COOKIE = 'SESS'
SESSION_COOKIES = frozenset({SITE_SESSION_COOKIE, 'user_id'})


@dataclass(frozen=True)
class SiteCookie:
    """One cookie of the sponsr.ru session, with enough to send it back to the right hosts."""

    name: str
    value: str
    # As the browser has it: `.sponsr.ru` for the whole domain, `sponsr.ru` for the one host.
    domain: str = f'.{SITE_DOMAIN}'
    path: str = '/'

    def to_json(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: Any) -> SiteCookie:
        return cls(name=str(data['name']), value=str(data['value']), domain=str(data['domain']), path=str(data['path']))


def is_site_domain(domain: str) -> bool:
    domain = domain.lstrip('.').lower()
    return domain == SITE_DOMAIN or domain.endswith(f'.{SITE_DOMAIN}')


def session_cookies(cookies: Iterable[SiteCookie]) -> list[SiteCookie]:
    """The cookies worth keeping; empty if the session cookie itself is not among them."""
    kept = [cookie for cookie in cookies if cookie.name in SESSION_COOKIES]
    return kept if any(cookie.name == SITE_SESSION_COOKIE for cookie in kept) else []


def from_webview(cookies: Iterable[SimpleCookie]) -> list[SiteCookie]:
    """Pick the sponsr.ru cookies out of everything the login window holds."""
    found = []
    for cookie in cookies:
        for name, morsel in cookie.items():
            if is_site_domain(morsel['domain']):
                found.append(
                    SiteCookie(name=name, value=morsel.value, domain=morsel['domain'], path=morsel['path'] or '/')
                )
    return found


def from_header(header: str) -> list[SiteCookie]:
    """Parse a `Cookie` request header copied from the browser's DevTools: `a=1; b=2`.

    Raises ValueError if there is not a single cookie in it.
    """
    header = header.strip()
    if header.lower().startswith('cookie:'):
        header = header[len('cookie:') :]

    found = []
    for pair in header.split(';'):
        name, separator, value = pair.strip().partition('=')
        if separator and name:
            found.append(SiteCookie(name=name.strip(), value=value.strip()))
    if not found:
        raise ValueError('No cookies in the header')
    return found
