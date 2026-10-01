from __future__ import annotations

import argparse
import secrets
from typing import TYPE_CHECKING

import webview

from offsponsr import __version__
from offsponsr.api import BackgroundServer, create_app

if TYPE_CHECKING:
    from collections.abc import Sequence

APP_TITLE = 'offsponsr'

# Dev mode: the window loads the Vite dev server, which proxies /api and /media to this port.
# Both values are mirrored in frontend/vite.config.ts.
DEV_API_PORT = 8765
DEV_FRONTEND_ORIGIN = 'http://localhost:5173'


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog='offsponsr')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument(
        '--dev',
        action='store_true',
        help=f'load the UI from the Vite dev server ({DEV_FRONTEND_ORIGIN}) and open devtools',
    )
    return parser.parse_args(argv)


def window_url(origin: str, launch_token: str) -> str:
    return f'{origin}/?token={launch_token}'


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)

    launch_token = secrets.token_urlsafe(32)
    server = BackgroundServer(create_app(launch_token), port=DEV_API_PORT if args.dev else 0)
    server.start()
    try:
        origin = DEV_FRONTEND_ORIGIN if args.dev else server.origin
        webview.create_window(APP_TITLE, window_url(origin, launch_token), width=1280, height=860, min_size=(800, 600))
        webview.start(debug=args.dev)
    finally:
        server.stop()


if __name__ == '__main__':
    main()
