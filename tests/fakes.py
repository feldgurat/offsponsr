"""Stand-ins for the outside world: sponsr.ru, the system keyring, the windows of the app."""

import base64
import io
import json
from email.message import Message
from urllib.parse import parse_qs, urlsplit

import requests
import urllib3
from keyring.backend import KeyringBackend
from keyring.errors import NoKeyringError, PasswordDeleteError
from requests.adapters import HTTPAdapter

from . import site_data

SITE = 'https://sponsr.ru'
API = f'{SITE}/api/v2'
REFRESH_URL = f'{API}/auth/refresh-token'

SUBSCRIBED_URL = f'{API}/content/projects/subscribed?withoutPagination=true'
LEVELS_URL = (
    f'{API}/content/levels?project_id={site_data.PROJECT_ID}&orderBy=level_price&orderByType=asc&withoutPagination=true'
)
PLAYLIST_URL = f'{API}/content/playlist?project_id={site_data.PROJECT_ID}&withoutPagination=true'
PROJECT_PAGE_URL = f'{SITE}/{site_data.PROJECT_URL}/'


def posts_url(page=1, project_id=site_data.PROJECT_ID):
    return (
        f'{API}/content/posts/?project_id={project_id}&withText=true&withFiles=true&tags=true'
        f'&limit=20&page={page}&orderBy=date&orderByType=desc'
    )


def more_posts_url(offset=0, project_id=site_data.PROJECT_ID):
    return f'{SITE}/project/{project_id}/more-posts/?offset={offset}'


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

    def close(self):
        pass


class FakeSponsr:
    """Answers the app's HTTP requests instead of the network.

    `routes` maps a URL to a function `(request) -> (status, body, set-cookie list)`, where the
    body is JSON-able data, or text or bytes to send as they are. A fourth item, if there is
    one, is a dict of extra response headers.
    Anything else fails like a dropped connection, so no test can reach the real site.
    """

    def __init__(self):
        self.routes = {}
        self.requests = []
        # Cookie values the site accepts as a signed-in session, and what it answers them.
        self.sessions = {}
        # Access tokens the API currently accepts.
        self.tokens = set()
        self._issued = 0
        # (URL prefix, route) pairs for addresses that vary, tried after `routes`.
        self.patterns = []
        self.routes[REFRESH_URL] = self._refresh
        self.serve_project()

    def serve_project(self):
        """Answer for the made-up project of site_data."""
        self.api(SUBSCRIBED_URL, site_data.subscribed)
        self.api(posts_url(), site_data.posts_page)
        self.api(LEVELS_URL, site_data.levels)
        self.api(PLAYLIST_URL, site_data.playlist)
        self.page(more_posts_url(), site_data.more_posts)
        self.page(PROJECT_PAGE_URL, site_data.project_page_html)

    def api(self, url, make_body):
        """An API route: answers only to a valid access token."""

        def route(request):
            token = request.headers.get('Authorization', '').removeprefix('Bearer ')
            if token not in self.tokens:
                return 401, {'message': 'Unauthorized', 'statusCode': 401}, []
            return 200, make_body(), []

        self.routes[url] = route

    def page(self, url, make_body):
        """A route of the site proper: goes by the cookies, as a browser would be served."""
        self.routes[url] = lambda request: (200, make_body(), [])

    def fail(self, url, *replies):
        """Answer `url` with each of `replies` in turn, then as before."""
        usual = self.routes.get(url)
        queue = list(replies)

        def route(request):
            if queue:
                reply = queue.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                return reply
            return usual(request)

        self.routes[url] = route

    def serve_feed(self, feed):
        """Answer both post lists of a project from a FakeFeed, page by page."""

        def posts(request):
            token = request.headers.get('Authorization', '').removeprefix('Bearer ')
            if token not in self.tokens:
                return 401, {'message': 'Unauthorized', 'statusCode': 401}, []
            page = int(parse_qs(urlsplit(request.url).query)['page'][0])
            return 200, feed.posts_page(page), []

        def more_posts(request):
            offset = int(parse_qs(urlsplit(request.url).query)['offset'][0])
            return 200, feed.more_posts(offset), []

        # The feed replaces the fixed first page that serve_project() set up.
        self.routes.pop(posts_url(project_id=feed.project_id), None)
        self.routes.pop(more_posts_url(project_id=feed.project_id), None)
        self.patterns.append((f'{API}/content/posts/?project_id={feed.project_id}&', posts))
        self.patterns.append((f'{SITE}/project/{feed.project_id}/more-posts/?', more_posts))

    def serve_file(self, url, content, *, needs_session=False, content_type='application/octet-stream'):
        """Serve bytes at `url` (any query), honouring Range requests as the real media hosts do.

        Returns a list that collects the Range header of every request, None for a whole-file one.
        """
        ranges = []

        def route(request):
            if needs_session:
                cookies = request.headers.get('Cookie', '')
                if not any(f'SESS={value}' in cookies for value in self.sessions):
                    return 403, '<html>403</html>', []
            asked = request.headers.get('Range')
            ranges.append(asked)
            total = len(content)
            if asked is None:
                return 200, content, [], {'Content-Type': content_type, 'Content-Length': str(total)}
            first, _, last = asked.removeprefix('bytes=').partition('-')
            first = int(first)
            if first >= total:
                return 416, b'', [], {'Content-Range': f'bytes */{total}'}
            last = min(int(last), total - 1) if last else total - 1
            body = content[first : last + 1]
            headers = {
                'Content-Type': content_type,
                'Content-Length': str(len(body)),
                'Content-Range': f'bytes {first}-{last}/{total}',
            }
            return 206, body, [], headers

        self.patterns.append((url, route))
        return ranges

    def revoke_tokens(self):
        """Stop accepting the access tokens handed out so far."""
        self.tokens.clear()

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
        self._issued += 1
        token = make_jwt(session['exp'], userId=session['user_id'], userEmail=session['email'], n=self._issued)
        self.tokens.add(token)
        body = {'message_code': 'success', 'message': '', 'data': {'access_token': token, 'email': session['email']}}
        return 200, body, set_cookies

    def send(self, adapter, request, **_kwargs):
        self.requests.append(request)
        route = self.routes.get(request.url)
        if route is None:
            route = next((found for prefix, found in reversed(self.patterns) if request.url.startswith(prefix)), None)
        if route is None:
            raise requests.ConnectionError(f'No fake route for {request.url}')

        status, body, set_cookies, *extra = route(request)
        if isinstance(body, bytes):
            content = body
        elif isinstance(body, str):
            content = body.encode()
        else:
            content = json.dumps(body).encode()
        headers = [
            ('Content-Type', 'text/html; charset=utf-8' if isinstance(body, str) else 'application/json'),
            *(('Set-Cookie', cookie) for cookie in set_cookies),
            *(extra[0].items() if extra else ()),
        ]
        raw = urllib3.HTTPResponse(
            body=io.BytesIO(content),
            headers=headers,
            status=status,
            preload_content=False,
            original_response=_OriginalResponse(headers),
        )
        return HTTPAdapter.build_response(adapter, request, raw)


class FakeFeed:
    """A project's posts on the fake site. Tests publish, edit and delete them between syncs."""

    def __init__(self, project_id=site_data.PROJECT_ID):
        self.project_id = project_id
        # Newest first, as the site lists them: (post as the API list gives it, its whole text).
        self.entries = []
        # Posts the legacy list leaves out, as if the lists had shifted between two requests.
        self.missing_from_legacy = set()

    def publish(self, post_id, text, *, long=False, date=None, **fields):
        """Put a readable post on top of the feed. A long post is listed with only its beginning."""
        date = date or f'2026-01-01T00:00:{len(self.entries) % 60:02d}.000Z'
        listed = site_data.post(
            post_id,
            fields.pop('title', f'Пост {post_id}'),
            date,
            html=text[: len(text) // 2] if long else text,
            truncated=long,
            **fields,
        )
        self.entries.insert(0, (listed, text))
        return listed

    def publish_closed(self, post_id, *, date='2026-01-01T00:00:00.000Z'):
        listed = site_data.closed_post(post_id, f'Закрытый пост {post_id}', date)
        self.entries.insert(0, (listed, ''))
        return listed

    def edit(self, post_id, text, *, long=False, updated_at='2026-02-02T00:00:00.000Z', **fields):
        index = self._index(post_id)
        listed, _ = self.entries[index]
        listed = {
            **listed,
            'text': {'post_id': post_id, 'text': text[: len(text) // 2] if long else text, 'ts': updated_at},
            'text_truncated': long,
            'updated_at': updated_at,
            **fields,
        }
        self.entries[index] = (listed, text)

    def close(self, post_id):
        """The account loses access to the post."""
        index = self._index(post_id)
        listed, _ = self.entries[index]
        self.entries[index] = (site_data.closed_post(post_id, listed['title'], listed['date']), '')

    def delete(self, post_id):
        del self.entries[self._index(post_id)]

    def _index(self, post_id):
        return next(index for index, (listed, _) in enumerate(self.entries) if listed['id'] == post_id)

    def posts_page(self, page):
        start = (page - 1) * 20
        chunk = [listed for listed, _ in self.entries[start : start + 20]]
        return {'total': len(self.entries), 'page': page, 'limit': 20, 'list': chunk}

    def more_posts(self, offset):
        rows = [
            {'post_id': listed['id'], 'post_text': site_data.marked(text), '_available': listed['available']}
            for listed, text in self.entries[offset : offset + 20]
            if listed['id'] not in self.missing_from_legacy
        ]
        return {'response': {'rows': rows, 'rows_count': len(self.entries), '_like': False}}


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


class FakeShell:
    """Stands in for the user's system: remembers what it was asked to open instead of opening it."""

    def __init__(self):
        self.calls = []
        # Set to make every request fail, as a system without a browser or a file manager would.
        self.error = None

    def _record(self, action, target):
        if self.error is not None:
            raise self.error
        self.calls.append((action, target))

    def open_url(self, url):
        self._record('open_url', url)

    def open_file(self, path):
        self._record('open_file', path)

    def reveal(self, path):
        self._record('reveal', path)
