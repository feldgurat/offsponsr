from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from offsponsr.auth.cookies import SiteCookie, from_header, session_cookies
from offsponsr.auth.errors import (
    DifferentAccountError,
    InvalidCookieError,
    LoginInProgressError,
    NoLibraryError,
    NotSignedInError,
    SessionExpiredError,
    SiteUnavailableError,
)
from offsponsr.auth.session import AccessToken, SponsrSession
from offsponsr.auth.store import SavedSession, SessionStore, open_session_store
from offsponsr.library.models import Account

if TYPE_CHECKING:
    from collections.abc import Callable

    import requests

    from offsponsr.library import Library, LibraryManager

    # Shows sponsr.ru's sign-in page and returns the cookies once the callback accepts them,
    # or None if the user gave up. See auth/login_window.py.
    LoginWindow = Callable[[Callable[[list[SiteCookie]], bool]], list[SiteCookie] | None]

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AccountState:
    signed_in: bool
    email: str | None = None
    # The stored session stopped working and was dropped; the user has to sign in again.
    expired: bool = False


class AccountService:
    """The sponsr.ru account of the open library: signing in and out, and the live session.

    There is one account per library. Its cookies are kept in the session store under the
    library's id, so each library remembers its own sign-in.
    """

    def __init__(
        self,
        libraries: LibraryManager,
        login_window: LoginWindow,
        open_store: Callable[[Library], SessionStore] = open_session_store,
    ) -> None:
        self._libraries = libraries
        self._login_window = login_window
        self._open_store = open_store
        self._lock = threading.RLock()
        self._login_lock = threading.Lock()
        # The session of the library with this id, loaded from the store on first use.
        self._loaded_for: str | None = None
        self._session: SponsrSession | None = None
        self._expired = False

    def state(self) -> AccountState:
        """Where the account stands, judged from what is stored. Doesn't touch the network."""
        library = self._libraries.current
        if library is None:
            return AccountState(signed_in=False)
        with self._lock:
            session = self._current_session(library)
            if session is None:
                return AccountState(signed_in=False, expired=self._expired)
            return AccountState(signed_in=True, email=session.email)

    def http(self) -> requests.Session:
        """The HTTP session that carries the account's cookies."""
        return self._signed_in_session(self._library()).http

    def token(self, *, force: bool = False) -> AccessToken:
        """An access token for the API. Signs the account out if sponsr.ru rejects the session.

        `force` asks for a new token even if the current one hasn't run out.
        """
        library = self._library()
        session = self._signed_in_session(library)

        # Outside the lock: this may wait on the network, and state() must stay quick meanwhile.
        try:
            return session.token(force=force)
        except SessionExpiredError:
            log.info('The stored session has expired')
            with self._lock:
                if self._session is session:
                    self._forget(library, expired=True)
            raise

    def login_with_window(self) -> AccountState:
        library = self._library()
        if not self._login_lock.acquire(blocking=False):
            raise LoginInProgressError
        try:
            accepted: list[SponsrSession] = []

            def accepts(cookies: list[SiteCookie]) -> bool:
                session = SponsrSession(cookies)
                try:
                    session.token()
                except SessionExpiredError:
                    # Not signed in yet: the page is still loading or the user is still typing.
                    return False
                except SiteUnavailableError:
                    log.warning('Could not check the sign-in', exc_info=True)
                    return False
                accepted.append(session)
                return True

            if self._login_window(accepts) is not None and accepted:
                self._adopt(library, accepted[-1])
            return self.state()
        finally:
            self._login_lock.release()

    def login_with_cookie_header(self, header: str) -> AccountState:
        """Sign in with the `Cookie` request header copied from a browser where the user is signed in."""
        library = self._library()
        try:
            session = SponsrSession(from_header(header))
            session.token()
        except (ValueError, SessionExpiredError):
            raise InvalidCookieError from None
        self._adopt(library, session)
        return self.state()

    def logout(self) -> AccountState:
        """Forget the session on this computer. Nothing is sent to sponsr.ru."""
        library = self._libraries.current
        if library is not None:
            with self._lock:
                self._forget(library, expired=False)
        return self.state()

    def _library(self) -> Library:
        library = self._libraries.current
        if library is None:
            raise NoLibraryError
        return library

    def _signed_in_session(self, library: Library) -> SponsrSession:
        with self._lock:
            session = self._current_session(library)
        if session is None:
            raise NotSignedInError
        return session

    def _current_session(self, library: Library) -> SponsrSession | None:
        if self._loaded_for != library.id:
            self._loaded_for = library.id
            self._expired = False
            self._session = self._load_session(library)
        return self._session

    def _load_session(self, library: Library) -> SponsrSession | None:
        store = self._open_store(library)
        saved = store.load()
        if saved is None:
            return None

        cookies = session_cookies(saved.cookies)
        if not cookies:
            store.clear()
            return None
        if cookies != saved.cookies:
            # Saved before the app knew which cookies matter; drop the rest from the store too.
            store.save(SavedSession(cookies=cookies, email=saved.email))
        return self._new_session(library, cookies, saved.email)

    def _new_session(self, library: Library, cookies: list[SiteCookie], email: str | None) -> SponsrSession:
        store = self._open_store(library)

        def save(session: SponsrSession) -> None:
            store.save(SavedSession(cookies=session.cookies, email=session.email))

        return SponsrSession(cookies, email=email, on_change=save)

    def _adopt(self, library: Library, checked: SponsrSession) -> None:
        """Make a session that sponsr.ru has just accepted the library's own."""
        with self._lock:
            # First: this is what refuses an account the library doesn't belong to.
            self._record_login(library, checked.token().user_id)
            self._open_store(library).save(SavedSession(cookies=checked.cookies, email=checked.email))
            self._loaded_for = library.id
            self._session = self._new_session(library, checked.cookies, checked.email)
            self._expired = False

    @staticmethod
    def _record_login(library: Library, user_id: int | None) -> None:
        """Tie the library to the account on its first sign-in, and hold it to that account after.

        What a library holds depends on what its account may read, so a library keeps to one
        account; another account needs a library of its own.
        """
        with library.session() as db:
            account = db.scalars(select(Account)).first() or Account()
            if account.user_id is not None and user_id is not None and account.user_id != user_id:
                raise DifferentAccountError
            account.user_id = user_id if user_id is not None else account.user_id
            account.last_login_at = datetime.now(UTC)
            db.add(account)
            db.commit()

    def _forget(self, library: Library, *, expired: bool) -> None:
        self._open_store(library).clear()
        self._loaded_for = library.id
        self._session = None
        self._expired = expired
