from __future__ import annotations

import sys
from typing import IO, TYPE_CHECKING

from offsponsr.library.errors import LibraryLockedError

if TYPE_CHECKING:
    from pathlib import Path

if sys.platform == 'win32':
    import msvcrt

    def _lock(file: IO[bytes]) -> None:
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(file: IO[bytes]) -> None:
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(file: IO[bytes]) -> None:
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(file: IO[bytes]) -> None:
        fcntl.flock(file, fcntl.LOCK_UN)


class LibraryLock:
    """Marks a library as open by this process.

    It is an OS-level lock on an open file, not a marker file: the OS drops it when the
    process dies, so a crash can't leave the library locked.
    """

    def __init__(self, library_root: Path, name: str = 'library.lock') -> None:
        self._library_root = library_root
        self._path = library_root / name
        self._file: IO[bytes] | None = None

    def acquire(self) -> None:
        file = self._path.open('a+b')
        try:
            _lock(file)
        except OSError:
            file.close()
            raise LibraryLockedError(self._library_root) from None
        self._file = file

    def release(self) -> None:
        if self._file is None:
            return
        try:
            _unlock(self._file)
        finally:
            self._file.close()
            self._file = None
