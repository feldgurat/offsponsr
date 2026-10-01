from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Self

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from offsponsr import __version__
from offsponsr.api.account import account_router
from offsponsr.api.ffmpeg import ProgramPicker, ffmpeg_router
from offsponsr.api.files import media_files_router, shell_router
from offsponsr.api.library import FolderPicker, library_router
from offsponsr.api.posts import posts_router
from offsponsr.api.projects import projects_router
from offsponsr.api.session import SESSION_COOKIE, SessionGate
from offsponsr.api.settings import settings_router
from offsponsr.auth import AccountService, AuthError, InvalidCookieError, SiteUnavailableError
from offsponsr.config import ConfigStore
from offsponsr.library import LibraryError, LibraryManager
from offsponsr.media.downloader import NO_FFMPEG, DownloadService
from offsponsr.media.ffmpeg_setup import FfmpegSetup, FfmpegSetupError
from offsponsr.shell import Shell
from offsponsr.sponsr import SponsrError
from offsponsr.sync.events import EventBus
from offsponsr.sync.service import InvalidAddressError, SyncError, SyncService, failure_code

# `npm run build` in frontend/ puts the bundle here.
WEB_DIR = Path(__file__).resolve().parent.parent / 'web'

# Paths the backend owns; the SPA fallback must not answer them with index.html.
BACKEND_PREFIXES = ('api', 'media')

# What the window may load and run. The texts of posts are somebody else's HTML: whatever gets
# past the UI's own cleaning still can't run a script or talk to anything but this server.
CONTENT_SECURITY_POLICY = '; '.join(
    (
        "default-src 'self'",
        "script-src 'self'",
        # The UI kit writes its styles into the page as it goes.
        "style-src 'self' 'unsafe-inline'",
        # Pictures not downloaded yet are shown from where they are on the web.
        "img-src 'self' data: https:",
        "media-src 'self'",
        # Third-party players (YouTube and the like); which ones is decided by the UI.
        'frame-src https:',
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
    )
)


class SessionRequest(BaseModel):
    token: str


class AppInfo(BaseModel):
    name: str
    version: str


@dataclass(frozen=True)
class Services:
    """Everything the API hands requests over to."""

    libraries: LibraryManager
    account: AccountService
    sync: SyncService
    downloads: DownloadService
    events: EventBus
    pick_folder: FolderPicker
    config: ConfigStore
    ffmpeg: FfmpegSetup
    pick_program: ProgramPicker
    shell: Shell = field(default_factory=Shell)

    @classmethod
    def build(
        cls,
        libraries: LibraryManager,
        account: AccountService,
        pick_folder: FolderPicker,
        pick_program: ProgramPicker,
        config: ConfigStore,
    ) -> Self:
        events = EventBus()
        ffmpeg = FfmpegSetup(config, events)
        downloads = DownloadService(libraries, account, events, ffmpeg=ffmpeg.path)
        # Once there is an ffmpeg, the videos that failed for the lack of one are tried again.
        ffmpeg.when_ready(lambda: downloads.enqueue_failed(NO_FFMPEG))
        # A project that has just been synced gets its pictures and other media downloaded.
        sync = SyncService(libraries, account, events, on_synced=downloads.enqueue_project)
        return cls(libraries, account, sync, downloads, events, pick_folder, config, ffmpeg, pick_program)

    def is_busy(self) -> bool:
        """Whether something is writing into the library in the background."""
        return self.sync.is_busy() or self.downloads.is_busy()

    def shutdown(self) -> None:
        """Stop the background work and end the event streams, so the server and the library can close."""
        self.ffmpeg.shutdown()
        self.sync.shutdown()
        self.downloads.shutdown()
        self.events.close()


def create_app(launch_token: str, services: Services, web_dir: Path = WEB_DIR) -> FastAPI:
    gate = SessionGate(launch_token)

    app = FastAPI(title='offsponsr', version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    # Blocks DNS rebinding: a page on another host name can't reach the API through the browser.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])

    @app.exception_handler(LibraryError)
    def library_error(_request: Request, error: LibraryError) -> JSONResponse:
        # The UI turns `code` into a message in the user's language.
        return JSONResponse({'code': error.code, 'path': str(error.path)}, status_code=status.HTTP_409_CONFLICT)

    @app.exception_handler(AuthError)
    def auth_error(_request: Request, error: AuthError) -> JSONResponse:
        if isinstance(error, SiteUnavailableError):
            status_code = status.HTTP_502_BAD_GATEWAY
        elif isinstance(error, InvalidCookieError):
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            status_code = status.HTTP_409_CONFLICT
        return JSONResponse({'code': error.code}, status_code=status_code)

    @app.exception_handler(SyncError)
    def sync_error(_request: Request, error: SyncError) -> JSONResponse:
        invalid = isinstance(error, InvalidAddressError)
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT if invalid else status.HTTP_409_CONFLICT
        return JSONResponse({'code': error.code}, status_code=status_code)

    @app.exception_handler(FfmpegSetupError)
    def ffmpeg_error(_request: Request, error: FfmpegSetupError) -> JSONResponse:
        missing = error.code == 'no_winget'
        status_code = status.HTTP_409_CONFLICT if missing else status.HTTP_422_UNPROCESSABLE_CONTENT
        return JSONResponse({'code': error.code}, status_code=status_code)

    @app.exception_handler(SponsrError)
    def site_error(_request: Request, error: SponsrError) -> JSONResponse:
        return JSONResponse({'code': failure_code(error)}, status_code=status.HTTP_502_BAD_GATEWAY)

    def require_session(session_id: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> None:
        if not gate.is_valid(session_id):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED)

    public = APIRouter(prefix='/api')
    protected = APIRouter(prefix='/api', dependencies=[Depends(require_session)])

    @public.post('/session', status_code=status.HTTP_204_NO_CONTENT)
    def open_session(body: SessionRequest, response: Response) -> None:
        session_id = gate.exchange(body.token)
        if session_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN)
        response.set_cookie(SESSION_COOKIE, session_id, httponly=True, samesite='strict')

    @protected.get('/app')
    def app_info() -> AppInfo:
        return AppInfo(name='offsponsr', version=__version__)

    protected.include_router(library_router(services.libraries, services.pick_folder, services.is_busy))
    protected.include_router(account_router(services.account))
    protected.include_router(projects_router(services.libraries, services.sync, services.downloads, services.events))
    protected.include_router(posts_router(services.libraries))
    protected.include_router(shell_router(services.libraries, services.shell))
    protected.include_router(settings_router(services.config))
    protected.include_router(ffmpeg_router(services.ffmpeg, services.pick_program))

    media = APIRouter(prefix='/media', dependencies=[Depends(require_session)])
    media.include_router(media_files_router(services.libraries))

    app.include_router(public)
    app.include_router(protected)
    app.include_router(media)
    _serve_frontend(app, web_dir)
    return app


def _serve_frontend(app: FastAPI, web_dir: Path) -> None:
    web_dir = web_dir.resolve()

    @app.get('/{path:path}', include_in_schema=False)
    def frontend(path: str) -> Response:
        if path.split('/', 1)[0] in BACKEND_PREFIXES:
            raise HTTPException(status.HTTP_404_NOT_FOUND)

        index = web_dir / 'index.html'
        if not index.is_file():
            return PlainTextResponse(
                'The frontend is not built. Run `npm run build` in frontend/.',
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # The policy goes with every file: the page can be asked for by its own name as well.
        headers = {'Content-Security-Policy': CONTENT_SECURITY_POLICY}
        asset = (web_dir / path).resolve()
        if asset.is_file() and asset.is_relative_to(web_dir):
            return FileResponse(asset, headers=headers)
        # Any other path is a client-side route.
        return FileResponse(index, headers=headers)
