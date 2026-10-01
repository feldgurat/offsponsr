from http.cookies import SimpleCookie

import pytest

from offsponsr.auth.cookies import SiteCookie, from_header, from_webview, is_site_domain, session_cookies
from offsponsr.auth.login_window import left_signin, page_of


def webview_cookie(name, value, domain, path='/'):
    cookie = SimpleCookie()
    cookie[name] = value
    cookie[name]['domain'] = domain
    cookie[name]['path'] = path
    return cookie


@pytest.mark.parametrize(
    ('domain', 'expected'),
    [
        ('sponsr.ru', True),
        ('.sponsr.ru', True),
        ('media.sponsr.ru', True),
        ('.SPONSR.ru', True),
        ('notsponsr.ru', False),
        ('sponsr.ru.evil.example', False),
        ('127.0.0.1', False),
        ('', False),
    ],
)
def test_site_domain(domain, expected):
    assert is_site_domain(domain) is expected


def test_from_webview_keeps_only_site_cookies():
    cookies = from_webview(
        [
            webview_cookie('SESS', 'abc', '.sponsr.ru'),
            webview_cookie('host_only', '1', 'sponsr.ru', path='/api'),
            webview_cookie('offsponsr_session', 'local', '127.0.0.1'),
            webview_cookie('oauth', 'x', '.mail.ru'),
        ]
    )

    assert cookies == [
        SiteCookie(name='SESS', value='abc', domain='.sponsr.ru', path='/'),
        SiteCookie(name='host_only', value='1', domain='sponsr.ru', path='/api'),
    ]


@pytest.mark.parametrize(
    'header',
    [
        'SESS=abc; theme=dark',
        'Cookie: SESS=abc; theme=dark',
        '  cookie:SESS=abc;theme=dark;  ',
    ],
)
def test_from_header(header):
    assert from_header(header) == [SiteCookie(name='SESS', value='abc'), SiteCookie(name='theme', value='dark')]


def test_only_the_session_cookies_are_kept():
    session = SiteCookie(name='SESS', value='abc')
    user = SiteCookie(name='user_id', value='123456')
    analytics = [SiteCookie(name='_ym_uid', value='1'), SiteCookie(name='tmr_lvid', value='2')]

    assert session_cookies([analytics[0], session, analytics[1], user]) == [session, user]
    assert session_cookies([session]) == [session]
    # Without the session cookie the rest is worth nothing.
    assert session_cookies([user, *analytics]) == []
    assert session_cookies([]) == []


def test_from_header_keeps_equals_signs_in_values():
    assert from_header('token=a=b==') == [SiteCookie(name='token', value='a=b==')]


@pytest.mark.parametrize('header', ['', '   ', 'no cookies here', 'Cookie:', '=novalue'])
def test_from_header_without_cookies(header):
    with pytest.raises(ValueError, match='No cookies'):
        from_header(header)


def test_cookie_json_round_trip():
    cookie = SiteCookie(name='SESS', value='abc', domain='sponsr.ru', path='/api')

    assert SiteCookie.from_json(cookie.to_json()) == cookie


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('https://sponsr.ru/', True),
        ('https://sponsr.ru/someproject/', True),
        ('https://sponsr.ru/auth/signin/', False),
        ('https://sponsr.ru/auth/signup/', False),
        # A social login leaves the site and comes back.
        ('https://oauth.mail.ru/login?client_id=1', False),
        ('about:blank', False),
        ('', False),
        (None, False),
    ],
)
def test_left_signin(url, expected):
    assert left_signin(url) is expected


@pytest.mark.parametrize(
    ('url', 'expected'),
    [
        ('https://sponsr.ru/auth/signin/?code=secret&state=1#frag', 'sponsr.ru/auth/signin/'),
        ('https://oauth.mail.ru/login?client_id=1', 'oauth.mail.ru/login'),
        ('about:blank', 'blank'),
        (None, ''),
    ],
)
def test_logged_page_has_no_query(url, expected):
    assert page_of(url) == expected
