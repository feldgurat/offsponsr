from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from offsponsr import __version__
from offsponsr.api.account import account_router
from offsponsr.api.library import FolderPicker, library_router
from offsponsr.api.session import SESSION_COOKIE, SessionGate
from offsponsr.auth import AccountService, AuthError, InvalidCookieError, SiteUnavailableError
from offsponsr.library import LibraryError, LibraryManager

# `npm run build` in frontend/ puts the bundle here.
WEB_DIR = Path(__file__).resolve().parent.parent / 'web'

# Paths the backend owns; the SPA fallback must not answer them with index.html.
BACKEND_PREFIXES = ('api', 'media')


class SessionRequest(BaseModel):
    token: str


class AppInfo(BaseModel):
    name: str
    version: str


def create_app(
    launch_token: str,
    libraries: LibraryManager,
    account: AccountService,
    pick_folder: FolderPicker,
    web_dir: Path = WEB_DIR,
) -> FastAPI:
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

    protected.include_router(library_router(libraries, pick_folder))
    protected.include_router(account_router(account))

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
