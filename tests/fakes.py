"""Stand-ins for the outside world: sponsr.ru, the system keyring, the windows of the app."""

import base64
import io
import json
from email.message import Message

import requests
import urllib3
from keyring.backend import KeyringBackend
from keyring.errors import NoKeyringError, PasswordDeleteError
from requests.adapters import HTTPAdapter

REFRESH_URL = 'https://sponsr.ru/api/v2/auth/refresh-token'


def make_jwt(exp, **claims):
    """A token shaped like sponsr.ru's: only the payload matters to the app."""

    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')

    return f'{part({"alg": "HS256"})}.{part({"exp": exp, "iat": exp - 3600, **claims})}.signature'


class _OriginalResponse:
    """The bit of http.client's response that requests reads Set-Cookie headers from."""

    def __init__(self, headers):
        self.msg = Message()
        for name, value in headers:
            self.msg[name] = value

    def isclosed(self):
        return True


class FakeSponsr:
    """Answers the app's HTTP requests instead of the network.

    `routes` maps a URL to a function `(request) -> (status, json body, set-cookie list)`.
    Anything else fails like a dropped connection, so no test can reach the real site.
    """

    def __init__(self):
        self.routes = {}
        self.requests = []
        # Cookie values the site accepts as a signed-in session, and what it answers them.
        self.sessions = {}
        self.routes[REFRESH_URL] = self._refresh

    def sign_in(self, cookie_value, *, email='reader@example.com', exp=4102444800, rotate_to=None, user_id=123456):
        """Make `SESS=<cookie_value>` a valid session. `rotate_to` makes the site replace the cookie."""
        self.sessions[cookie_value] = {'email': email, 'exp': exp, 'rotate_to': rotate_to, 'user_id': user_id}

    def sign_out(self, cookie_value):
        self.sessions.pop(cookie_value, None)

    def calls(self, url=REFRESH_URL):
        return [request for request in self.requests if request.url == url]

    def _refresh(self, request):
        cookies = dict(
            pair.strip().split('=', 1) for pair in request.headers.get('Cookie', '').split(';') if '=' in pair
        )
        session = self.sessions.get(cookies.get('SESS'))
        if session is None:
            return 403, {'message': 'Forbidden resource', 'error': 'Forbidden', 'statusCode': 403}, []

        set_cookies = []
        if session['rotate_to']:
            new_value = session['rotate_to']
            self.sessions[new_value] = {**session, 'rotate_to': None}
            del self.sessions[cookies['SESS']]
            set_cookies.append(f'SESS={new_value}; Domain=.sponsr.ru; Path=/; HttpOnly')
            # The site hands out analytics cookies too; the app must not pick those up.
            set_cookies.append('_ym_uid=42; Domain=.sponsr.ru; Path=/')
        token = make_jwt(session['exp'], userId=session['user_id'], userEmail=session['email'])
        body = {'message_code': 'success', 'message': '', 'data': {'access_token': token, 'email': session['email']}}
        return 200, body, set_cookies

    def send(self, adapter, request, **_kwargs):
        self.requests.append(request)
        route = self.routes.get(request.url)
        if route is None:
            raise requests.ConnectionError(f'No fake route for {request.url}')

        status, body, set_cookies = route(request)
        content = body if isinstance(body, bytes) else json.dumps(body).encode()
        headers = [('Content-Type', 'application/json'), *(('Set-Cookie', cookie) for cookie in set_cookies)]
        raw = urllib3.HTTPResponse(
            body=io.BytesIO(content),
            headers=headers,
            status=status,
            preload_content=False,
            original_response=_OriginalResponse(headers),
        )
        return HTTPAdapter.build_response(adapter, request, raw)


class MemoryKeyring(KeyringBackend):
    """A keyring that lives in a dict, with Windows' limit on the size of one entry."""

    priority = 1
    max_length = 1280

    def __init__(self):
        super().__init__()
        self.entries = {}

    def get_password(self, service, username):
        return self.entries.get((service, username))

    def set_password(self, service, username, password):
        assert len(password) <= self.max_length, 'The entry is too long for Windows Credential Manager'
        self.entries[service, username] = password

    def delete_password(self, service, username):
        if (service, username) not in self.entries:
            raise PasswordDeleteError(username)
        del self.entries[service, username]


class BrokenKeyring(KeyringBackend):
    """What a system without a secret storage looks like."""

    priority = 1

    def get_password(self, service, username):
        raise NoKeyringError

    def set_password(self, service, username, password):
        raise NoKeyringError

    def delete_password(self, service, username):
        raise NoKeyringError


class FakeFolderPicker:
    """Stands in for the system folder dialog: returns whatever the test put in `choice`."""

    def __init__(self):
        self.choice = None

    def __call__(self):
        return self.choice


class FakeLoginWindow:
    """Stands in for the sponsr.ru login window.

    `pages` is what the window would see as the user goes along: one list of cookies per look.
    The window closes with the first cookies the app accepts, or unsigned once the pages run out.
    """

    def __init__(self):
        self.pages = []
        self.opened = 0
        self.on_open = None

    def __call__(self, accepts):
        self.opened += 1
        if self.on_open:
            self.on_open()
        for cookies in self.pages:
            if accepts(cookies):
                return cookies
        return None
