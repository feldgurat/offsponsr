import pytest
from fastapi.testclient import TestClient

from offsponsr.api import create_app
from offsponsr.config import ConfigStore
from offsponsr.library import LibraryManager

LAUNCH_TOKEN = 'launch-token'


class FakeFolderPicker:
    """Stands in for the system folder dialog: returns whatever the test put in `choice`."""

    def __init__(self):
        self.choice = None

    def __call__(self):
        return self.choice


@pytest.fixture
def web_dir(tmp_path):
    """A stand-in for the built frontend."""
    root = tmp_path / 'web'
    (root / 'assets').mkdir(parents=True)
    (root / 'index.html').write_text('<!doctype html><title>index</title>', encoding='utf-8')
    (root / 'assets' / 'app.js').write_text('console.log(1)', encoding='utf-8')
    return root


@pytest.fixture
def config_store(tmp_path):
    return ConfigStore(tmp_path / 'config' / 'config.json')


@pytest.fixture
def libraries(config_store):
    manager = LibraryManager(config_store)
    yield manager
    # Open libraries hold file locks; Windows won't delete tmp_path until they are released.
    manager.close()


@pytest.fixture
def folder_picker():
    return FakeFolderPicker()


@pytest.fixture
def make_app(web_dir, libraries, folder_picker):
    def make(*, web_dir=web_dir):
        return create_app(LAUNCH_TOKEN, libraries, folder_picker, web_dir)

    return make


@pytest.fixture
def client(make_app):
    # The app only answers to loopback host names, so the default `testserver` won't do.
    return TestClient(make_app(), base_url='http://127.0.0.1')


@pytest.fixture
def session_client(client):
    """A client that has already traded the launch token for a session."""
    client.post('/api/session', json={'token': LAUNCH_TOKEN})
    return client
