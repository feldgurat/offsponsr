"""Getting an ffmpeg onto a machine that has none: winget installs one, or the user points at theirs."""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from offsponsr.media.ffmpeg import NO_WINDOW, ffmpeg_version, find_ffmpeg

if TYPE_CHECKING:
    from collections.abc import Callable

    from offsponsr.config import ConfigStore
    from offsponsr.sync.events import EventBus

log = logging.getLogger(__name__)

# The build of ffmpeg by Gyan with what most people need; joining a video takes far less.
WINGET_PACKAGE = 'Gyan.FFmpeg.Essentials'

# winget downloads about 110 MB; past this many seconds it is taken for stuck and stopped.
INSTALL_TIMEOUT = 30 * 60

PLATFORM = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')


class FfmpegSetupError(Exception):
    """What was asked for can't be done; `code` tells the UI why."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FfmpegState:
    path: Path | None
    version: str | None
    # The path is the one the user pointed at, not one the app found.
    chosen: bool
    # There is a winget to install ffmpeg with.
    can_install: bool
    installing: bool
    # Why the last installation failed.
    error: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            'found': self.path is not None,
            'path': str(self.path) if self.path else None,
            'version': self.version,
            'chosen': self.chosen,
            'can_install': self.can_install,
            'installing': self.installing,
            'error': self.error,
            'platform': PLATFORM,
        }


def find_winget() -> Path | None:
    if sys.platform != 'win32':
        return None
    found = shutil.which('winget')
    return Path(found) if found else None


def install_command(winget: Path) -> list[str]:
    return [
        str(winget),
        'install',
        '--id',
        WINGET_PACKAGE,
        '--exact',
        # Only the community repository: the Store's catalogue has agreements of its own.
        '--source',
        'winget',
        # The user has agreed in the app's window; winget has nobody to ask.
        '--accept-package-agreements',
        '--accept-source-agreements',
        '--disable-interactivity',
    ]


def run_winget(winget: Path) -> int:
    """Have winget install ffmpeg and wait for it. winget checks the download against its manifest itself."""
    result = subprocess.run(
        install_command(winget),
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=INSTALL_TIMEOUT,
        creationflags=NO_WINDOW,
    )
    if result.returncode != 0:
        said = (result.stdout + result.stderr).decode('utf-8', 'replace').strip()
        log.warning('winget ended with %#010x: %s', result.returncode & 0xFFFFFFFF, said[-2000:])
    return result.returncode


class FfmpegSetup:
    def __init__(
        self,
        config: ConfigStore,
        events: EventBus,
        *,
        find: Callable[[str | None], Path | None] = find_ffmpeg,
        version: Callable[[Path], str | None] = ffmpeg_version,
        winget: Callable[[], Path | None] = find_winget,
        run: Callable[[Path], int] = run_winget,
    ) -> None:
        self._config = config
        self._events = events
        self._find = find
        self._version = version
        self._winget = winget
        self._run = run

        self._lock = threading.Lock()
        self._installing = False
        self._error: str | None = None
        self._closed = False
        self._when_ready: list[Callable[[], object]] = []
        # The version of the ffmpeg last asked: asking means running it.
        self._asked: tuple[Path, float, str | None] | None = None

    def path(self) -> Path | None:
        """The ffmpeg to join videos with right now, if there is one."""
        return self._find(self._config.load().ffmpeg_path)

    def when_ready(self, callback: Callable[[], object]) -> None:
        """Call `callback` whenever an ffmpeg turns up or changes: what waited for one can go on."""
        self._when_ready.append(callback)

    def state(self) -> FfmpegState:
        chosen = self._config.load().ffmpeg_path
        path = self._find(chosen)
        version = self._version_of(path) if path else None
        can_install = self._winget() is not None
        with self._lock:
            return FfmpegState(
                path=path,
                version=version,
                chosen=chosen is not None and path == Path(chosen),
                can_install=can_install,
                installing=self._installing,
                error=self._error,
            )

    def _version_of(self, path: Path) -> str | None:
        try:
            changed = path.stat().st_mtime
        except OSError:
            return None
        if self._asked is None or self._asked[:2] != (path, changed):
            self._asked = (path, changed, self._version(path))
        return self._asked[2]

    def choose(self, path: Path) -> FfmpegState:
        """Use the ffmpeg the user pointed at from now on."""
        # The name is checked first: finding out more means running the file.
        if path.stem.lower() != 'ffmpeg' or not path.is_file() or self._version(path) is None:
            raise FfmpegSetupError('not_ffmpeg')
        self._config.update(ffmpeg_path=str(path))
        return self._announce()

    def forget_choice(self) -> FfmpegState:
        """Go back to the ffmpeg the app finds by itself."""
        self._config.update(ffmpeg_path=None)
        return self._announce()

    def check(self) -> FfmpegState:
        """Look again: the user may have installed ffmpeg by their own means."""
        return self._announce()

    def install(self) -> FfmpegState:
        """Start installing ffmpeg with winget; the state and the events tell how it went."""
        with self._lock:
            starting = not self._installing
            if starting:
                winget = self._winget()
                if winget is None:
                    raise FfmpegSetupError('no_winget')
                self._installing = True
                self._error = None
        if starting:
            # Told before winget starts, so that the news of its end can't come first.
            self._publish()
            threading.Thread(target=self._install, args=(winget,), name='offsponsr-ffmpeg', daemon=True).start()
        return self.state()

    def _install(self, winget: Path) -> None:
        error = None
        try:
            self._run(winget)
        except subprocess.TimeoutExpired:
            log.warning('winget did not finish installing ffmpeg in %s seconds', INSTALL_TIMEOUT)
            error = 'install_timeout'
        except OSError:
            log.exception('winget could not be started')
            error = 'install_failed'
        # Whatever winget's exit code says (ffmpeg may have been there already), what counts is whether it is found.
        if error is None and self.path() is None:
            error = 'install_failed'
        try:
            if error is None:
                self._ready()
        finally:
            # The installation is over only when what waited for ffmpeg has been started.
            with self._lock:
                self._installing = False
                self._error = error
            self._publish()

    def shutdown(self) -> None:
        """The app is closing: an installation that ends after this starts nothing."""
        self._closed = True

    def _publish(self) -> FfmpegState:
        state = self.state()
        self._events.publish({'type': 'ffmpeg', 'state': state.to_json()})
        return state

    def _ready(self) -> None:
        if not self._closed:
            for callback in self._when_ready:
                callback()

    def _announce(self) -> FfmpegState:
        """Tell what there is now; if it is an ffmpeg, start what waited for one first."""
        if self.path() is not None:
            self._ready()
        return self._publish()
