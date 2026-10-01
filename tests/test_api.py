from fastapi.testclient import TestClient

from offsponsr import __version__
from offsponsr.api import create_app
from offsponsr.api.session import SESSION_COOKIE

from .conftest import LAUNCH_TOKEN


def test_session_opens_with_launch_token(client):
    response = client.post('/api/session', json={'token': LAUNCH_TOKEN})

    assert response.status_code == 204
    cookie = response.headers['set-cookie']
    assert cookie.startswith(f'{SESSION_COOKIE}=')
    assert 'HttpOnly' in cookie
    assert 'SameSite=strict' in cookie


def test_session_rejects_wrong_token(client):
    assert client.post('/api/session', json={'token': 'wrong'}).status_code == 403
    assert client.post('/api/session', json={'token': 'не-ascii'}).status_code == 403
    # A wrong guess must not burn the real token.
    assert client.post('/api/session', json={'token': LAUNCH_TOKEN}).status_code == 204


def test_launch_token_works_once(client):
    assert client.post('/api/session', json={'token': LAUNCH_TOKEN}).status_code == 204
    assert client.post('/api/session', json={'token': LAUNCH_TOKEN}).status_code == 403


def test_api_requires_session(client):
    assert client.get('/api/app').status_code == 401

    client.cookies.set(SESSION_COOKIE, 'made-up')
    assert client.get('/api/app').status_code == 401


def test_app_info(session_client):
    response = session_client.get('/api/app')

    assert response.status_code == 200
    assert response.json() == {'name': 'offsponsr', 'version': __version__}


def test_foreign_host_is_rejected(web_dir):
    client = TestClient(create_app(LAUNCH_TOKEN, web_dir), base_url='http://evil.example')

    assert client.post('/api/session', json={'token': LAUNCH_TOKEN}).status_code == 400


def test_frontend_index_and_assets(client):
    assert '<title>index</title>' in client.get('/').text
    assert client.get('/assets/app.js').text == 'console.log(1)'


def test_frontend_serves_index_for_client_routes(client):
    response = client.get('/project/42')

    assert response.status_code == 200
    assert '<title>index</title>' in response.text


def test_unknown_backend_paths_are_not_index(client):
    assert client.get('/api/nope').status_code == 404
    assert client.get('/media/nope.mp4').status_code == 404


def test_frontend_does_not_leave_web_dir(client, web_dir):
    (web_dir.parent / 'secret.txt').write_text('secret', encoding='utf-8')

    assert 'secret' not in client.get('/%2e%2e/secret.txt').text


def test_frontend_not_built(tmp_path):
    client = TestClient(create_app(LAUNCH_TOKEN, tmp_path / 'missing'), base_url='http://127.0.0.1')

    response = client.get('/')

    assert response.status_code == 503
    assert 'npm run build' in response.text
