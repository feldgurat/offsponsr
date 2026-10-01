from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_DIR_ENV = 'OFFSPONSR_CONFIG_DIR'


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


class ConfigStore:
    """Keeps AppConfig in a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or user_config_dir() / 'config.json'

    def load(self) -> AppConfig:
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            # Missing or damaged settings are not worth failing the start over.
            return AppConfig()
        if not isinstance(data, dict):
            return AppConfig()

        library_path = data.get('library_path')
        return AppConfig(library_path=library_path if isinstance(library_path, str) else None)

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write aside and swap, so a crash mid-write can't leave a half-written file.
        temporary = self.path.with_name(f'{self.path.name}.tmp')
        temporary.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.path)
