from datetime import UTC, datetime, timedelta

import pytest
import requests

from offsponsr.auth import SessionExpiredError, SiteUnavailableError
from offsponsr.auth.cookies import SiteCookie
from offsponsr.auth.session import DEFAULT_LIFETIME, USER_AGENT, SponsrSession

from .fakes import REFRESH_URL

SID = SiteCookie(name='SESS', value='good')


def in_seconds(seconds):
    return int((datetime.now(UTC) + timedelta(seconds=seconds)).timestamp())


def test_token_comes_from_the_session_cookies(sponsr):
    sponsr.sign_in('good', email='reader@example.com', exp=in_seconds(3600))
    session = SponsrSession([SiteCookie(name='_ym_uid', value='1'), SID, SiteCookie(name='user_id', value='123456')])

    token = session.token()

    assert token.value.count('.') == 2
    assert token.email == 'reader@example.com'
    assert token.user_id == 123456
    assert token.expires_at == datetime.fromtimestamp(in_seconds(3600), UTC)
    assert session.email == 'reader@example.com'
    request = sponsr.calls()[0]
    # The analytics cookie stays behind.
    assert request.headers['Cookie'] == 'SESS=good; user_id=123456'
    assert request.headers['User-Agent'] == USER_AGENT


def test_no_session_cookie_means_no_session(sponsr):
    session = SponsrSession([SiteCookie(name='user_id', value='123456')])

    with pytest.raises(SessionExpiredError):
        session.token()

    assert sponsr.requests == []


def test_token_is_reused_while_fresh(sponsr):
    sponsr.sign_in('good', exp=in_seconds(3600))
    session = SponsrSession([SID])

    assert session.token() is session.token()
    assert len(sponsr.calls()) == 1


def test_token_is_renewed_shortly_before_it_expires(sponsr):
    # Four minutes left: inside the five-minute margin.
    sponsr.sign_in('good', exp=in_seconds(240))
    session = SponsrSession([SID])

    session.token()
    session.token()

    assert len(sponsr.calls()) == 2


def test_rejected_cookies_mean_an_expired_session(sponsr):
    session = SponsrSession([SiteCookie(name='SESS', value='stale')])

    with pytest.raises(SessionExpiredError):
        session.token()


@pytest.mark.parametrize(
    'reply',
    [
        (500, {'message': 'oops'}, []),
        (200, {'data': {}}, []),
        (200, {'data': {'access_token': ''}}, []),
        (200, {'data': None}, []),
        (200, b'<html>maintenance</html>', []),
    ],
)
def test_unexpected_answers_are_not_taken_for_an_expired_session(sponsr, reply):
    sponsr.routes[REFRESH_URL] = lambda request: reply
    session = SponsrSession([SID])

    with pytest.raises(SiteUnavailableError):
        session.token()


def test_network_failure(sponsr):
    def unreachable(request):
        raise requests.ConnectionError('no route to host')

    sponsr.routes[REFRESH_URL] = unreachable

    with pytest.raises(SiteUnavailableError, match='no route to host'):
        SponsrSession([SID]).token()


def test_token_without_expiry_gets_a_default_lifetime(sponsr):
    sponsr.routes[REFRESH_URL] = lambda request: (200, {'data': {'access_token': 'opaque-token'}}, [])

    token = SponsrSession([SID]).token()

    assert token.email is None
    assert timedelta(0) < token.expires_at - datetime.now(UTC) <= DEFAULT_LIFETIME


def test_new_cookies_from_the_site_are_reported(sponsr):
    sponsr.sign_in('good', exp=in_seconds(240), rotate_to='rotated')
    changes = []
    session = SponsrSession([SID], on_change=lambda changed: changes.append(changed.cookies))

    session.token()

    assert changes == [[SiteCookie(name='SESS', value='rotated')]]

    # The next request goes out with the new cookie, and nothing changes again.
    session.token()

    assert sponsr.calls()[-1].headers['Cookie'] == 'SESS=rotated'
    assert len(changes) == 1


def test_no_report_when_nothing_changed(sponsr):
    sponsr.sign_in('good', email='reader@example.com', exp=in_seconds(240))
    changes = []
    session = SponsrSession([SID], email='reader@example.com', on_change=changes.append)

    session.token()
    session.token()

    assert changes == []
