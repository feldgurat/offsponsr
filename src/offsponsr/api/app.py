from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Self

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from offsponsr import __version__
from offsponsr.api.account import account_router
from offsponsr.api.library import FolderPicker, library_router
from offsponsr.api.projects import projects_router
from offsponsr.api.session import SESSION_COOKIE, SessionGate
from offsponsr.auth import AccountService, AuthError, InvalidCookieError, SiteUnavailableError
from offsponsr.library import LibraryError, LibraryManager
from offsponsr.media.downloader import DownloadService
from offsponsr.sponsr import SponsrError
from offsponsr.sync.events import EventBus
from offsponsr.sync.service import InvalidAddressError, SyncError, SyncService, failure_code

# `npm run build` in frontend/ puts the bundle here.
WEB_DIR = Path(__file__).resolve().parent.parent / 'web'

# Paths the backend owns; the SPA fallback must not answer them with index.html.
BACKEND_PREFIXES = ('api', 'media')


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

    @classmethod
    def build(cls, libraries: LibraryManager, account: AccountService, pick_folder: FolderPicker) -> Self:
        events = EventBus()
        downloads = DownloadService(libraries, account, events)
        # A project that has just been synced gets its pictures and other media downloaded.
        sync = SyncService(libraries, account, events, on_synced=downloads.enqueue_project)
        return cls(libraries, account, sync, downloads, events, pick_folder)

    def is_busy(self) -> bool:
        """Whether something is writing into the library in the background."""
        return self.sync.is_busy() or self.downloads.is_busy()

    def shutdown(self) -> None:
        """Stop the background work and end the event streams, so the server and the library can close."""
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

    app.include_router(public)
    app.include_router(protected)
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

        asset = (web_dir / path).resolve()
        if asset.is_file() and asset.is_relative_to(web_dir):
            return FileResponse(asset)
        # Any other path is a client-side route.
        return FileResponse(index)
