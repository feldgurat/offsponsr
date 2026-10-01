class AuthError(Exception):
    """Signing in or using the sponsr.ru session failed. `code` is what the UI keys its message on."""

    code = 'auth_error'


class NoLibraryError(AuthError):
    """The account belongs to a library, and none is open."""

    code = 'no_library'


class NotSignedInError(AuthError):
    code = 'not_signed_in'


class SessionExpiredError(AuthError):
    """sponsr.ru no longer accepts the stored cookies; the user has to sign in again."""

    code = 'session_expired'


class SiteUnavailableError(AuthError):
    """sponsr.ru couldn't be reached or answered with something unexpected."""

    code = 'site_unavailable'


class InvalidCookieError(AuthError):
    """The pasted Cookie string has no cookies in it or sponsr.ru doesn't accept them."""

    code = 'invalid_cookie'


class DifferentAccountError(AuthError):
    """The library is tied to one sponsr.ru account, and the sign-in was with another."""

    code = 'different_account'


class LoginInProgressError(AuthError):
    """The login window is already open."""

    code = 'login_in_progress'
