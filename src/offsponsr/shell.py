"""Hands things over to the user's system: a link to the browser, a file to its program or the file manager."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from pathlib import Path, PurePath

# Files that are safe to hand to whatever program the system opens them with: documents and media.
# Anything else (programs, scripts, archives) is only ever shown in its folder.
OPENABLE = frozenset(
    {
        '.pdf', '.epub', '.fb2', '.djvu', '.txt', '.rtf', '.doc', '.docx', '.odt', '.xls', '.xlsx', '.ods',
        '.ppt', '.pptx', '.odp', '.csv', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.mp3', '.m4a', '.ogg',
        '.wav', '.flac', '.mp4', '.mkv', '.webm', '.mov',
    }
)  # fmt: skip

_LONG_PATH_PREFIX = '\\\\?\\'


class ShellError(Exception):
    """The system refused to do what was asked."""


def is_web_link(url: str) -> bool:
    """Whether it is a link the system may be handed: a web page, or an address to write a letter to."""
    parts = urlsplit(url)
    if parts.scheme == 'mailto':
        return bool(parts.path)
    return parts.scheme in ('http', 'https') and bool(parts.netloc)


def is_openable(path: PurePath) -> bool:
    return path.suffix.lower() in OPENABLE


def _plain(path: Path) -> str:
    """The path without the long-path prefix, which the Windows shell doesn't understand."""
    return str(path).removeprefix(_LONG_PATH_PREFIX)


class Shell:
    def open_url(self, url: str) -> None:
        """Open a web link in the user's browser."""
        if not is_web_link(url):
            raise ShellError(f'Not a web link: {url[:80]}')
        webbrowser.open(url)

    def open_file(self, path: Path) -> None:
        """Open a document or a media file with the program the system has for it."""
        if not is_openable(path) or not path.is_file():
            raise ShellError(f'Not a file to open: {path.name}')
        try:
            if sys.platform == 'win32':
                os.startfile(_plain(path))
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
        except OSError as error:
            raise ShellError(str(error)) from error

    def reveal(self, path: Path) -> None:
        """Show the file in the system's file manager."""
        try:
            if sys.platform == 'win32':
                # Explorer returns a non-zero code even when it works, so its answer is not checked.
                subprocess.Popen(['explorer', f'/select,{_plain(path)}'])
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', str(path)])
            else:
                subprocess.Popen(['xdg-open', str(path.parent)])
        except OSError as error:
            raise ShellError(str(error)) from error
