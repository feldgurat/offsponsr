from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from offsponsr.library import Library, LibraryManager
from offsponsr.sync.service import SyncRunningError

# Shows the system folder dialog; None if the user cancelled it.
FolderPicker = Callable[[], Path | None]


class LibraryInfo(BaseModel):
    id: str
    path: str


class LibraryFailureInfo(BaseModel):
    path: str
    code: str


class LibraryStatus(BaseModel):
    library: LibraryInfo | None
    # Set when the library from the previous run couldn't be reopened.
    last_failure: LibraryFailureInfo | None


class LibraryPath(BaseModel):
    path: str


class FolderChoice(BaseModel):
    path: str | None


def _info(library: Library) -> LibraryInfo:
    return LibraryInfo(id=library.id, path=str(library.root))


def library_router(libraries: LibraryManager, pick_folder: FolderPicker, is_busy: Callable[[], bool]) -> APIRouter:
    router = APIRouter()

    def refuse_while_syncing() -> None:
        # Switching closes the current library, and a running sync is writing into it.
        if is_busy():
            raise SyncRunningError

    @router.get('/library')
    def status() -> LibraryStatus:
        library = libraries.current
        failure = libraries.last_failure
        return LibraryStatus(
            library=_info(library) if library else None,
            last_failure=LibraryFailureInfo(path=str(failure.path), code=failure.code) if failure else None,
        )

    @router.post('/library/create')
    def create(body: LibraryPath) -> LibraryInfo:
        refuse_while_syncing()
        return _info(libraries.create(Path(body.path)))

    @router.post('/library/open')
    def open_existing(body: LibraryPath) -> LibraryInfo:
        refuse_while_syncing()
        return _info(libraries.open(Path(body.path)))

    @router.post('/dialogs/folder')
    def choose_folder() -> FolderChoice:
        folder = pick_folder()
        return FolderChoice(path=str(folder) if folder else None)

    return router
