"""The library's files: served to the UI, opened in other programs, shown in their folders."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from offsponsr.api.urls import SHOWN_KINDS
from offsponsr.auth import NoLibraryError
from offsponsr.library import Library, LibraryManager
from offsponsr.library.models import Media, MediaKind, MediaState, Post, Project
from offsponsr.shell import Shell, ShellError, is_openable, is_web_link

# What the files are served as, by extension. The list is the app's own: what the system knows
# about file types differs from one machine to the next.
_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.avif': 'image/avif',
    '.bmp': 'image/bmp',
    '.svg': 'image/svg+xml',
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.aac': 'audio/aac',
    '.ogg': 'audio/ogg',
    '.oga': 'audio/ogg',
    '.opus': 'audio/ogg',
    '.wav': 'audio/wav',
    '.flac': 'audio/flac',
    '.mp4': 'video/mp4',
    '.m4v': 'video/mp4',
    '.webm': 'video/webm',
    '.mov': 'video/quicktime',
    '.mkv': 'video/x-matroska',
}
# A file of each kind is served only as that kind. One that claims to be something else (an HTML
# page posing as a picture, say) goes out as plain bytes and the page can do nothing with it.
_TYPE_PREFIXES = {MediaKind.IMAGE: 'image/', MediaKind.AUDIO: 'audio/', MediaKind.VIDEO: 'video/'}
_FALLBACK_TYPE = 'application/octet-stream'

_HEADERS = {
    # The files change in place (a cover is downloaded again when the site changes it), so the
    # window always asks whether its copy is still good.
    'Cache-Control': 'no-cache',
    'X-Content-Type-Options': 'nosniff',
    # Opened as a page of its own, a file gets no scripts and no access to the app.
    'Content-Security-Policy': "default-src 'none'; sandbox",
}


class Link(BaseModel):
    url: str


def _file_response(path: Path, type_prefix: str) -> FileResponse:
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    known = _TYPES.get(path.suffix.lower(), '')
    media_type = known if known.startswith(type_prefix) else _FALLBACK_TYPE
    # FileResponse answers Range requests itself, which is what lets audio and video be rewound.
    return FileResponse(path, media_type=media_type, headers=_HEADERS)


def media_files_router(libraries: LibraryManager) -> APIRouter:
    """Mounted at /media: what `<img>`, `<audio>` and `<video>` in the UI load."""
    router = APIRouter()

    def open_library() -> Library:
        library = libraries.current
        if library is None:
            raise NoLibraryError
        return library

    @router.get('/posts/{post_id}/cover')
    def post_cover(post_id: int) -> FileResponse:
        library = open_library()
        with library.session() as db:
            post = db.get(Post, post_id)
            relative = post.cover_path if post else None
        if not relative:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return _file_response(library.file(relative), 'image/')

    @router.get('/projects/{project_id}/{picture}')
    def project_picture(project_id: int, picture: str) -> FileResponse:
        if picture not in ('logo', 'cover'):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        library = open_library()
        with library.session() as db:
            project = db.get(Project, project_id)
            relative = (project.logo_path if picture == 'logo' else project.cover_path) if project else None
        if not relative:
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return _file_response(library.file(relative), 'image/')

    @router.get('/{media_id}')
    def media_file(media_id: int) -> FileResponse:
        library = open_library()
        with library.session() as db:
            media = db.get(Media, media_id)
            if media is None or media.state != MediaState.DONE or not media.local_path or media.kind not in SHOWN_KINDS:
                raise HTTPException(status.HTTP_404_NOT_FOUND)
            relative, kind = media.local_path, media.kind
        return _file_response(library.file(relative), _TYPE_PREFIXES[kind])

    return router


def shell_router(libraries: LibraryManager, shell: Shell) -> APIRouter:
    """Mounted under /api: things the UI asks the system to do with a file or a link."""
    router = APIRouter()

    def downloaded(media_id: int) -> Path:
        library = libraries.current
        if library is None:
            raise NoLibraryError
        with library.session() as db:
            media = db.get(Media, media_id)
            if media is None or media.state != MediaState.DONE or not media.local_path:
                raise HTTPException(status.HTTP_404_NOT_FOUND)
            path = library.file(media.local_path)
        if not path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        return path

    def run(action: str, target: Path | str) -> None:
        try:
            getattr(shell, action)(target)
        except ShellError as error:
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail='shell') from error

    @router.post('/media/{media_id}/reveal', status_code=status.HTTP_204_NO_CONTENT)
    def reveal(media_id: int) -> None:
        """Show the downloaded file in the system's file manager."""
        run('reveal', downloaded(media_id))

    @router.post('/media/{media_id}/open', status_code=status.HTTP_204_NO_CONTENT)
    def open_file(media_id: int) -> None:
        """Open the downloaded file with the system's program for it; documents and media only."""
        path = downloaded(media_id)
        if not is_openable(path):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT)
        run('open_file', path)

    @router.post('/open-link', status_code=status.HTTP_204_NO_CONTENT)
    def open_link(body: Link) -> None:
        """Open a link from a post in the user's browser instead of the app's window."""
        if not is_web_link(body.url):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT)
        run('open_url', body.url)

    return router
