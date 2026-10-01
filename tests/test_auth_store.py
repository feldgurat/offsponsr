import keyring
import pytest

from offsponsr.auth.cookies import SiteCookie
from offsponsr.auth.store import (
    KEYRING_SERVICE,
    FallbackSessionStore,
    FileSessionStore,
    KeyringSessionStore,
    SavedSession,
    open_session_store,
)

from .fakes import BrokenKeyring

SESSION = SavedSession(cookies=[SiteCookie(name='SESS', value='abc')], email='reader@example.com')
# Bigger than one keyring entry may be on Windows.
BIG_SESSION = SavedSession(cookies=[SiteCookie(name=f'cookie{index}', value='x' * 400) for index in range(8)])


def test_saved_session_round_trip():
    assert SavedSession.loads(SESSION.dumps()) == SESSION


@pytest.mark.parametrize('text', ['', '{broken', '[]', '{"cookies": [{"name": "sid"}]}', '{"email": "x"}'])
def test_damaged_saved_session(text):
    assert SavedSession.loads(text) is None


def test_keyring_store(system_keyring):
    store = KeyringSessionStore('library-1')

    assert store.load() is None

    store.save(SESSION)

    assert store.load() == SESSION
    assert KeyringSessionStore('library-2').load() is None
    assert all(service == KEYRING_SERVICE for service, _ in system_keyring.entries)

    store.clear()

    assert store.load() is None
    assert system_keyring.entries == {}


def test_keyring_store_splits_long_sessions(system_keyring):
    store = KeyringSessionStore('library-1')

    store.save(BIG_SESSION)

    assert len(system_keyring.entries) > 2
    assert store.load() == BIG_SESSION

    # A shorter session must not leave the tail of the longer one behind.
    store.save(SESSION)

    assert store.load() == SESSION
    assert len(system_keyring.entries) == 2

    store.clear()

    assert system_keyring.entries == {}


def test_clearing_an_empty_keyring_store():
    KeyringSessionStore('library-1').clear()


def test_file_store(tmp_path):
    store = FileSessionStore(tmp_path / 'session.json')

    assert store.load() is None

    store.save(SESSION)

    assert store.load() == SESSION

    store.clear()
    store.clear()

    assert store.load() is None


def test_session_goes_to_the_keyring_when_there_is_one(library, system_keyring):
    store = open_session_store(library)

    store.save(SESSION)

    assert store.load() == SESSION
    assert system_keyring.entries
    assert not (library.root / 'session.json').exists()


def test_session_falls_back_to_a_file_without_a_keyring(library):
    keyring.set_keyring(BrokenKeyring())
    store = open_session_store(library)

    assert store.load() is None

    store.save(SESSION)

    assert (library.root / 'session.json').is_file()
    assert store.load() == SESSION

    store.clear()

    assert store.load() is None
    assert not (library.root / 'session.json').exists()


def test_keyring_coming_back_takes_the_session_over(library, system_keyring):
    keyring.set_keyring(BrokenKeyring())
    open_session_store(library).save(SESSION)
    keyring.set_keyring(system_keyring)
    store = open_session_store(library)

    # Still readable from the file...
    assert store.load() == SESSION

    # ...and the next save moves it into the keyring.
    store.save(SESSION)

    assert system_keyring.entries
    assert not (library.root / 'session.json').exists()
    assert store.load() == SESSION


def test_fallback_store_types(library):
    assert isinstance(open_session_store(library), FallbackSessionStore)
