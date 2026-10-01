from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

CONFIG_DIR_ENV = 'OFFSPONSR_CONFIG_DIR'

THEMES = ('system', 'light', 'dark')
# How a project's posts are laid out: the same four ways sponsr.ru has.
FEED_VIEWS = ('stream', 'feed', 'tile', 'list')


def user_config_dir() -> Path:
    """The per-user directory for app settings that don't belong to a library."""
    if override := os.environ.get(CONFIG_DIR_ENV):
        return Path(override)
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming'
    elif sys.platform == 'darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config'
    return Path(base) / 'offsponsr'


@dataclass
class AppConfig:
    # The library opened last; the app reopens it on start.
    library_path: str | None = None
    theme: str = 'system'
    feed_view: str = 'stream'
    # Leave the posts the account can't read out of the feeds.
    hide_closed: bool = False
    # The ffmpeg the user pointed at; without it the app looks for one itself.
    ffmpeg_path: str | None = None


# Settings that hold a path, or nothing.
_PATHS = ('library_path', 'ffmpeg_path')


def _valid(name: str, value: Any) -> bool:
    if name in _PATHS:
        return isinstance(value, str)
    if name == 'theme':
        return value in THEMES
    if name == 'feed_view':
        return value in FEED_VIEWS
    return isinstance(value, bool)


class ConfigStore:
    """Keeps AppConfig in a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_config_dir() / 'config.json'
        self._lock = threading.Lock()

    def load(self) -> AppConfig:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            # Missing or damaged settings are not worth failing the start over.
            return AppConfig()
        if not isinstance(data, dict):
            return AppConfig()

        # Anything unknown or of the wrong kind falls back to its default.
        known = {field.name for field in fields(AppConfig)}
        return AppConfig(**{name: value for name, value in data.items() if name in known and _valid(name, value)})

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write aside and swap, so a crash mid-write can't leave a half-written file.
        temporary = self.path.with_name(f'{self.path.name}.tmp')
        temporary.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)

    def update(self, **changes: Any) -> AppConfig:
        """Change some settings and keep the rest; safe to call from several threads."""
        with self._lock:
            config = self.load()
            for name, value in changes.items():
                if not _valid(name, value) and not (name in _PATHS and value is None):
                    raise ValueError(f'Bad value for {name}')
                setattr(config, name, value)
            self.save(config)
            return config
