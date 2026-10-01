"""Finds ffmpeg and runs it. The app needs it for one thing: joining a video with its sound."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from offsponsr.config import user_config_dir

if sys.platform == 'win32':
    import winreg

log = logging.getLogger(__name__)

EXECUTABLE = 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'

# Don't flash a console window on Windows every time ffmpeg runs.
NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

# How long a program asked for its version may take to answer, in seconds.
VERSION_TIMEOUT = 10

_VERSION = re.compile(rb'ffmpeg version (\S+)')


class FfmpegError(Exception):
    """ffmpeg ran and failed; the message is the end of what it wrote to stderr."""


def own_ffmpeg_dir() -> Path:
    """Where the app looks for an ffmpeg of its own, for systems that have none."""
    return user_config_dir() / 'ffmpeg'


def installed_path() -> str | None:
    """The PATH a program started right now would get, on Windows.

    The app's own PATH is the one from when it started: an ffmpeg installed since is in the
    registry and not in there.
    """
    if sys.platform != 'win32':
        return None

    folders = []
    # The system's folders come first and the user's after them, as Windows puts them together.
    for root, key in (
        (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment'),
        (winreg.HKEY_CURRENT_USER, 'Environment'),
    ):
        try:
            with winreg.OpenKey(root, key) as opened:
                value, kind = winreg.QueryValueEx(opened, 'Path')
        except OSError:
            continue
        if isinstance(value, str) and value:
            folders.append(winreg.ExpandEnvironmentStrings(value) if kind == winreg.REG_EXPAND_SZ else value)
    return os.pathsep.join(folders) or None


def find_ffmpeg(configured: str | None = None) -> Path | None:
    """The ffmpeg to use: the one named in the settings, the system's, or the app's own."""
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        log.warning('The ffmpeg from the settings is not there: %s', configured)
    if found := shutil.which('ffmpeg'):
        return Path(found)
    if (fresh := installed_path()) and (found := shutil.which('ffmpeg', path=fresh)):
        return Path(found)
    own = own_ffmpeg_dir() / EXECUTABLE
    return own if own.is_file() else None


def ffmpeg_version(ffmpeg: Path) -> str | None:
    """What the program calls its version; None if it doesn't answer the way ffmpeg does."""
    try:
        result = subprocess.run(
            [str(ffmpeg), '-version'],
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=VERSION_TIMEOUT,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    version = _VERSION.match(result.stdout)
    return version.group(1).decode('ascii', 'replace') if version else None


def mux(ffmpeg: Path, inputs: list[Path], dest: Path) -> None:
    """Put the streams of `inputs` (a video, its sound) into one MP4 without re-encoding."""
    command = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y']
    for source in inputs:
        command += ['-i', str(source)]
    # faststart moves the index to the front of the file, so playback can start at once.
    command += ['-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', str(dest)]

    result = subprocess.run(command, capture_output=True, check=False, creationflags=NO_WINDOW)
    if result.returncode != 0:
        dest.unlink(missing_ok=True)
        raise FfmpegError(result.stderr.decode('utf-8', 'replace').strip()[-2000:])
