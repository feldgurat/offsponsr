import json
import threading
import time

from fastapi.testclient import TestClient

from . import site_data
from .conftest import LAUNCH_TOKEN
from .test_sync_service import wait_until_idle

PID = site_data.PROJECT_ID
IDLE = {'running': None, 'queue': [], 'failures': [], 'cancelling': False}


def test_projects_api_requires_session(client):
    for path in ('/api/projects', '/api/subscriptions', '/api/sync', '/api/events'):
        assert client.get(path).status_code == 401
    assert client.post('/api/projects', json={}).status_code == 401
    assert client.post('/api/sync', json={}).status_code == 401
    assert client.post('/api/sync/cancel').status_code == 401


def test_projects_need_a_library(session_client):
    response = session_client.get('/api/projects')

    assert response.status_code == 409
    assert response.json() == {'code': 'no_library'}


def test_empty_library(session_client, library):
    assert session_client.get('/api/projects').json() == []
    assert session_client.get('/api/sync').json() == IDLE


def test_subscriptions(session_client, signed_in):
    assert session_client.get('/api/subscriptions').json() == [
        {
            'id': PID,
            'url': site_data.PROJECT_URL,
            'title': 'Вымышленный альманах',
            'owner_name': 'Автор Выдуманный',
            'level_name': 'Читатель',
            'in_library': False,
        }
    ]


def test_subscriptions_when_signed_out(session_client, library):
    response = session_client.get('/api/subscriptions')

    assert response.status_code == 409
    assert response.json() == {'code': 'not_signed_in'}


def test_add_projects_and_see_them_downloaded(session_client, signed_in, sync_service):
    response = session_client.post('/api/projects', json={'subscription_ids': [PID]})
    wait_until_idle(sync_service)

    assert response.json() == {'added': [PID]}
    [project] = session_client.get('/api/projects').json()
    assert project.pop('last_synced_at') is not None
    assert project == {
        'id': PID,
        'url': site_data.PROJECT_URL,
        'title': 'Вымышленный альманах',
        'intent': 'на выдуманные тексты',
        # Not downloaded yet, so the pictures are shown from where the site keeps them.
        'logo': 'https://media.sponsr.ru/images/projects/42/4242/logo@2x.webp?5d41402abc4b2a76',
        'cover': 'https://media.sponsr.ru/images/projects/42/4242/bg.webp?5d41402abc4b2a76',
        'added_via': 'subscription',
        'sync_enabled': True,
        'media_mode_audio': 'auto',
        'media_mode_video': 'manual',
        'media_mode_attach': 'auto',
        'video_quality': None,
        'posts': 6,
        'posts_without_text': 0,
        'posts_deleted': 0,
        'posts_closed': 1,
    }
    assert session_client.get('/api/sync').json() == IDLE
    assert session_client.get('/api/subscriptions').json()[0]['in_library'] is True


def test_add_by_a_bad_address(session_client, signed_in):
    response = session_client.post('/api/projects', json={'address': 'https://example.com/x'})

    assert response.status_code == 422
    assert response.json() == {'code': 'invalid_address'}


def test_add_a_project_that_does_not_exist(session_client, signed_in, sponsr):
    sponsr.routes['https://sponsr.ru/nobody-home/'] = lambda request: (404, '<html>404</html>', [])

    response = session_client.post('/api/projects', json={'address': 'nobody-home'})

    assert response.status_code == 409
    assert response.json() == {'code': 'project_not_found'}


def test_site_trouble_while_adding(session_client, signed_in, sponsr):
    sponsr.routes['https://sponsr.ru/some-project/'] = lambda request: (200, '<html>redesigned</html>', [])

    response = session_client.post('/api/projects', json={'address': 'some-project'})

    assert response.status_code == 502
    assert response.json() == {'code': 'site_changed'}


def test_start_and_cancel(session_client, signed_in, sync_service):
    session_client.post('/api/projects', json={'subscription_ids': [PID]})
    wait_until_idle(sync_service)

    started = session_client.post('/api/sync', json={'project_ids': [PID]})
    assert started.status_code == 200
    assert set(started.json()) == {'running', 'queue', 'failures', 'cancelling'}
    wait_until_idle(sync_service)

    assert session_client.post('/api/sync', json={}).status_code == 200
    wait_until_idle(sync_service)
    assert session_client.post('/api/sync/cancel').json() == IDLE


def test_library_cannot_be_switched_under_a_sync(
    session_client, library, sync_service, monkeypatch, make_app, tmp_path
):
    monkeypatch.setattr(sync_service, 'is_busy', lambda: True)
    client = TestClient(make_app(), base_url='http://127.0.0.1')
    client.post('/api/session', json={'token': LAUNCH_TOKEN})

    for action in ('create', 'open'):
        response = client.post(f'/api/library/{action}', json={'path': str(tmp_path / 'another')})

        assert response.status_code == 409
        assert response.json() == {'code': 'sync_running'}


def test_event_stream(session_client, library, events):
    def publish_then_close():
        # The stream must be listening before anything is published.
        deadline = time.monotonic() + 5
        while not events._listeners and time.monotonic() < deadline:
            time.sleep(0.01)
        events.publish({'type': 'projects'})
        events.publish({'type': 'sync', 'state': {'running': {'title': 'Проект'}}})
        events.close()

    threading.Thread(target=publish_then_close, daemon=True).start()

    response = session_client.get('/api/events')

    assert response.headers['content-type'].startswith('text/event-stream')
    received = [json.loads(line.removeprefix('data: ')) for line in response.text.splitlines() if line]
    assert received == [
        {'type': 'sync', 'state': IDLE},
        {'type': 'downloads', 'state': {'active': [], 'queued': 0, 'done': 0, 'failed': 0, 'cancelling': False}},
        {'type': 'projects'},
        {'type': 'sync', 'state': {'running': {'title': 'Проект'}}},
    ]
    # Cyrillic goes out as it is, not as escapes.
    assert 'Проект' in response.text


NO_DOWNLOADS = {'active': [], 'queued': 0, 'done': 0, 'failed': 0, 'cancelling': False}


def test_downloads_api_requires_session(client):
    assert client.get('/api/downloads').status_code == 401
    assert client.post('/api/downloads/cancel').status_code == 401
    assert client.post(f'/api/projects/{PID}/download').status_code == 401
    assert client.post('/api/media/1/download').status_code == 401


def test_downloads_api(session_client, signed_in, sync_service, downloads, sponsr):
    session_client.post('/api/projects', json={'subscription_ids': [PID]})
    wait_until_idle(sync_service)
    sponsr.serve_file('https://media.sponsr.ru/', b'any file', needs_session=False)

    assert session_client.get('/api/downloads').json() == NO_DOWNLOADS

    # A logo, a cover, two post covers, a picture and an audio file.
    assert session_client.post(f'/api/projects/{PID}/download').json() == {'queued': 6}
    deadline = time.monotonic() + 10
    while downloads.is_busy():
        assert time.monotonic() < deadline
        time.sleep(0.01)

    assert session_client.get('/api/downloads').json() == {**NO_DOWNLOADS, 'done': 6}
    assert session_client.post(f'/api/projects/{PID}/download').json() == {'queued': 0}
    assert session_client.post('/api/media/999999/download').json() == {'queued': 0}
    assert session_client.post('/api/downloads/cancel').json() == {**NO_DOWNLOADS, 'done': 6}
