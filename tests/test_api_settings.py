from offsponsr.config import AppConfig

DEFAULTS = {'theme': 'system', 'feed_view': 'stream', 'hide_closed': False}


def test_settings_require_session(client):
    assert client.get('/api/settings').status_code == 401
    assert client.patch('/api/settings', json={'theme': 'dark'}).status_code == 401


def test_settings_start_with_defaults(session_client):
    # No library is needed: the settings belong to the user, not to a library.
    assert session_client.get('/api/settings').json() == DEFAULTS


def test_settings_are_changed_one_at_a_time(session_client, config_store):
    changed = session_client.patch('/api/settings', json={'theme': 'dark'})
    assert changed.json() == {**DEFAULTS, 'theme': 'dark'}

    session_client.patch('/api/settings', json={'feed_view': 'tile', 'hide_closed': True})

    assert session_client.get('/api/settings').json() == {'theme': 'dark', 'feed_view': 'tile', 'hide_closed': True}
    assert config_store.load() == AppConfig(theme='dark', feed_view='tile', hide_closed=True)


def test_settings_keep_the_library_path(session_client, library, config_store):
    session_client.patch('/api/settings', json={'theme': 'light'})

    assert config_store.load().library_path == str(library.root)


def test_bad_settings_are_refused(session_client):
    assert session_client.patch('/api/settings', json={'theme': 'pink'}).status_code == 422
    assert session_client.patch('/api/settings', json={'feed_view': 'pile'}).status_code == 422
    assert session_client.get('/api/settings').json() == DEFAULTS
