from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from offsponsr.library.db import UnknownRevisionError, migrate, open_engine
from offsponsr.library.errors import (
    FolderNotEmptyError,
    LibraryExistsError,
    LibraryMissingError,
    LibraryTooNewError,
    NotALibraryError,
)
from offsponsr.library.lock import LibraryLock

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy import Engine

MANIFEST_NAME = 'library.json'
DB_NAME = 'offsponsr.db'
PROJECTS_DIR = 'projects'
TMP_DIR = '.tmp'

# The version of the folder layout (not of the database schema, which migrations track).
FORMAT_VERSION = 1

# Files the OS drops into folders on its own; they don't make a folder "not empty".
OS_CLUTTER = frozenset({'.DS_Store', 'Thumbs.db', 'desktop.ini'})


@dataclass(frozen=True)
class Manifest:
    """library.json: what marks a folder as a library."""

    format: int
    id: str
    created_at: datetime

    @classmethod
    def new(cls) -> Manifest:
        return cls(format=FORMAT_VERSION, id=str(uuid.uuid4()), created_at=datetime.now(UTC))

    @classmethod
    def read(cls, root: Path) -> Manifest:
        try:
            data = json.loads((root / MANIFEST_NAME).read_text(encoding='utf-8'))
            return cls(
                format=int(data['format']),
                id=str(data['id']),
                created_at=datetime.fromisoformat(data['created_at']),
            )
        except (OSError, ValueError, KeyError, TypeError):
            raise NotALibraryError(root) from None

    def write(self, root: Path) -> None:
        data = {'format': self.format, 'id': self.id, 'created_at': self.created_at.isoformat()}
        (root / MANIFEST_NAME).write_text(json.dumps(data, indent=2), encoding='utf-8')


class Library:
    """An open library folder: its manifest, its lock and its database."""

    def __init__(self, root: Path, manifest: Manifest, lock: LibraryLock, engine: Engine) -> None:
        self.root = root
        self.manifest = manifest
        self._lock = lock
        self._engine = engine

    @classmethod
    def create(cls, root: Path) -> Library:
        """Turn an empty (or not yet existing) folder into a library and open it."""
        root = root.expanduser().absolute()
        if root.exists():
            if not root.is_dir():
                raise LibraryMissingError(root)
            if (root / MANIFEST_NAME).exists():
                raise LibraryExistsError(root)
            if any(entry.name not in OS_CLUTTER for entry in root.iterdir()):
                raise FolderNotEmptyError(root)
        else:
            root.mkdir(parents=True)

        Manifest.new().write(root)
        return cls.open(root)

    @classmethod
    def open(cls, root: Path) -> Library:
        root = root.expanduser().absolute()
        if not root.is_dir():
            raise LibraryMissingError(root)

        manifest = Manifest.read(root)
        if manifest.format > FORMAT_VERSION:
            raise LibraryTooNewError(root)

        lock = LibraryLock(root)
        lock.acquire()
        engine = open_engine(root / DB_NAME)
        try:
            migrate(engine)
            (root / PROJECTS_DIR).mkdir(exist_ok=True)
            (root / TMP_DIR).mkdir(exist_ok=True)
        except UnknownRevisionError:
            engine.dispose()
            lock.release()
            raise LibraryTooNewError(root) from None
        except BaseException:
            engine.dispose()
            lock.release()
            raise

        return cls(root, manifest, lock, engine)

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def projects_dir(self) -> Path:
        return self.root / PROJECTS_DIR

    @property
    def tmp_dir(self) -> Path:
        """Where unfinished downloads live."""
        return self.root / TMP_DIR

    def session(self) -> Session:
        return Session(self._engine)

    def close(self) -> None:
        self._engine.dispose()
        self._lock.release()
