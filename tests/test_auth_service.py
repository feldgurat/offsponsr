from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from offsponsr.auth import (
    AccountService,
    AccountState,
    DifferentAccountError,
    InvalidCookieError,
    LoginInProgressError,
    NoLibraryError,
    NotSignedInError,
    SessionExpiredError,
    SiteUnavailableError,
)
from offsponsr.auth.cookies import SiteCookie
from offsponsr.auth.store import SavedSession, open_session_store
from offsponsr.library.models import Account

from .fakes import REFRESH_URL

SIGNED_OUT = AccountState(signed_in=False)
SIGNED_IN = AccountState(signed_in=True, email='reader@example.com')

ANALYTICS = SiteCookie(name='_ym_uid', value='1')
SID = SiteCookie(name='SESS', value='good')
USER_ID = SiteCookie(name='user_id', value='123456')


@pytest.fixture
def signed_in(account, library, login_window, sponsr):
    """The account service after a successful sign-in through the window."""
    sponsr.sign_in('good')
    login_window.pages = [[ANALYTICS, SID, USER_ID]]
    account.login_with_window()
    return account


def recorded_account(library):
    with library.session() as db:
        return db.scalars(select(Account)).all()


def test_no_account_without_a_library(account, login_window):
    assert account.state() == SIGNED_OUT
    assert account.logout() == SIGNED_OUT
    with pytest.raises(NoLibraryError):
        account.login_with_window()
    with pytest.raises(NoLibraryError):
        account.login_with_cookie_header('SESS=good')
    with pytest.raises(NoLibraryError):
        account.token()
    assert login_window.opened == 0


def test_signed_out_in_a_new_library(account, library):
    assert account.state() == SIGNED_OUT
    with pytest.raises(NotSignedInError):
        account.token()


def test_login_through_the_window(account, library, login_window, sponsr):
    sponsr.sign_in('good')
    # First look: the sign-in hasn't happened yet. Second look: it has.
    login_window.pages = [[ANALYTICS], [ANALYTICS, SID, USER_ID]]

    state = account.login_with_window()

    assert state == SIGNED_IN
    assert account.state() == SIGNED_IN
    # Only the session cookies are kept, not the analytics ones.
    assert open_session_store(library).load().cookies == [SID, USER_ID]
    assert account.token().email == 'reader@example.com'


def test_login_window_does_not_ask_the_site_without_a_session_cookie(account, library, login_window, sponsr):
    login_window.pages = [[ANALYTICS], [ANALYTICS, USER_ID]]

    assert account.login_with_window() == SIGNED_OUT
    assert sponsr.requests == []


def test_login_is_recorded_in_the_library(account, library, login_window, sponsr):
    sponsr.sign_in('good', user_id=123456)
    login_window.pages = [[SID]]
    before = datetime.now(UTC)

    account.login_with_window()

    [recorded] = recorded_account(library)
    assert recorded.user_id == 123456
    assert before <= recorded.last_login_at <= datetime.now(UTC)

    # Signing in again keeps it to one row.
    account.login_with_cookie_header('SESS=good')

    [recorded] = recorded_account(library)
    assert recorded.user_id == 123456


def test_library_keeps_to_its_first_account(signed_in, library, login_window, sponsr):
    sponsr.sign_in('other', user_id=777, email='someone.else@example.com')
    signed_in.logout()

    with pytest.raises(DifferentAccountError):
        signed_in.login_with_cookie_header('SESS=other')
    login_window.pages = [[SiteCookie(name='SESS', value='other')]]
    with pytest.raises(DifferentAccountError):
        signed_in.login_with_window()

    assert signed_in.state() == SIGNED_OUT
    assert open_session_store(library).load() is None
    [recorded] = recorded_account(library)
    assert recorded.user_id == 123456

    # The account it belongs to is still welcome.
    assert signed_in.login_with_cookie_header('SESS=good') == SIGNED_IN


def test_another_account_does_not_replace_the_current_session(signed_in, library, sponsr):
    sponsr.sign_in('other', user_id=777, email='someone.else@example.com')

    with pytest.raises(DifferentAccountError):
        signed_in.login_with_cookie_header('SESS=other')

    assert signed_in.state() == SIGNED_IN
    assert open_session_store(library).load().cookies == [SID, USER_ID]


def test_session_saved_with_analytics_cookies_is_trimmed(library, libraries, login_window, sponsr):
    store = open_session_store(library)
    store.save(SavedSession(cookies=[ANALYTICS, SID, USER_ID], email='reader@example.com'))

    assert AccountService(libraries, login_window).state() == SIGNED_IN
    assert store.load().cookies == [SID, USER_ID]
    assert sponsr.requests == []


def test_saved_session_without_the_session_cookie_is_dropped(library, libraries, login_window):
    store = open_session_store(library)
    store.save(SavedSession(cookies=[ANALYTICS, USER_ID], email='reader@example.com'))

    assert AccountService(libraries, login_window).state() == SIGNED_OUT
    assert store.load() is None


def test_closing_the_login_window_changes_nothing(account, library, login_window):
    login_window.pages = [[ANALYTICS]]

    assert account.login_with_window() == SIGNED_OUT
    assert open_session_store(library).load() is None


def test_site_trouble_during_login_is_not_a_sign_in(account, library, login_window, sponsr):
    sponsr.routes[REFRESH_URL] = lambda request: (500, {}, [])
    login_window.pages = [[SID]]

    assert account.login_with_window() == SIGNED_OUT


def test_one_login_window_at_a_time(account, library, login_window):
    seen = []

    def open_second_window():
        with pytest.raises(LoginInProgressError):
            account.login_with_window()
        seen.append('refused')

    login_window.on_open = open_second_window

    account.login_with_window()

    assert seen == ['refused']
    assert login_window.opened == 1


def test_login_with_a_cookie_header(account, library, sponsr):
    sponsr.sign_in('good')

    assert account.login_with_cookie_header('Cookie: _ym_uid=1; SESS=good') == SIGNED_IN
    assert account.state() == SIGNED_IN


@pytest.mark.parametrize('header', ['', 'not a cookie', 'SESS=stale', 'user_id=123456; _ym_uid=1'])
def test_login_with_a_useless_cookie_header(account, library, header):
    with pytest.raises(InvalidCookieError):
        account.login_with_cookie_header(header)

    assert account.state() == SIGNED_OUT


def test_cookie_login_while_the_site_is_down(account, library, sponsr):
    sponsr.routes[REFRESH_URL] = lambda request: (502, {}, [])

    with pytest.raises(SiteUnavailableError):
        account.login_with_cookie_header('SESS=good')


def test_sign_in_survives_a_restart_without_the_network(signed_in, libraries, login_window, sponsr):
    calls_before = len(sponsr.requests)

    after_restart = AccountService(libraries, login_window)

    assert after_restart.state() == SIGNED_IN
    assert len(sponsr.requests) == calls_before


def test_logout_forgets_the_session_locally(signed_in, library, libraries, login_window, sponsr):
    calls_before = len(sponsr.requests)

    assert signed_in.logout() == SIGNED_OUT

    assert open_session_store(library).load() is None
    assert AccountService(libraries, login_window).state() == SIGNED_OUT
    # Signing out is local: sponsr.ru is not told anything.
    assert len(sponsr.requests) == calls_before


def test_expired_session_signs_the_account_out(signed_in, library, libraries, login_window, sponsr):
    after_restart = AccountService(libraries, login_window)
    sponsr.sign_out('good')

    with pytest.raises(SessionExpiredError):
        after_restart.token()

    assert after_restart.state() == AccountState(signed_in=False, expired=True)
    assert open_session_store(library).load() is None
    with pytest.raises(NotSignedInError):
        after_restart.token()


def test_signing_in_again_clears_the_expired_mark(signed_in, libraries, login_window, sponsr):
    after_restart = AccountService(libraries, login_window)
    sponsr.sign_out('good')
    with pytest.raises(SessionExpiredError):
        after_restart.token()
    sponsr.sign_in('good')

    assert after_restart.login_with_window() == SIGNED_IN


def test_site_trouble_does_not_sign_the_account_out(signed_in, libraries, login_window, sponsr):
    after_restart = AccountService(libraries, login_window)
    sponsr.routes[REFRESH_URL] = lambda request: (503, {}, [])

    with pytest.raises(SiteUnavailableError):
        after_restart.token()

    assert after_restart.state() == SIGNED_IN


def test_rotated_cookies_are_saved(account, library, libraries, login_window, sponsr):
    sponsr.sign_in('good')
    login_window.pages = [[SID]]
    account.login_with_window()
    sponsr.sign_in('good', rotate_to='rotated')

    AccountService(libraries, login_window).token()

    assert open_session_store(library).load().cookies == [SiteCookie(name='SESS', value='rotated')]


def test_each_library_has_its_own_account(signed_in, libraries, tmp_path):
    first = libraries.current.root

    libraries.create(tmp_path / 'second')

    assert signed_in.state() == SIGNED_OUT

    libraries.open(first)

    assert signed_in.state() == SIGNED_IN
