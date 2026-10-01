import keyring
import pytest
from fastapi.testclient import TestClient
from requests.adapters import HTTPAdapter

from offsponsr.api import Services, create_app
from offsponsr.auth import AccountService
from offsponsr.config import ConfigStore
from offsponsr.library import LibraryManager
from offsponsr.media import files
from offsponsr.media.downloader import DownloadService
from offsponsr.sponsr import SponsrClient
from offsponsr.sync.events import EventBus
from offsponsr.sync.service import SyncService

from .fakes import FakeFolderPicker, FakeLoginWindow, FakeShell, FakeSponsr, MemoryKeyring

LAUNCH_TOKEN = 'launch-token'


@pytest.fixture(autouse=True)
def sponsr(monkeypatch):
    """Every test talks to a fake sponsr.ru; none can reach the network."""
    fake = FakeSponsr()
    monkeypatch.setattr(HTTPAdapter, 'send', lambda adapter, request, **kwargs: fake.send(adapter, request, **kwargs))
    return fake


@pytest.fixture(autouse=True)
def system_keyring():
    """Every test gets an empty in-memory keyring instead of the real one of this machine."""
    real = keyring.get_keyring()
    fake = MemoryKeyring()
    keyring.set_keyring(fake)
    yield fake
    keyring.set_keyring(real)


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
def library(libraries, tmp_path):
    """An open, empty library."""
    return libraries.create(tmp_path / 'library')


@pytest.fixture
def folder_picker():
    return FakeFolderPicker()


@pytest.fixture
def login_window():
    return FakeLoginWindow()


@pytest.fixture
def account(libraries, login_window):
    return AccountService(libraries, login_window)


@pytest.fixture
def signed_in(account, library, sponsr):
    """The account service of an open library, signed in to the fake sponsr.ru."""
    sponsr.sign_in('good')
    account.login_with_cookie_header('SESS=good; user_id=123456')
    return account


@pytest.fixture
def events():
    return EventBus()


@pytest.fixture
def sync_service(libraries, account, events):
    # No pauses and no waiting between retries: the site is a fake and the tests are in a hurry.
    return SyncService(
        libraries,
        account,
        events,
        make_client=lambda account: SponsrClient(account, pause=0, sleep=lambda seconds: None),
    )


@pytest.fixture
def ffmpeg_path(tmp_path):
    """Where the downloads look for ffmpeg in tests: a file that exists; nothing ever runs it."""
    path = tmp_path / 'ffmpeg-for-tests'
    path.write_bytes(b'')
    return path


@pytest.fixture
def downloads(libraries, account, events, ffmpeg_path, monkeypatch):
    # A dropped connection is retried at once: the site is a fake and the tests are in a hurry.
    monkeypatch.setattr(files, 'RETRY_DELAY', 0)
    service = DownloadService(libraries, account, events, ffmpeg=lambda: ffmpeg_path)
    yield service
    service.shutdown()


@pytest.fixture
def shell():
    return FakeShell()


@pytest.fixture
def services(libraries, account, sync_service, downloads, events, folder_picker, config_store, shell):
    services = Services(libraries, account, sync_service, downloads, events, folder_picker, config_store, shell)
    yield services
    # Before the `libraries` fixture closes the library the sync may still be writing to.
    services.shutdown()


@pytest.fixture
def make_app(web_dir, services):
    def make(*, web_dir=web_dir):
        return create_app(LAUNCH_TOKEN, services, web_dir)

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
