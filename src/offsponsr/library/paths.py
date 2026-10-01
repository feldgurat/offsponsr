"""Where things go inside a library folder, and names that every file system will take.

Paths kept in the database are relative to the library root and use `/`, whatever the OS,
so a library can be moved between machines.
"""

from __future__ import annotations

import re
import sys
from datetime import timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Container
    from datetime import datetime

# What a file system takes for one name.
MAX_FILENAME_BYTES = 255
# What the app gives a post's folder and a media file. Much shorter than the file system
# allows: on Windows a whole path of more than 260 characters, library folder included,
# is trouble for Explorer and for many programs that might be asked to open the file.
MAX_POST_FOLDER_CHARS = 60
MAX_MEDIA_NAME_CHARS = 60

PROJECTS_DIR = 'projects'
# Inside a project's folder: its logo and cover.
PROJECT_ASSETS_DIR = '_project'
IMAGES_DIR = 'images'
AUDIO_DIR = 'audio'
VIDEO_DIR = 'video'
ATTACHMENTS_DIR = 'attachments'

# What Windows refuses in a name; other systems refuse a subset of it.
_INVALID_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_DEVICES = frozenset(
    {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{n}' for n in range(1, 10)), *(f'LPT{n}' for n in range(1, 10))}
)
# Windows' own limit for a path, and the prefix that lifts it.
_WINDOWS_MAX_PATH = 248
_WINDOWS_LONG_PREFIX = '\\\\?\\'

# Folder dates follow the site's clock (Moscow, which keeps no summer time).
SITE_TIME = timezone(timedelta(hours=3))


def _split_extension(filename: str) -> tuple[str, str]:
    stem, dot, extension = filename.rpartition('.')
    if dot and stem and len(extension) <= 10:
        return stem, f'.{extension}'
    return filename, ''


def truncate_filename(filename: str, max_bytes: int = MAX_FILENAME_BYTES) -> str:
    """Cut a name down to `max_bytes` bytes of UTF-8, keeping its extension."""
    # From sponsrdump (BSD-3-Clause, © Igor Starikov).
    encoded = filename.encode('utf-8')
    if len(encoded) <= max_bytes:
        return filename

    stem, suffix = _split_extension(filename)
    max_stem_bytes = max_bytes - len(suffix.encode('utf-8'))
    if max_stem_bytes <= 0:
        return encoded[:max_bytes].decode('utf-8', 'ignore')
    return stem.encode('utf-8')[:max_stem_bytes].decode('utf-8', 'ignore') + suffix


def safe_name(name: str, max_chars: int | None = None) -> str:
    """A file or folder name made from any text, acceptable to Windows, Linux and macOS.

    `max_chars` cuts it shorter than the file system would, keeping the extension.
    """
    # Whitespace first: tabs and line breaks are among the characters replaced below.
    name = re.sub(r'\s+', ' ', name)
    name = _INVALID_CHARACTERS.sub('_', name).strip(' .')
    if not name:
        name = '_'
    if name.split('.', 1)[0].upper() in _WINDOWS_DEVICES:
        name = f'_{name}'
    if max_chars is not None and len(name) > max_chars:
        stem, suffix = _split_extension(name)
        name = stem[: max(1, max_chars - len(suffix))].rstrip(' .') + suffix
    # Cutting may leave a space or a dot at the end again; Windows drops those silently.
    return truncate_filename(name).rstrip(' .') or '_'


def unique_name(name: str, taken: Container[str]) -> str:
    """`name`, or `name (2)`, `name (3)`... if it is taken. Compares without regard to case."""
    stem, suffix = _split_extension(name)
    number = 1
    candidate = name
    while candidate.lower() in taken:
        number += 1
        candidate = truncate_filename(f'{stem} ({number}){suffix}')
    return candidate


def project_folder(project_url: str) -> PurePosixPath:
    return PurePosixPath(PROJECTS_DIR) / safe_name(project_url, MAX_MEDIA_NAME_CHARS)


def project_assets_folder(project_url: str) -> PurePosixPath:
    return project_folder(project_url) / PROJECT_ASSETS_DIR


def post_folder(project_url: str, post_id: int, date: datetime, title: str) -> PurePosixPath:
    """`projects/<project>/<date> [<id>] <title>`: readable, and findable by the id in brackets."""
    day = date.astimezone(SITE_TIME).strftime('%Y-%m-%d')
    return project_folder(project_url) / safe_name(f'{day} [{post_id}] {title}', MAX_POST_FOLDER_CHARS)


def long_path(path: Path) -> Path:
    """The same path in the form Windows accepts however long it is; unchanged elsewhere.

    The names the app makes are short, but the library itself may sit deep in the folders.
    """
    if sys.platform != 'win32':
        return path
    text = str(path.absolute())
    if len(text) < _WINDOWS_MAX_PATH or text.startswith(_WINDOWS_LONG_PREFIX):
        return path
    if text.startswith('\\\\'):
        # A network share: \\server\share\... becomes \\?\UNC\server\share\...
        return Path(f'{_WINDOWS_LONG_PREFIX}UNC\\{text[2:]}')
    return Path(f'{_WINDOWS_LONG_PREFIX}{text}')
