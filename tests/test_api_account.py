from offsponsr.auth.cookies import SiteCookie

from .fakes import REFRESH_URL

SIGNED_OUT = {'signed_in': False, 'email': None, 'expired': False}
SIGNED_IN = {'signed_in': True, 'email': 'reader@example.com', 'expired': False}


def test_account_api_requires_session(client):
    assert client.get('/api/account').status_code == 401
    assert client.post('/api/account/login').status_code == 401
    assert client.post('/api/account/login/cookie', json={'cookie': 'SESS=good'}).status_code == 401
    assert client.post('/api/account/logout').status_code == 401


def test_account_without_a_library(session_client):
    assert session_client.get('/api/account').json() == SIGNED_OUT

    response = session_client.post('/api/account/login')

    assert response.status_code == 409
    assert response.json() == {'code': 'no_library'}


def test_login_and_logout(session_client, library, login_window, sponsr):
    sponsr.sign_in('good')
    login_window.pages = [[SiteCookie(name='SESS', value='good')]]

    assert session_client.post('/api/account/login').json() == SIGNED_IN
    assert session_client.get('/api/account').json() == SIGNED_IN
    assert session_client.post('/api/account/logout').json() == SIGNED_OUT
    assert session_client.get('/api/account').json() == SIGNED_OUT


def test_cancelled_login(session_client, library, login_window):
    response = session_client.post('/api/account/login')

    assert response.status_code == 200
    assert response.json() == SIGNED_OUT


def test_login_with_cookie(session_client, library, sponsr):
    sponsr.sign_in('good')

    response = session_client.post('/api/account/login/cookie', json={'cookie': 'SESS=good'})

    assert response.json() == SIGNED_IN


def test_login_with_a_cookie_the_site_rejects(session_client, library):
    response = session_client.post('/api/account/login/cookie', json={'cookie': 'SESS=stale'})

    assert response.status_code == 422
    assert response.json() == {'code': 'invalid_cookie'}


def test_login_with_another_account(session_client, library, sponsr):
    sponsr.sign_in('good', user_id=1)
    sponsr.sign_in('other', user_id=2)
    session_client.post('/api/account/login/cookie', json={'cookie': 'SESS=good'})

    response = session_client.post('/api/account/login/cookie', json={'cookie': 'SESS=other'})

    assert response.status_code == 409
    assert response.json() == {'code': 'different_account'}
    assert session_client.get('/api/account').json() == SIGNED_IN


def test_login_with_cookie_while_the_site_is_down(session_client, library, sponsr):
    sponsr.routes[REFRESH_URL] = lambda request: (500, {}, [])

    response = session_client.post('/api/account/login/cookie', json={'cookie': 'SESS=good'})

    assert response.status_code == 502
    assert response.json() == {'code': 'site_unavailable'}
