"""Finds ffmpeg and runs it. The app needs it for one thing: joining a video with its sound."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

from offsponsr.config import user_config_dir

log = logging.getLogger(__name__)

EXECUTABLE = 'ffmpeg.exe' if sys.platform == 'win32' else 'ffmpeg'

# Don't flash a console window on Windows every time ffmpeg runs.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0


class FfmpegError(Exception):
    """ffmpeg ran and failed; the message is the end of what it wrote to stderr."""


def own_ffmpeg_dir() -> Path:
    """Where the app keeps an ffmpeg of its own, for systems that have none."""
    return user_config_dir() / 'ffmpeg'


def find_ffmpeg(configured: str | None = None) -> Path | None:
    """The ffmpeg to use: the one named in the settings, the system's, or the app's own."""
    if configured:
        path = Path(configured)
        if path.is_file():
            return path
        log.warning('The ffmpeg from the settings is not there: %s', configured)
    if found := shutil.which('ffmpeg'):
        return Path(found)
    own = own_ffmpeg_dir() / EXECUTABLE
    return own if own.is_file() else None


def mux(ffmpeg: Path, inputs: list[Path], dest: Path) -> None:
    """Put the streams of `inputs` (a video, its sound) into one MP4 without re-encoding."""
    command = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y']
    for source in inputs:
        command += ['-i', str(source)]
    # faststart moves the index to the front of the file, so playback can start at once.
    command += ['-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', str(dest)]

    result = subprocess.run(command, capture_output=True, check=False, creationflags=_NO_WINDOW)
    if result.returncode != 0:
        dest.unlink(missing_ok=True)
        raise FfmpegError(result.stderr.decode('utf-8', 'replace').strip()[-2000:])
