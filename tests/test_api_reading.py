"""The API the UI reads the library through: feeds, posts, files, project settings."""

import time

import pytest
from sqlalchemy import select

from offsponsr.library.models import Media, MediaKind, MediaState, Post, PostStatus
from offsponsr.shell import ShellError

from . import site_data
from .test_sync_service import wait_until_idle

PID = site_data.PROJECT_ID
PICTURE = b'\x89PNG picture bytes'


def wait_for_downloads(downloads, timeout=10):
    deadline = time.monotonic() + timeout
    while downloads.is_busy():
        assert time.monotonic() < deadline, 'The downloads did not finish in time'
        time.sleep(0.01)


@pytest.fixture
def reader(session_client, signed_in, sync_service):
    """A session with the made-up project synced into the library; no media downloaded."""
    session_client.post('/api/projects', json={'subscription_ids': [PID]})
    wait_until_idle(sync_service)
    return session_client


@pytest.fixture
def with_media(reader, downloads, sponsr):
    """The same, with the project's pictures and audio downloaded."""
    sponsr.serve_file('https://media.sponsr.ru/', PICTURE, needs_session=False)
    reader.post(f'/api/projects/{PID}/download')
    wait_for_downloads(downloads)
    return reader


def media_of(library, kind):
    with library.session() as db:
        return db.scalars(select(Media).where(Media.kind == kind)).one()


def test_reading_requires_session(client):
    for path in (f'/api/projects/{PID}', f'/api/projects/{PID}/posts', '/api/posts/1', '/api/settings', '/media/1'):
        assert client.get(path).status_code == 401
    assert client.get(f'/media/posts/{site_data.POST_SHORT}/cover').status_code == 401
    assert client.get(f'/media/projects/{PID}/logo').status_code == 401
    assert client.patch(f'/api/projects/{PID}', json={}).status_code == 401
    assert client.post('/api/open-link', json={'url': 'https://example.com'}).status_code == 401
    assert client.post('/api/media/1/open').status_code == 401
    assert client.post('/api/media/1/reveal').status_code == 401


def test_reading_needs_a_library(session_client):
    for path in (f'/api/projects/{PID}', f'/api/projects/{PID}/posts', '/api/posts/1', '/media/1'):
        response = session_client.get(path)
        assert (response.status_code, response.json()) == (409, {'code': 'no_library'})


def test_one_project(reader):
    project = reader.get(f'/api/projects/{PID}').json()

    assert project['title'] == 'Вымышленный альманах'
    assert (project['posts'], project['posts_closed']) == (6, 1)
    assert reader.get('/api/projects/1').status_code == 404


def test_feed_lists_posts_newest_first(reader):
    page = reader.get(f'/api/projects/{PID}/posts').json()

    assert (page['total'], page['page'], page['per_page']) == (6, 1, 20)
    assert [post['id'] for post in page['posts']] == [
        site_data.POST_SHORT,
        site_data.POST_LONG,
        site_data.POST_VIDEO,
        site_data.POST_AUDIO,
        site_data.POST_CLOSED,
        site_data.POST_FREE,
    ]
    short = page['posts'][0]
    assert short == {
        'id': site_data.POST_SHORT,
        'project_id': PID,
        'title': 'Короткая заметка',
        'date': '2026-09-30T18:15:00Z',
        'excerpt': 'Короткая заметка целиком помещается в список.',
        # Not downloaded yet: the picture's address on the site.
        'cover': 'https://media.sponsr.ru/images/projects/42/4242/7e/yn/u4//42ab12cd_original.webp',
        'closed': False,
        'status': 'active',
        'text_is_full': True,
        'level': {'id': site_data.LEVEL_BASIC, 'name': 'Читатель', 'price': 300},
        'duration_text': 120,
        'duration_audio': 0,
        'duration_video': 0,
        'has_audio': False,
        'has_video': False,
        'pinned': False,
        'tags': [],
        # The feeds other than the stream don't carry the texts.
        'html': None,
        'media': [],
    }


def test_feed_cards_tell_what_a_post_has(reader):
    posts = {post['id']: post for post in reader.get(f'/api/projects/{PID}/posts').json()['posts']}

    video, audio, closed, free = (
        posts[site_data.POST_VIDEO],
        posts[site_data.POST_AUDIO],
        posts[site_data.POST_CLOSED],
        posts[site_data.POST_FREE],
    )
    assert (video['has_video'], video['has_audio'], video['duration_video']) == (True, False, 3120)
    assert (audio['has_audio'], audio['has_video']) == (True, False)
    assert video['tags'] == [{'id': site_data.TAG_TALKS, 'name': 'Лекции'}]
    assert (closed['closed'], closed['excerpt'], closed['text_is_full']) == (True, '', False)
    assert closed['level'] == {'id': site_data.LEVEL_HIDDEN, 'name': 'Меценат', 'price': 1500}
    # A post outside the levels, and pinned by the author.
    assert (free['level'], free['pinned'], free['closed']) == (None, True, False)


def test_feed_with_texts_labels_the_media(reader, library):
    page = reader.get(f'/api/projects/{PID}/posts', params={'with_text': True}).json()
    posts = {post['id']: post for post in page['posts']}

    picture = media_of(library, MediaKind.IMAGE)
    short = posts[site_data.POST_SHORT]
    assert f'<img data-media="{picture.id}" src="https://media.sponsr.ru/' in short['html']
    assert [(item['id'], item['kind'], item['state'], item['url']) for item in short['media']] == [
        (picture.id, 'image', 'pending', None)
    ]
    video = media_of(library, MediaKind.VIDEO)
    assert f'<iframe data-media="{video.id}" src="{site_data.KINESCOPE_EMBED}"' in posts[site_data.POST_VIDEO]['html']
    # A closed post has no text to show.
    assert (posts[site_data.POST_CLOSED]['html'], posts[site_data.POST_CLOSED]['media']) == (None, [])


def test_feed_pages(reader, library):
    with library.session() as db:
        template = db.get(Post, site_data.POST_FREE)
        for number in range(1, 41):
            db.add(
                Post(
                    id=number,
                    project_id=PID,
                    date=template.date.replace(year=2020, day=1, hour=number % 24, minute=number),
                    title=f'Старый пост {number}',
                    available=True,
                    html='<p>Текст.</p>',
                    html_is_full=True,
                )
            )
        db.commit()

    first = reader.get(f'/api/projects/{PID}/posts').json()
    third = reader.get(f'/api/projects/{PID}/posts', params={'page': 3}).json()
    beyond = reader.get(f'/api/projects/{PID}/posts', params={'page': 9}).json()

    assert (first['total'], len(first['posts'])) == (46, 20)
    assert (third['page'], len(third['posts'])) == (3, 6)
    assert beyond['posts'] == []
    assert reader.get(f'/api/projects/{PID}/posts', params={'page': 0}).status_code == 422


def test_feed_order_and_period(reader):
    oldest_first = reader.get(f'/api/projects/{PID}/posts', params={'order': 'asc'}).json()
    assert [post['id'] for post in oldest_first['posts']][:2] == [site_data.POST_FREE, site_data.POST_CLOSED]

    period = {'date_from': '2026-09-27T00:00:00+03:00', 'date_to': '2026-09-28T23:59:59+03:00'}
    within = reader.get(f'/api/projects/{PID}/posts', params=period).json()
    assert [post['id'] for post in within['posts']] == [site_data.POST_VIDEO, site_data.POST_AUDIO]
    assert within['total'] == 2

    # A time without a zone could mean any moment, so it is refused.
    naive = reader.get(f'/api/projects/{PID}/posts', params={'date_from': '2026-09-27T00:00:00'})
    assert naive.status_code == 422


def test_feed_filters(reader, library):
    def ids(**params):
        return [post['id'] for post in reader.get(f'/api/projects/{PID}/posts', params=params).json()['posts']]

    assert ids(content='audio') == [site_data.POST_AUDIO]
    assert ids(content='video') == [site_data.POST_VIDEO]
    assert site_data.POST_CLOSED not in ids(hide_closed=True)
    assert len(ids(hide_closed=True)) == 5

    with library.session() as db:
        db.get(Post, site_data.POST_LONG).status = PostStatus.DELETED_ON_SITE
        db.commit()
    assert site_data.POST_LONG in ids()
    assert site_data.POST_LONG not in ids(hide_deleted=True)
    assert reader.get(f'/api/projects/{PID}/posts', params={'content': 'smell'}).status_code == 422


def test_a_post_that_lost_access_but_kept_its_text_is_not_closed(reader, library):
    with library.session() as db:
        post = db.get(Post, site_data.POST_SHORT)
        post.available, post.status = False, PostStatus.UNAVAILABLE
        db.commit()

    posts = reader.get(f'/api/projects/{PID}/posts', params={'hide_closed': True}).json()['posts']

    kept = next(post for post in posts if post['id'] == site_data.POST_SHORT)
    assert (kept['closed'], kept['status']) == (False, 'unavailable')


def test_feed_of_an_unknown_project(reader):
    assert reader.get('/api/projects/1/posts').status_code == 404


def test_post(reader, library):
    post = reader.get(f'/api/posts/{site_data.POST_VIDEO}').json()

    video = media_of(library, MediaKind.VIDEO)
    assert post['title'] == 'Лекция'
    assert post['project'] == {'id': PID, 'url': site_data.PROJECT_URL, 'title': 'Вымышленный альманах'}
    assert f'data-media="{video.id}"' in post['html']
    assert post['media'] == [
        {
            'id': video.id,
            'kind': 'video',
            'source_id': site_data.VIDEO_ID,
            'source_url': site_data.KINESCOPE_EMBED,
            'title': None,
            'size': None,
            'duration': None,
            'state': 'pending',
            'error': None,
            'url': None,
            'file_name': None,
            'can_open': False,
        }
    ]
    assert post['newer'] == {'id': site_data.POST_LONG, 'title': 'Длинное эссе'}
    assert post['older'] == {'id': site_data.POST_AUDIO, 'title': 'Подкаст'}


def test_post_at_the_ends_of_the_feed(reader):
    newest = reader.get(f'/api/posts/{site_data.POST_SHORT}').json()
    oldest = reader.get(f'/api/posts/{site_data.POST_FREE}').json()

    assert (newest['newer'], newest['older']['id']) == (None, site_data.POST_LONG)
    assert (oldest['older'], oldest['newer']['id']) == (None, site_data.POST_CLOSED)
    assert reader.get('/api/posts/1').status_code == 404


def test_closed_post_has_no_text(reader):
    post = reader.get(f'/api/posts/{site_data.POST_CLOSED}').json()

    assert (post['closed'], post['html'], post['media']) == (True, None, [])
    assert post['level']['name'] == 'Меценат'


def test_downloaded_media_is_served(with_media, library):
    picture = media_of(library, MediaKind.IMAGE)
    post = with_media.get(f'/api/posts/{site_data.POST_SHORT}').json()

    assert post['media'][0]['url'] == f'/media/{picture.id}'
    assert (post['media'][0]['file_name'], post['media'][0]['can_open']) == ('31.webp', True)
    assert post['cover'] == f'/media/posts/{site_data.POST_SHORT}/cover'

    response = with_media.get(f'/media/{picture.id}')
    assert response.content == PICTURE
    assert response.headers['content-type'] == 'image/webp'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert 'sandbox' in response.headers['content-security-policy']
    assert with_media.get(post['cover']).content == PICTURE

    project = with_media.get(f'/api/projects/{PID}').json()
    assert (project['logo'], project['cover']) == (f'/media/projects/{PID}/logo', f'/media/projects/{PID}/cover')
    assert with_media.get(project['logo']).content == PICTURE
    assert with_media.get(project['cover']).content == PICTURE


def test_media_is_served_in_ranges(with_media, library):
    audio = media_of(library, MediaKind.AUDIO)

    response = with_media.get(f'/media/{audio.id}', headers={'Range': 'bytes=1-4'})

    assert response.status_code == 206
    assert response.content == PICTURE[1:5]
    assert response.headers['content-range'] == f'bytes 1-4/{len(PICTURE)}'
    assert response.headers['content-type'] == 'audio/mpeg'


def test_what_is_not_in_the_library_is_not_served(reader, with_media, library):
    video = media_of(library, MediaKind.VIDEO)

    assert with_media.get(f'/media/{video.id}').status_code == 404
    assert with_media.get('/media/999999').status_code == 404
    assert with_media.get('/media/posts/999999/cover').status_code == 404
    assert with_media.get(f'/media/posts/{site_data.POST_FREE}/cover').status_code == 404
    assert with_media.get('/media/projects/1/logo').status_code == 404
    assert with_media.get(f'/media/projects/{PID}/banner').status_code == 404


def test_a_file_missing_from_disk_is_not_served(with_media, library):
    picture = media_of(library, MediaKind.IMAGE)
    library.file(picture.local_path).unlink()

    assert with_media.get(f'/media/{picture.id}').status_code == 404


def test_a_file_posing_as_media_goes_out_as_plain_bytes(with_media, library):
    """An HTML page saved as a post's picture must never reach the window as a page."""
    picture = media_of(library, MediaKind.IMAGE)
    disguised = library.file(picture.local_path).with_suffix('.html')
    disguised.write_bytes(b'<script>alert(1)</script>')
    with library.session() as db:
        db.get(Media, picture.id).local_path = str(picture.local_path).replace('.webp', '.html')
        db.commit()

    response = with_media.get(f'/media/{picture.id}')

    assert response.headers['content-type'] == 'application/octet-stream'


def test_attachments_are_not_served_to_the_window(with_media, library):
    audio = media_of(library, MediaKind.AUDIO)
    with library.session() as db:
        db.get(Media, audio.id).kind = MediaKind.ATTACH
        db.commit()

    assert with_media.get(f'/media/{audio.id}').status_code == 404
    assert with_media.get(f'/api/posts/{site_data.POST_AUDIO}').json()['media'][0]['url'] is None


def test_reveal_and_open_a_downloaded_file(with_media, library, shell):
    audio = media_of(library, MediaKind.AUDIO)
    path = library.file(audio.local_path)

    assert with_media.post(f'/api/media/{audio.id}/reveal').status_code == 204
    assert with_media.post(f'/api/media/{audio.id}/open').status_code == 204

    assert shell.calls == [('reveal', path), ('open_file', path)]


def test_only_documents_and_media_are_opened(with_media, library, shell):
    audio = media_of(library, MediaKind.AUDIO)
    program = library.file(audio.local_path).with_suffix('.exe')
    library.file(audio.local_path).rename(program)
    with library.session() as db:
        db.get(Media, audio.id).local_path = str(audio.local_path).replace('.mp3', '.exe')
        db.commit()

    assert with_media.get(f'/api/posts/{site_data.POST_AUDIO}').json()['media'][0]['can_open'] is False
    assert with_media.post(f'/api/media/{audio.id}/open').status_code == 422
    # Showing it in its folder runs nothing, so that is allowed.
    assert with_media.post(f'/api/media/{audio.id}/reveal').status_code == 204
    assert shell.calls == [('reveal', program)]


def test_files_not_downloaded_cannot_be_opened(reader, library, shell):
    video = media_of(library, MediaKind.VIDEO)

    assert reader.post(f'/api/media/{video.id}/open').status_code == 404
    assert reader.post(f'/api/media/{video.id}/reveal').status_code == 404
    assert reader.post('/api/media/999999/reveal').status_code == 404
    assert shell.calls == []


def test_links_open_in_the_browser(reader, shell):
    assert reader.post('/api/open-link', json={'url': 'https://example.com/page?x=1'}).status_code == 204
    assert shell.calls == [('open_url', 'https://example.com/page?x=1')]


@pytest.mark.parametrize(
    'url', ['file:///C:/Windows/system32/calc.exe', 'javascript:alert(1)', 'data:text/html,x', 'x']
)
def test_only_web_links_open(reader, shell, url):
    assert reader.post('/api/open-link', json={'url': url}).status_code == 422
    assert shell.calls == []


def test_the_system_refusing_is_reported(reader, shell):
    shell.error = ShellError('no browser')

    assert reader.post('/api/open-link', json={'url': 'https://example.com'}).status_code == 500


def test_change_project_settings(reader):
    response = reader.patch(f'/api/projects/{PID}', json={'sync_enabled': False, 'video_quality': 720})

    body = response.json()
    assert (body['project']['sync_enabled'], body['project']['video_quality']) == (False, 720)
    # Nothing was switched to downloading right away, so there is nothing to offer.
    assert body['to_download'] == {'files': 0, 'bytes': 0, 'files_without_size': 0}
    # What wasn't mentioned stays.
    assert body['project']['media_mode_audio'] == 'auto'

    best = reader.patch(f'/api/projects/{PID}', json={'video_quality': None}).json()
    assert best['project']['video_quality'] is None
    assert reader.get(f'/api/projects/{PID}').json()['sync_enabled'] is False


def test_switching_a_kind_on_tells_what_there_is_to_download(reader):
    reader.patch(f'/api/projects/{PID}', json={'media_mode_audio': 'manual'})

    video = reader.patch(f'/api/projects/{PID}', json={'media_mode_video': 'auto'}).json()
    audio = reader.patch(f'/api/projects/{PID}', json={'media_mode_audio': 'auto'}).json()
    again = reader.patch(f'/api/projects/{PID}', json={'media_mode_audio': 'auto'}).json()

    # A video doesn't tell its size in advance; the audio file does.
    assert video['to_download'] == {'files': 1, 'bytes': 0, 'files_without_size': 1}
    assert audio['to_download'] == {'files': 1, 'bytes': 48211234, 'files_without_size': 0}
    # It was on already: nothing new to offer.
    assert again['to_download']['files'] == 0
    assert video['project']['media_mode_video'] == 'auto'


def test_bad_project_settings(reader):
    assert reader.patch(f'/api/projects/{PID}', json={'video_quality': 999}).status_code == 422
    assert reader.patch(f'/api/projects/{PID}', json={'media_mode_audio': 'sometimes'}).status_code == 422
    assert reader.patch('/api/projects/1', json={}).status_code == 404


def test_sync_history(reader, sync_service):
    reader.post('/api/sync', json={'project_ids': [PID]})
    wait_until_idle(sync_service)

    history = reader.get('/api/sync/history').json()

    assert [run['outcome'] for run in history] == ['ok', 'ok']
    latest, first = history
    assert (first['project_id'], first['title']) == (PID, 'Вымышленный альманах')
    assert (first['full'], first['posts_new'], first['posts_changed'], first['posts_deleted']) == (True, 6, 0, 0)
    assert (latest['full'], latest['posts_new']) == (False, 0)
    assert latest['finished_at'] >= latest['started_at']


def test_failed_downloads_are_listed_and_retried(reader, library, downloads, sponsr):
    # Nothing serves the files: every download fails.
    reader.post(f'/api/projects/{PID}/download')
    wait_for_downloads(downloads)

    failed = reader.get('/api/downloads/failed').json()
    assert failed['total'] == 2
    assert {(item['kind'], item['error']) for item in failed['items']} == {
        ('image', 'site_unavailable'),
        ('audio', 'site_unavailable'),
    }
    audio = next(item for item in failed['items'] if item['kind'] == 'audio')
    assert (audio['title'], audio['post_title'], audio['post_id'], audio['project_id']) == (
        'Альманах, выпуск 12',
        'Подкаст',
        site_data.POST_AUDIO,
        PID,
    )

    sponsr.serve_file('https://media.sponsr.ru/', PICTURE, needs_session=False)
    assert reader.post('/api/downloads/retry').json() == {'queued': 2}
    wait_for_downloads(downloads)

    assert reader.get('/api/downloads/failed').json() == {'total': 0, 'items': []}
    assert media_of(library, MediaKind.AUDIO).state is MediaState.DONE
    assert reader.post('/api/downloads/retry').json() == {'queued': 0}
