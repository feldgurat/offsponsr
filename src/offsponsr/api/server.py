from __future__ import annotations

import socket
import threading
import time
from typing import TYPE_CHECKING

import uvicorn

if TYPE_CHECKING:
    from fastapi import FastAPI

HOST = '127.0.0.1'


class BackgroundServer:
    """Serves the API on a loopback port from a background thread."""

    def __init__(self, app: FastAPI, port: int = 0) -> None:
        # Bind here rather than in uvicorn so the port picked for `port=0` is known before start.
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.bind((HOST, port))
        self.port: int = self._socket.getsockname()[1]

        # log_config=None: uvicorn's default config writes to stdout, which a windowed build doesn't have.
        # A short grace period: an open event stream must not keep the app from quitting.
        config = uvicorn.Config(app, log_config=None, access_log=False, timeout_graceful_shutdown=3)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run,
            kwargs={'sockets': [self._socket]},
            name='offsponsr-api',
            daemon=True,
        )

    @property
    def origin(self) -> str:
        return f'http://{HOST}:{self.port}'

    def start(self, timeout: float = 10) -> None:
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('The API server failed to start')
            time.sleep(0.01)

    def stop(self, timeout: float = 5) -> None:
        self._server.should_exit = True
        self._thread.join(timeout)
