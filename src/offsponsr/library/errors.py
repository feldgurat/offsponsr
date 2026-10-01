from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class LibraryError(Exception):
    """A library folder can't be created or opened. `code` is what the UI keys its message on."""

    code = 'library_error'

    def __init__(self, path: Path) -> None:
        super().__init__(f'{self.code}: {path}')
        self.path = path


class LibraryMissingError(LibraryError):
    """The folder isn't there, e.g. the drive it lives on is unplugged."""

    code = 'missing'


class NotALibraryError(LibraryError):
    """The folder has no readable library.json."""

    code = 'not_a_library'


class FolderNotEmptyError(LibraryError):
    """A new library was asked for in a folder that already holds other files."""

    code = 'not_empty'


class LibraryExistsError(LibraryError):
    """A new library was asked for in a folder that already is one."""

    code = 'already_library'


class LibraryLockedError(LibraryError):
    """Another running copy of the app has the library open."""

    code = 'locked'


class LibraryTooNewError(LibraryError):
    """The library was written by a newer version of the app."""

    code = 'too_new'
