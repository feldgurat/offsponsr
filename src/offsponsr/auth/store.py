from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

from offsponsr.auth.cookies import SiteCookie

if TYPE_CHECKING:
    from pathlib import Path

    from offsponsr.library import Library

log = logging.getLogger(__name__)

KEYRING_SERVICE = 'offsponsr'
# Windows Credential Manager takes about 1280 characters per entry; longer secrets go in pieces.
KEYRING_CHUNK = 1000

SESSION_FILE = 'session.json'


@dataclass(frozen=True)
class SavedSession:
    """What is kept between runs to stay signed in."""

    cookies: list[SiteCookie] = field(default_factory=list)
    # Shown as "signed in as"; sponsr.ru returns it with every token.
    email: str | None = None

    def dumps(self) -> str:
        return json.dumps({'cookies': [cookie.to_json() for cookie in self.cookies], 'email': self.email})

    @classmethod
    def loads(cls, text: str) -> SavedSession | None:
        """None if the text is not a saved session (damaged, or written by something else)."""
        try:
            data = json.loads(text)
            email = data.get('email')
            return cls(
                cookies=[SiteCookie.from_json(item) for item in data['cookies']],
                email=email if isinstance(email, str) else None,
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            return None


class SessionStore(Protocol):
    def load(self) -> SavedSession | None: ...

    def save(self, session: SavedSession) -> None: ...

    def clear(self) -> None: ...


class KeyringSessionStore:
    """Keeps the session in the system's secret storage, under the library's id."""

    def __init__(self, library_id: str) -> None:
        self._library_id = library_id

    def _piece(self, index: int) -> str:
        return f'{self._library_id}/{index}'

    def _count(self) -> int:
        count = keyring.get_password(KEYRING_SERVICE, self._library_id)
        return int(count) if count and count.isdigit() else 0

    def load(self) -> SavedSession | None:
        pieces = [keyring.get_password(KEYRING_SERVICE, self._piece(index)) for index in range(self._count())]
        if not pieces or None in pieces:
            return None
        return SavedSession.loads(''.join(pieces))

    def save(self, session: SavedSession) -> None:
        text = session.dumps()
        pieces = [text[start : start + KEYRING_CHUNK] for start in range(0, len(text), KEYRING_CHUNK)]

        previous = self._count()
        for index, piece in enumerate(pieces):
            keyring.set_password(KEYRING_SERVICE, self._piece(index), piece)
        keyring.set_password(KEYRING_SERVICE, self._library_id, str(len(pieces)))
        self._delete_pieces(range(len(pieces), previous))

    def clear(self) -> None:
        previous = self._count()
        if previous:
            self._delete(self._library_id)
        self._delete_pieces(range(previous))

    def _delete_pieces(self, indexes: range) -> None:
        for index in indexes:
            self._delete(self._piece(index))

    @staticmethod
    def _delete(username: str) -> None:
        try:
            keyring.delete_password(KEYRING_SERVICE, username)
        except PasswordDeleteError:
            # Already gone.
            pass


class FileSessionStore:
    """Keeps the session in a plain file inside the library. Only for systems without a keyring."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> SavedSession | None:
        try:
            return SavedSession.loads(self._path.read_text(encoding='utf-8'))
        except OSError:
            return None

    def save(self, session: SavedSession) -> None:
        self._path.write_text(session.dumps(), encoding='utf-8')

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)


class FallbackSessionStore:
    """The system keyring when it works, the file in the library when it doesn't."""

    def __init__(self, primary: SessionStore, fallback: SessionStore) -> None:
        self._primary = primary
        self._fallback = fallback

    def load(self) -> SavedSession | None:
        try:
            session = self._primary.load()
        except KeyringError:
            log.warning('The system keyring is unavailable, reading the session from the library', exc_info=True)
            session = None
        return session or self._fallback.load()

    def save(self, session: SavedSession) -> None:
        try:
            self._primary.save(session)
        except KeyringError:
            log.warning('The system keyring is unavailable, saving the session into the library', exc_info=True)
            self._fallback.save(session)
        else:
            # Don't leave a stale plain-text copy behind once the keyring works.
            self._fallback.clear()

    def clear(self) -> None:
        try:
            self._primary.clear()
        except KeyringError:
            log.warning('The system keyring is unavailable, nothing to clear there', exc_info=True)
        self._fallback.clear()


def open_session_store(library: Library) -> SessionStore:
    return FallbackSessionStore(KeyringSessionStore(library.id), FileSessionStore(library.root / SESSION_FILE))
