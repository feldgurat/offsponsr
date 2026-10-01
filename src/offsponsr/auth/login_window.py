from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import webview

from offsponsr.auth.cookies import SiteCookie, from_webview, is_site_domain

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

SIGNIN_URL = 'https://sponsr.ru/auth/signin/'
WINDOW_TITLE = 'Вход в sponsr.ru'

POLL_INTERVAL = 0.5
# How many times to ask the site whether the cookies work while the window sits on one page.
CHECKS_PER_PAGE = 3
CHECK_INTERVAL = 2.0


def left_signin(url: str | None) -> bool:
    """Whether the window has moved from the sign-in pages to the rest of sponsr.ru."""
    if not url:
        return False
    parts = urlsplit(url)
    return is_site_domain(parts.hostname or '') and not parts.path.startswith('/auth')


def page_of(url: str | None) -> str:
    """The host and path of a URL, for the log: the query can carry sign-in codes and stays out."""
    parts = urlsplit(url or '')
    return f'{parts.hostname or ""}{parts.path}'


def run_login_window(accepts: Callable[[list[SiteCookie]], bool]) -> list[SiteCookie] | None:
    """Let the user sign in on sponsr.ru itself and return the cookies of that session.

    The password is typed into the site's own page; the app only reads the cookies afterwards.
    `accepts` says whether sponsr.ru takes the cookies as a signed-in session.
    Returns None if the user closes the window without signing in.
    """
    window = webview.create_window(WINDOW_TITLE, SIGNIN_URL, width=520, height=760)
    closed = threading.Event()
    window.events.closed += closed.set
    log.info('Login window opened')

    logged_page = None
    checked_url = None
    checks_left = 0
    next_check = 0.0
    while not closed.wait(POLL_INTERVAL):
        try:
            url = window.get_current_url()
            if page_of(url) != logged_page:
                logged_page = page_of(url)
                log.info('Login window is at %s', logged_page)
            if not left_signin(url):
                continue
            if url != checked_url:
                checked_url, checks_left, next_check = url, CHECKS_PER_PAGE, 0.0
            if not checks_left or time.monotonic() < next_check:
                continue

            checks_left -= 1
            next_check = time.monotonic() + CHECK_INTERVAL
            cookies = from_webview(window.get_cookies())
        except Exception:
            # Asking a window that the user has just closed fails in engine-specific ways.
            if closed.is_set():
                break
            raise

        # Names and sizes only: enough to see what the site sets, without logging the secrets.
        log.info('Login window cookies: %s', [(c.name, c.domain, len(c.value)) for c in cookies])
        if accepts(cookies):
            log.info('Login window: signed in')
            window.destroy()
            return cookies

    log.info('Login window closed without a sign-in')
    return None
