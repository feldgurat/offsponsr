from datetime import UTC, datetime

import pytest
import requests

from offsponsr.auth import AccountState, NotSignedInError, SessionExpiredError, SiteUnavailableError
from offsponsr.sponsr import SponsrApiError, SponsrClient, SponsrFormatError
from offsponsr.sponsr.client import MAX_RETRY_AFTER, PAUSE, RETRIES, RETRY_DELAYS

from . import site_data
from .fakes import (
    LEVELS_URL,
    PLAYLIST_URL,
    PROJECT_PAGE_URL,
    REFRESH_URL,
    SUBSCRIBED_URL,
    more_posts_url,
    posts_url,
)


class FakeTime:
    """A clock that only moves when somebody sleeps."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_time():
    return FakeTime()


@pytest.fixture
def client(signed_in, fake_time):
    return SponsrClient(signed_in, sleep=fake_time.sleep, clock=fake_time.clock)


def by_id(posts):
    return {post.id: post for post in posts}


def test_subscriptions(client):
    [subscription] = client.subscriptions()

    assert subscription.id == site_data.PROJECT_ID
    assert subscription.url == site_data.PROJECT_URL
    assert subscription.title == 'Вымышленный альманах'
    assert subscription.owner_name == 'Автор Выдуманный'
    assert subscription.logo.x1 == '/images/projects/42/4242/logo.webp?5d41402abc4b2a76'
    assert subscription.logo.x2 == '/images/projects/42/4242/logo@2x.webp?5d41402abc4b2a76'
    assert (subscription.level.id, subscription.level.name, subscription.level.price) == (501, 'Читатель', 300)
    assert subscription.last_paid == datetime(2026, 9, 21, 10, 15, tzinfo=UTC)
    assert subscription.status == 'active'
    assert subscription.months == 1


def test_authors_email_is_not_kept(client):
    [subscription] = client.subscriptions()

    assert site_data.OWNER_EMAIL not in repr(subscription.model_dump())
    # The rest of the answer is kept as it came.
    assert subscription.raw['owner']['name'] == 'Автор Выдуманный'
    assert subscription.raw['next_level_id'] == site_data.LEVEL_BASIC


def test_posts_page(client):
    page = client.posts(site_data.PROJECT_ID)

    assert (page.total, page.page, page.limit) == (6, 1, 20)
    assert [post.id for post in page.posts] == [9006, 9005, 9004, 9003, 9002, 9001]


def test_short_post_comes_whole(client):
    post = by_id(client.posts(site_data.PROJECT_ID).posts)[site_data.POST_SHORT]

    assert post.available is True
    assert post.text_truncated is False
    assert post.has_full_text is True
    assert post.html == site_data.FULL_TEXTS[site_data.POST_SHORT]
    assert post.title == 'Короткая заметка'
    assert post.date == datetime(2026, 9, 30, 18, 15, tzinfo=UTC)
    assert post.updated_at == datetime(2026, 9, 30, 18, 15, tzinfo=UTC)
    assert post.level_id == site_data.LEVEL_BASIC
    assert post.content_type == 'image'
    assert post.image == '/images/projects/42/4242/7e/yn/u4//42ab12cd_original.webp'
    assert post.pinned is False
    assert post.views == 250
    assert post.duration_text == 120


def test_long_post_comes_truncated(client):
    post = by_id(client.posts(site_data.PROJECT_ID).posts)[site_data.POST_LONG]

    assert post.text_truncated is True
    assert post.has_full_text is False
    assert post.html == site_data.TRUNCATED_LONG
    assert post.updated_at == datetime(2026, 9, 29, 12, 30, tzinfo=UTC)
    assert [(tag.id, tag.name) for tag in post.tags] == [(site_data.TAG_ESSAYS, 'Эссе')]


def test_video_post(client):
    post = by_id(client.posts(site_data.PROJECT_ID).posts)[site_data.POST_VIDEO]

    assert post.content_type == 'video'
    assert post.duration_video == 3120
    assert site_data.KINESCOPE_EMBED in post.html
    [poster] = post.video_posters
    assert poster.type == 'kinescope'
    assert poster.iframe_src == f'/post/video/?video_id={site_data.VIDEO_ID}?poster_id={site_data.POSTER_ID}'
    assert poster.poster_url.startswith('https://kinescopecdn.net/')


def test_audio_post(client):
    post = by_id(client.posts(site_data.PROJECT_ID).posts)[site_data.POST_AUDIO]

    assert post.duration_podcast == 1835
    [file] = post.files
    assert file.id == 6001
    assert file.category == 'podcast'
    assert file.mime == 'audio/mpeg'
    assert file.name == 'ALMANAC_012.mp3'
    assert file.title == 'Альманах, выпуск 12'
    assert file.path.startswith('/uploads/files/p4242/9003/')
    # The site sends these two as text.
    assert file.size == 48211234
    assert file.duration == 1835


def test_closed_post_has_no_text(client):
    post = by_id(client.posts(site_data.PROJECT_ID).posts)[site_data.POST_CLOSED]

    assert post.available is False
    assert post.html is None
    assert post.text_truncated is None
    assert post.has_full_text is False
    assert post.title == 'Закрытый материал для старшего уровня'
    assert post.level_id == site_data.LEVEL_HIDDEN
    assert post.updated_at is None
    assert post.files == []


def test_free_pinned_post(client):
    post = by_id(client.posts(site_data.PROJECT_ID).posts)[site_data.POST_FREE]

    assert post.level_id is None
    assert post.pinned is True


def test_post_raw_leaves_the_text_out(client):
    post = by_id(client.posts(site_data.PROJECT_ID).posts)[site_data.POST_LONG]

    assert 'text' not in post.raw
    assert post.raw['cnt_likes'] == 3
    assert post.raw['tags'][0]['tag']['tag_name'] == 'Эссе'


def test_full_texts(client):
    texts = client.full_texts(site_data.PROJECT_ID)

    assert texts.total == 6
    assert [text.id for text in texts.posts] == [9006, 9005, 9004, 9003, 9002, 9001]
    whole = by_id(texts.posts)
    # Whole, and without the invisible marks the legacy list puts between the words.
    assert whole[site_data.POST_LONG].html == site_data.FULL_TEXTS[site_data.POST_LONG]
    assert whole[site_data.POST_SHORT].html == site_data.FULL_TEXTS[site_data.POST_SHORT]
    assert whole[site_data.POST_LONG].available is True
    assert whole[site_data.POST_CLOSED].available is False
    assert whole[site_data.POST_CLOSED].html == ''


def test_full_texts_page_matches_the_posts_page(client, sponsr):
    sponsr.page(more_posts_url(offset=40), site_data.more_posts)

    client.full_texts(site_data.PROJECT_ID, page=3)

    assert sponsr.requests[-1].url == more_posts_url(offset=40)


def test_levels(client):
    levels = by_id(client.levels(site_data.PROJECT_ID))

    basic = levels[site_data.LEVEL_BASIC]
    assert (basic.name, basic.price, basic.project_id) == ('Читатель', 300, site_data.PROJECT_ID)
    assert basic.description_html == '<p>Все тексты альманаха.</p>'
    assert basic.visible is True
    assert levels[site_data.LEVEL_HIDDEN].visible is False
    assert levels[site_data.LEVEL_HIDDEN].price == 1500
    # Deleted levels are still listed: old posts point at them.
    assert levels[site_data.LEVEL_DELETED].status == 'deleted'
    assert levels[site_data.LEVEL_DELETED].visible is False


def test_collections(client):
    collections = client.collections(site_data.PROJECT_ID)

    assert [(c.id, c.name, c.count, c.image) for c in collections] == [
        (site_data.TAG_ESSAYS, 'Эссе', 1, None),
        (site_data.TAG_TALKS, 'Лекции', 2, None),
    ]


def test_project_page(client):
    page = client.project(site_data.PROJECT_URL)

    project = page.project
    assert (project.id, project.url, project.title) == (
        site_data.PROJECT_ID,
        site_data.PROJECT_URL,
        'Вымышленный альманах',
    )
    assert project.intent == 'на выдуманные тексты'
    assert project.description_html == '<p>Альманах, которого <b>не существует</b>.</p>'
    assert project.cover == '/images/projects/42/4242/bg.webp?5d41402abc4b2a76'
    assert project.logo.x2 == '/images/projects/42/4242/logo@2x.webp?5d41402abc4b2a76'
    assert project.raw['project_stats']['project_active_posts_amount'] == 6
    assert [level.id for level in page.levels] == [site_data.LEVEL_BASIC, site_data.LEVEL_HIDDEN]
    assert (page.user.id, page.user.nickname) == (site_data.USER_ID, 'reader')


def test_project_page_seen_signed_out(client, sponsr):
    props = site_data.project_page_props()
    del props['user']
    sponsr.page(PROJECT_PAGE_URL, lambda: site_data.project_page_html(props))

    assert client.project(site_data.PROJECT_URL).user is None


@pytest.mark.parametrize('address', ['', 'two/parts', '../etc', 'with space', 'https://sponsr.ru/x/'])
def test_project_address_is_checked(client, sponsr, address):
    before = len(sponsr.requests)

    with pytest.raises(ValueError, match='Not a project address'):
        client.project(address)

    assert len(sponsr.requests) == before


def test_api_requests_carry_the_token_and_the_cookies(client, sponsr):
    client.subscriptions()

    request = sponsr.requests[-1]
    assert request.url == SUBSCRIBED_URL
    assert request.headers['Authorization'].removeprefix('Bearer ') in sponsr.tokens
    assert request.headers['Cookie'] == 'SESS=good; user_id=123456'
    assert request.headers['Accept'] == 'application/json'


def test_site_requests_go_by_cookies_alone(client, sponsr):
    client.full_texts(site_data.PROJECT_ID)
    client.project(site_data.PROJECT_URL)

    for request in sponsr.requests[-2:]:
        assert 'Authorization' not in request.headers
        assert request.headers['Cookie'] == 'SESS=good; user_id=123456'


def test_one_token_serves_many_requests(client, sponsr):
    client.subscriptions()
    before = len(sponsr.calls(REFRESH_URL))

    client.subscriptions()
    client.posts(site_data.PROJECT_ID)
    client.levels(site_data.PROJECT_ID)

    assert len(sponsr.calls(REFRESH_URL)) == before


def test_requests_keep_a_pause_between_them(client, fake_time):
    client.subscriptions()

    assert fake_time.sleeps == []

    client.posts(site_data.PROJECT_ID)
    client.levels(site_data.PROJECT_ID)

    assert fake_time.sleeps == [PAUSE, PAUSE]


def test_no_pause_once_enough_time_has_passed(client, fake_time):
    client.subscriptions()
    fake_time.now += 5

    client.posts(site_data.PROJECT_ID)

    assert fake_time.sleeps == []


def test_busy_site_is_tried_again(client, sponsr, fake_time):
    sponsr.fail(SUBSCRIBED_URL, (503, {}, []), (502, {}, []))

    assert len(client.subscriptions()) == 1
    assert len(sponsr.calls(SUBSCRIBED_URL)) == 3
    assert fake_time.sleeps == [RETRY_DELAYS[0], RETRY_DELAYS[1]]


def test_dropped_connection_is_tried_again(client, sponsr, fake_time):
    sponsr.fail(SUBSCRIBED_URL, requests.ConnectionError('reset by peer'))

    assert len(client.subscriptions()) == 1
    assert fake_time.sleeps == [RETRY_DELAYS[0]]


def test_site_that_stays_down(client, sponsr, fake_time, signed_in):
    sponsr.fail(SUBSCRIBED_URL, *[(500, {}, [])] * (RETRIES + 1))

    with pytest.raises(SiteUnavailableError, match='HTTP 500'):
        client.subscriptions()

    assert len(sponsr.calls(SUBSCRIBED_URL)) == RETRIES + 1
    assert fake_time.sleeps == list(RETRY_DELAYS[:RETRIES])
    # Trouble on the site's side doesn't cost the sign-in.
    assert signed_in.state().signed_in is True


def test_rate_limit_waits_as_long_as_asked(client, sponsr, fake_time):
    sponsr.fail(SUBSCRIBED_URL, (429, {}, [], {'Retry-After': '7'}), (429, {}, [], {'Retry-After': '100000'}))

    client.subscriptions()

    assert fake_time.sleeps == [7.0, MAX_RETRY_AFTER]


@pytest.mark.parametrize('status', [403, 404])
def test_refusals_are_not_retried(client, sponsr, fake_time, status):
    sponsr.fail(posts_url(), (status, {'message': 'no'}, []))

    with pytest.raises(SponsrApiError) as raised:
        client.posts(site_data.PROJECT_ID)

    assert raised.value.status == status
    assert '/api/v2/content/posts/' in str(raised.value)
    assert len(sponsr.calls(posts_url())) == 1
    assert fake_time.sleeps == []


def test_withdrawn_token_is_replaced_once(client, sponsr):
    client.subscriptions()
    refreshes = len(sponsr.calls(REFRESH_URL))
    sponsr.revoke_tokens()

    assert len(client.subscriptions()) == 1
    assert len(sponsr.calls(REFRESH_URL)) == refreshes + 1


def test_token_the_api_keeps_rejecting(client, sponsr):
    sponsr.routes[SUBSCRIBED_URL] = lambda request: (401, {}, [])

    with pytest.raises(SponsrApiError) as raised:
        client.subscriptions()

    assert raised.value.status == 401
    assert len(sponsr.calls(SUBSCRIBED_URL)) == 2


def test_expired_session_signs_out(client, sponsr, signed_in):
    client.subscriptions()
    sponsr.revoke_tokens()
    sponsr.sign_out('good')

    with pytest.raises(SessionExpiredError):
        client.subscriptions()

    assert signed_in.state() == AccountState(signed_in=False, expired=True)


def test_client_needs_a_signed_in_account(account, library, sponsr, fake_time):
    client = SponsrClient(account, sleep=fake_time.sleep, clock=fake_time.clock)

    with pytest.raises(NotSignedInError):
        client.subscriptions()
    with pytest.raises(NotSignedInError):
        client.full_texts(site_data.PROJECT_ID)

    assert sponsr.requests == []


@pytest.mark.parametrize(
    ('url', 'call', 'body', 'problem'),
    [
        (SUBSCRIBED_URL, lambda c: c.subscriptions(), {'data': []}, 'no "list"'),
        (SUBSCRIBED_URL, lambda c: c.subscriptions(), '<html>maintenance</html>', 'not JSON'),
        (LEVELS_URL, lambda c: c.levels(site_data.PROJECT_ID), {'list': [{'id': 1}]}, 'project_id: missing'),
        (PLAYLIST_URL, lambda c: c.collections(site_data.PROJECT_ID), [], 'no "list"'),
        (posts_url(), lambda c: c.posts(site_data.PROJECT_ID), {'list': []}, 'total: missing'),
        (more_posts_url(), lambda c: c.full_texts(site_data.PROJECT_ID), {'rows': []}, 'no "response"'),
        (PROJECT_PAGE_URL, lambda c: c.project(site_data.PROJECT_URL), '<html>no data</html>', 'no page data'),
        (
            PROJECT_PAGE_URL,
            lambda c: c.project(site_data.PROJECT_URL),
            '<script id="__NEXT_DATA__" type="application/json">{"props": {}}</script>',
            'unreadable page data',
        ),
    ],
)
def test_answers_the_client_does_not_understand(client, sponsr, url, call, body, problem):
    sponsr.routes[url] = lambda request: (200, body, [])

    with pytest.raises(SponsrFormatError, match=problem):
        call(client)


def test_format_errors_do_not_quote_the_content(client, sponsr):
    page = site_data.posts_page()
    page['list'][0]['date'] = 'Секретный текст вместо даты'
    sponsr.routes[posts_url()] = lambda request: (200, page, [])

    with pytest.raises(SponsrFormatError) as raised:
        client.posts(site_data.PROJECT_ID)

    assert 'list.0.date' in str(raised.value)
    assert 'Секретный' not in str(raised.value)
    assert raised.value.__cause__ is None
