from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from offsponsr.library.errors import LibraryError
from offsponsr.library.library import Library

if TYPE_CHECKING:
    from offsponsr.config import ConfigStore


@dataclass(frozen=True)
class LibraryFailure:
    """Why the library the app was last using didn't open on start."""

    path: Path
    code: str


class LibraryManager:
    """Holds the library the app currently has open and remembers it between runs."""

    def __init__(self, config_store: ConfigStore) -> None:
        self._config_store = config_store
        self._lock = threading.Lock()
        self._current: Library | None = None
        self._last_failure: LibraryFailure | None = None

    @property
    def current(self) -> Library | None:
        return self._current

    @property
    def last_failure(self) -> LibraryFailure | None:
        return self._last_failure

    def open_last(self) -> None:
        """Reopen the library from the previous run, if there was one."""
        remembered = self._config_store.load().library_path
        if remembered is None:
            return

        with self._lock:
            try:
                self._current = Library.open(Path(remembered))
            except LibraryError as error:
                self._last_failure = LibraryFailure(path=error.path, code=error.code)

    def create(self, path: Path) -> Library:
        return self._switch_to(path, create=True)

    def open(self, path: Path) -> Library:
        return self._switch_to(path, create=False)

    def close(self) -> None:
        with self._lock:
            if self._current is not None:
                self._current.close()
                self._current = None

    def _switch_to(self, path: Path, *, create: bool) -> Library:
        with self._lock:
            # Reopening the open library would trip over its own lock.
            if not create and self._current is not None and _same_folder(self._current.root, path):
                return self._current

            # Open the new one first: if that fails, the current library stays open.
            library = Library.create(path) if create else Library.open(path)
            if self._current is not None:
                self._current.close()
            self._current = library
            self._last_failure = None

            self._config_store.update(library_path=str(library.root))
            return library


def _same_folder(left: Path, right: Path) -> bool:
    try:
        return left.samefile(right)
    except OSError:
        return False
