import json
import urllib.error
import urllib.request

import pytest

from offsponsr.api import BackgroundServer

from .conftest import LAUNCH_TOKEN


def test_background_server_serves_and_stops(make_app):
    server = BackgroundServer(make_app())
    server.start()
    try:
        assert server.port > 0
        assert server.origin == f'http://127.0.0.1:{server.port}'

        request = urllib.request.Request(
            f'{server.origin}/api/session',
            data=json.dumps({'token': LAUNCH_TOKEN}).encode(),
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 204
    finally:
        server.stop()

    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(f'{server.origin}/', timeout=1)
