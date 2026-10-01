import pytest
from fastapi.testclient import TestClient

from offsponsr.api import create_app

LAUNCH_TOKEN = 'launch-token'


@pytest.fixture
def web_dir(tmp_path):
    """A stand-in for the built frontend."""
    root = tmp_path / 'web'
    (root / 'assets').mkdir(parents=True)
    (root / 'index.html').write_text('<!doctype html><title>index</title>', encoding='utf-8')
    (root / 'assets' / 'app.js').write_text('console.log(1)', encoding='utf-8')
    return root


@pytest.fixture
def client(web_dir):
    # The app only answers to loopback host names, so the default `testserver` won't do.
    return TestClient(create_app(LAUNCH_TOKEN, web_dir), base_url='http://127.0.0.1')


@pytest.fixture
def session_client(client):
    """A client that has already traded the launch token for a session."""
    client.post('/api/session', json={'token': LAUNCH_TOKEN})
    return client
