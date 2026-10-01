import secrets
import threading

SESSION_COOKIE = 'offsponsr_session'


def _same(left: str, right: str) -> bool:
    return secrets.compare_digest(left.encode(), right.encode())


class SessionGate:
    """Trades the one-time launch token for the session id the UI then sends as a cookie.

    The app puts the launch token into the window URL. Anything else on the machine that
    finds the port can't use the API: the token works once and the window spends it on load.
    """

    def __init__(self, launch_token: str) -> None:
        self._launch_token: str | None = launch_token
        self._session_id: str | None = None
        self._lock = threading.Lock()

    def exchange(self, token: str) -> str | None:
        """Return a new session id, or None if the token is wrong or already spent."""
        with self._lock:
            if self._launch_token is None or not _same(token, self._launch_token):
                return None
            self._launch_token = None
            self._session_id = secrets.token_urlsafe(32)
            return self._session_id

    def is_valid(self, session_id: str | None) -> bool:
        with self._lock:
            return bool(session_id and self._session_id and _same(session_id, self._session_id))
