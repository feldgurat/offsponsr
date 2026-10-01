import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from offsponsr.library.models import AddedVia, Media, MediaKind, MediaMode, MediaState, Post, Project
from offsponsr.media import kinescope
from offsponsr.media.downloader import DownloadService, DownloadState, file_url
from offsponsr.media.ffmpeg import FfmpegError
from offsponsr.media.files import DownloadError
from offsponsr.sponsr import SponsrClient
from offsponsr.sync.engine import ProjectSync
from offsponsr.sync.service import SyncService

from . import site_data
from .fakes import FakeFeed

PID = site_data.PROJECT_ID
MEDIA = 'https://media.sponsr.ru'
PICTURE = b'picture' * 100
AUDIO = b'audio' * 1000
LOGO = b'logo'
PROJECT_COVER = b'project cover'
POST_COVER = b'post cover'

SHORT_FOLDER = 'projects/fictional-almanac/2026-09-30 [9006] Короткая заметка'
AUDIO_FOLDER = 'projects/fictional-almanac/2026-09-27 [9003] Подкаст'


def wait_until_idle(service, timeout=10):
    deadline = time.monotonic() + timeout
    while service.is_busy():
        assert time.monotonic() < deadline, 'The downloads did not finish in time'
        time.sleep(0.01)


@pytest.fixture
def media_host(sponsr):
    """The fake site's media: every file of the made-up project, each with a log of the ranges asked."""
    return {
        'picture': sponsr.serve_file(f'{MEDIA}/project/4242/post/9006/image/31/', PICTURE),
        'audio': sponsr.serve_file(file_url(PID, site_data.POST_AUDIO, '6001'), AUDIO, needs_session=True),
        'logo': sponsr.serve_file(f'{MEDIA}/images/projects/42/4242/logo@2x.webp', LOGO),
        'project_cover': sponsr.serve_file(f'{MEDIA}/images/projects/42/4242/bg.webp', PROJECT_COVER),
        'post_cover': sponsr.serve_file(f'{MEDIA}/images/projects/42/4242/7e/', POST_COVER),
        'closed_cover': sponsr.serve_file(f'{MEDIA}/images/projects/42/4242/1a/', POST_COVER),
    }


@pytest.fixture
def client(signed_in):
    return SponsrClient(signed_in, pause=0, sleep=lambda seconds: None)


@pytest.fixture
def synced(library, client):
    """A library with the made-up project synced: texts in, no media downloaded yet."""
    with library.session() as db:
        db.add(
            Project(
                id=PID,
                url=site_data.PROJECT_URL,
                title='Вымышленный альманах',
                added_via=AddedVia.SUBSCRIPTION,
                media_mode_audio=MediaMode.AUTO,
                media_mode_video=MediaMode.MANUAL,
                media_mode_attach=MediaMode.AUTO,
            )
        )
        db.commit()
    ProjectSync(library, client).run(PID)
    return library


def media_rows(library):
    with library.session() as db:
        return {media.kind: media for media in db.scalars(select(Media))}


def test_media_of_a_synced_project_is_downloaded(downloads, synced, media_host):
    queued = downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    # A logo, two covers of posts, a cover of the project, a picture and an audio file.
    assert queued == 6
    rows = media_rows(synced)
    picture, audio = rows[MediaKind.IMAGE], rows[MediaKind.AUDIO]
    assert (picture.state, picture.local_path, picture.size) == (
        MediaState.DONE,
        f'{SHORT_FOLDER}/images/31.webp',
        len(PICTURE),
    )
    assert (audio.state, audio.local_path) == (MediaState.DONE, f'{AUDIO_FOLDER}/audio/Альманах, выпуск 12.mp3')
    assert (synced.root / picture.local_path).read_bytes() == PICTURE
    assert (synced.root / audio.local_path).read_bytes() == AUDIO

    with synced.session() as db:
        project = db.get(Project, PID)
        short, closed = db.get(Post, site_data.POST_SHORT), db.get(Post, site_data.POST_CLOSED)
    assert project.logo_path == 'projects/fictional-almanac/_project/logo.webp'
    assert project.cover_path == 'projects/fictional-almanac/_project/cover.webp'
    assert (synced.root / project.logo_path).read_bytes() == LOGO
    assert (synced.root / project.cover_path).read_bytes() == PROJECT_COVER
    assert short.cover_path == f'{SHORT_FOLDER}/cover.webp'
    assert (synced.root / short.cover_path).read_bytes() == POST_COVER
    # A closed post still shows its cover, as on the site.
    assert closed.cover_path.endswith('[9002] Закрытый материал для старшего уровня/cover.jpg')

    assert downloads.state() == DownloadState(done=6)
    # Nothing is left among the unfinished downloads.
    assert list(synced.tmp_dir.iterdir()) == []


def test_video_waits_for_the_button(downloads, synced, media_host):
    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    video = media_rows(synced)[MediaKind.VIDEO]
    assert (video.state, video.local_path) == (MediaState.PENDING, None)


def test_audio_goes_by_the_accounts_session(downloads, synced, media_host, sponsr):
    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    by_url = {request.url: request for request in sponsr.requests}
    assert 'SESS=good' in by_url[file_url(PID, site_data.POST_AUDIO, '6001')].headers['Cookie']
    # Pictures are public: the session is not shown where it isn't needed.
    picture = next(request for request in sponsr.requests if '/image/31/' in request.url)
    assert 'Cookie' not in picture.headers


def test_nothing_is_downloaded_twice(downloads, synced, media_host, sponsr):
    downloads.enqueue_project(PID)
    wait_until_idle(downloads)
    requests_before = len(sponsr.requests)

    assert downloads.enqueue_project(PID) == 0
    assert len(sponsr.requests) == requests_before


def test_manual_modes_leave_audio_alone(downloads, synced, media_host):
    with synced.session() as db:
        db.get(Project, PID).media_mode_audio = MediaMode.MANUAL
        db.commit()

    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    assert media_rows(synced)[MediaKind.AUDIO].state is MediaState.PENDING
    assert media_host['audio'] == []


def test_one_file_on_demand(downloads, synced, media_host):
    with synced.session() as db:
        db.get(Project, PID).media_mode_audio = MediaMode.MANUAL
        db.commit()
    audio_id = media_rows(synced)[MediaKind.AUDIO].id

    assert downloads.enqueue_media(audio_id) == 1
    wait_until_idle(downloads)

    assert media_rows(synced)[MediaKind.AUDIO].state is MediaState.DONE
    # Asking again for what is there does nothing.
    assert downloads.enqueue_media(audio_id) == 0
    assert downloads.enqueue_media(999999) == 0


def test_video_on_demand(downloads, synced, media_host, monkeypatch, ffmpeg_path):
    calls = []

    def fake_download(http, embed_url, dest, **options):
        calls.append((embed_url, options))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b'video')
        options['on_progress'](5, 5)

    monkeypatch.setattr(kinescope, 'download', fake_download)
    with synced.session() as db:
        db.get(Project, PID).video_quality = 480
        db.commit()
    video_id = media_rows(synced)[MediaKind.VIDEO].id

    downloads.enqueue_media(video_id)
    wait_until_idle(downloads)

    video = media_rows(synced)[MediaKind.VIDEO]
    assert (video.state, video.size) == (MediaState.DONE, 5)
    assert video.local_path == 'projects/fictional-almanac/2026-09-28 [9004] Лекция/video/Лекция.mp4'
    [(embed_url, options)] = calls
    assert embed_url == site_data.KINESCOPE_EMBED
    assert options['max_height'] == 480
    assert options['ffmpeg'] == ffmpeg_path
    assert options['work_dir'] == synced.tmp_dir
    assert options['work_name'] == f'media-{video_id}'


def test_video_is_downloaded_with_the_rest_when_the_project_says_so(downloads, synced, media_host, monkeypatch):
    monkeypatch.setattr(kinescope, 'download', lambda http, url, dest, **options: dest.write_bytes(b'video'))
    with synced.session() as db:
        db.get(Project, PID).media_mode_video = MediaMode.AUTO
        db.commit()
    (synced.root / 'projects/fictional-almanac/2026-09-28 [9004] Лекция/video').mkdir(parents=True)

    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    assert media_rows(synced)[MediaKind.VIDEO].state is MediaState.DONE


def test_video_without_ffmpeg(libraries, account, events, synced, media_host):
    service = DownloadService(libraries, account, events, ffmpeg=lambda: None)
    video_id = media_rows(synced)[MediaKind.VIDEO].id

    service.enqueue_media(video_id)
    wait_until_idle(service)

    video = media_rows(synced)[MediaKind.VIDEO]
    assert (video.state, video.error) == (MediaState.ERROR, 'no_ffmpeg')
    assert service.state().failed == 1


def test_only_the_files_that_failed_for_one_reason_can_be_tried_again(
    downloads, synced, media_host, machine, events, sponsr, monkeypatch
):
    machine.ffmpeg = None
    sponsr.patterns.append((file_url(PID, site_data.POST_AUDIO, '6001'), lambda request: (404, b'', [])))
    rows = media_rows(synced)
    downloads.enqueue_media(rows[MediaKind.VIDEO].id)
    downloads.enqueue_media(rows[MediaKind.AUDIO].id)
    wait_until_idle(downloads)
    rows = media_rows(synced)
    assert rows[MediaKind.VIDEO].error == 'no_ffmpeg'
    assert rows[MediaKind.AUDIO].state is MediaState.ERROR

    def fake_download(http, embed_url, dest, **options):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b'video')

    monkeypatch.setattr(kinescope, 'download', fake_download)
    machine.ffmpeg = machine.make_ffmpeg('installed/ffmpeg')
    listener = events.subscribe()

    assert downloads.enqueue_failed('no_ffmpeg') == 1
    wait_until_idle(downloads)

    rows = media_rows(synced)
    assert rows[MediaKind.VIDEO].state is MediaState.DONE
    assert rows[MediaKind.AUDIO].state is MediaState.ERROR
    # The pages showing the video as failed are told to read it again, before the download and after.
    files = []
    while (event := listener.get(0)) is not None:
        if event['type'] == 'file':
            files.append(event['id'])
    assert files == [rows[MediaKind.VIDEO].id] * 2
    assert downloads.enqueue_failed('no_ffmpeg') == 0


@pytest.mark.parametrize(
    ('failure', 'code'),
    [(DownloadError('player_changed'), 'player_changed'), (FfmpegError('boom'), 'ffmpeg_failed')],
)
def test_video_failures_are_recorded(downloads, synced, media_host, monkeypatch, failure, code):
    def failing(http, url, dest, **options):
        raise failure

    monkeypatch.setattr(kinescope, 'download', failing)

    downloads.enqueue_media(media_rows(synced)[MediaKind.VIDEO].id)
    wait_until_idle(downloads)

    assert media_rows(synced)[MediaKind.VIDEO].error == code


def test_failed_file_is_marked_and_tried_again_next_time(downloads, synced, media_host, sponsr):
    sponsr.patterns.append((f'{MEDIA}/project/4242/post/9006/image/31/', lambda request: (404, b'', [])))

    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    picture = media_rows(synced)[MediaKind.IMAGE]
    assert (picture.state, picture.error, picture.local_path) == (MediaState.ERROR, 'not_found', None)
    assert downloads.state() == DownloadState(done=5, failed=1)
    sponsr.patterns.pop()

    assert downloads.enqueue_project(PID) == 1
    wait_until_idle(downloads)

    picture = media_rows(synced)[MediaKind.IMAGE]
    assert (picture.state, picture.error) == (MediaState.DONE, None)
    # A new batch counts from zero.
    assert downloads.state() == DownloadState(done=1)


def test_audio_without_a_session_fails_cleanly(downloads, synced, media_host, signed_in):
    signed_in.logout()

    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    rows = media_rows(synced)
    assert (rows[MediaKind.AUDIO].state, rows[MediaKind.AUDIO].error) == (MediaState.ERROR, 'not_signed_in')
    # What is public is still downloaded.
    assert rows[MediaKind.IMAGE].state is MediaState.DONE


def test_unfinished_download_is_continued(downloads, synced, media_host):
    audio_id = media_rows(synced)[MediaKind.AUDIO].id
    (synced.tmp_dir / f'media-{audio_id}.part').write_bytes(AUDIO[:1234])

    downloads.enqueue_media(audio_id)
    wait_until_idle(downloads)

    assert media_host['audio'] == ['bytes=1234-']
    audio = media_rows(synced)[MediaKind.AUDIO]
    assert (synced.root / audio.local_path).read_bytes() == AUDIO


def test_files_with_the_same_title_get_different_names(downloads, library, client, sponsr, media_host):
    feed = FakeFeed()
    file = {**site_data.posts_page()['list'][3]['files'][0], 'post_id': 100}
    feed.publish(
        100, '<p>Два файла</p>', files=[{**file, 'id': 1, 'title': 'Запись'}, {**file, 'id': 2, 'title': 'Запись'}]
    )
    sponsr.serve_feed(feed)
    sponsr.serve_file(f'{MEDIA}/project/{PID}/post/100/file/', AUDIO, needs_session=True)
    with library.session() as db:
        db.add(
            Project(
                id=PID, url=site_data.PROJECT_URL, title='x', added_via=AddedVia.SUBSCRIPTION,
                media_mode_audio=MediaMode.AUTO, media_mode_video=MediaMode.MANUAL, media_mode_attach=MediaMode.AUTO,
            )
        )  # fmt: skip
        db.commit()
    ProjectSync(library, client).run(PID)

    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    with library.session() as db:
        names = sorted(media.local_path.rsplit('/', 1)[1] for media in db.scalars(select(Media)))
    assert names == ['Запись (2).mp3', 'Запись.mp3']


def test_post_keeps_its_folder_when_it_is_renamed(downloads, synced, media_host, client, sponsr):
    downloads.enqueue_project(PID)
    wait_until_idle(downloads)
    feed = FakeFeed()
    feed.publish(
        site_data.POST_SHORT,
        f'{site_data.FULL_TEXTS[site_data.POST_SHORT]}<img src="{MEDIA}/project/4242/post/9006/image/32/second.png?1">',
        title='Заметка с новым названием',
        date='2026-09-30T18:15:00.000Z',
        updated_at='2026-10-01T10:00:00.000Z',
        image='/images/projects/42/4242/7e/yn/u4//42ab12cd_original.webp',
    )
    sponsr.serve_feed(feed)
    sponsr.serve_file(f'{MEDIA}/project/4242/post/9006/image/32/', b'second picture')
    ProjectSync(synced, client).run(PID)

    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    with synced.session() as db:
        paths = sorted(
            media.local_path for media in db.scalars(select(Media).where(Media.post_id == site_data.POST_SHORT))
        )
    assert paths == [f'{SHORT_FOLDER}/images/31.webp', f'{SHORT_FOLDER}/images/32.png']


def test_new_cover_address_downloads_the_cover_again(downloads, synced, media_host, client, sponsr):
    downloads.enqueue_project(PID)
    wait_until_idle(downloads)
    props = site_data.project_page_props()
    props['project']['image'] = '/images/projects/42/4242/bg.webp?new-stamp'
    sponsr.page(f'https://sponsr.ru/{site_data.PROJECT_URL}/', lambda: site_data.project_page_html(props))
    ProjectSync(synced, client).run(PID)
    with synced.session() as db:
        assert db.get(Project, PID).cover_path is None
        assert db.get(Project, PID).logo_path is not None
    media_host['project_cover'].clear()

    assert downloads.enqueue_project(PID) == 1
    wait_until_idle(downloads)

    assert media_host['project_cover'] == [None]
    with synced.session() as db:
        assert db.get(Project, PID).cover_path == 'projects/fictional-almanac/_project/cover.webp'


def test_cancel(libraries, account, events, synced, media_host, sponsr):
    service = DownloadService(libraries, account, events, workers=1)
    started = []

    def slow_picture(request):
        # The first download is in flight: cancel from the outside, as the button does.
        started.append(service.cancel())
        return 200, PICTURE, [], {'Content-Length': str(len(PICTURE))}

    sponsr.patterns.append((f'{MEDIA}/images/projects/42/4242/logo@2x.webp', slow_picture))

    service.enqueue_project(PID)
    wait_until_idle(service)

    assert started[0].cancelling is True
    assert started[0].queued == 0
    rows = media_rows(synced)
    # What was waiting goes back to "not downloaded", not to "failed".
    assert rows[MediaKind.IMAGE].state is MediaState.PENDING
    assert rows[MediaKind.AUDIO].state is MediaState.PENDING
    assert service.state().failed == 0
    assert service.state().cancelling is False

    # And the next batch runs as usual.
    sponsr.patterns.pop()
    service.enqueue_project(PID)
    wait_until_idle(service)
    assert media_rows(synced)[MediaKind.AUDIO].state is MediaState.DONE
    service.shutdown()


def test_progress_is_announced(downloads, synced, media_host, events):
    listener = events.subscribe()

    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    states = []
    finished = []
    while (event := listener.get(0.05)) is not None:
        if event['type'] == 'file':
            finished.append((event['kind'], event['id']))
        else:
            assert event['type'] == 'downloads'
            states.append(event['state'])
    # Every file that is through says so, for whoever is showing it.
    assert len(finished) == 6
    assert {kind for kind, _ in finished} == {'media', 'post_cover', 'project_logo', 'project_cover'}
    assert states[0]['queued'] + len(states[0]['active']) == 6
    assert states[-1] == {'active': [], 'queued': 0, 'done': 6, 'failed': 0, 'cancelling': False}
    titles = {download['title'] for state in states for download in state['active']}
    assert 'Альманах, выпуск 12' in titles


def test_no_library_no_downloads(downloads):
    assert downloads.enqueue_project(PID) == 0
    assert downloads.enqueue_media(1) == 0
    assert downloads.cancel() == DownloadState()


def test_unknown_project(downloads, library):
    assert downloads.enqueue_project(404) == 0


def test_sync_hands_the_project_over_to_the_downloads(libraries, signed_in, events, downloads, media_host, library):
    sync = SyncService(
        libraries,
        signed_in,
        events,
        make_client=lambda account: SponsrClient(account, pause=0, sleep=lambda seconds: None),
        on_synced=downloads.enqueue_project,
    )

    sync.add_projects([PID])
    deadline = time.monotonic() + 10
    while sync.is_busy() or downloads.is_busy():
        assert time.monotonic() < deadline
        time.sleep(0.01)

    assert media_rows(library)[MediaKind.AUDIO].state is MediaState.DONE
    with library.session() as db:
        assert db.get(Project, PID).logo_path is not None
    sync.shutdown()


def test_post_dates_in_folder_names_follow_the_sites_clock(downloads, library, client, sponsr, media_host):
    feed = FakeFeed()
    feed.publish(
        100, f'<p><img src="{MEDIA}/project/4242/post/100/image/5/a.jpg"></p>', date='2026-12-31T21:30:00.000Z'
    )
    sponsr.serve_feed(feed)
    sponsr.serve_file(f'{MEDIA}/project/4242/post/100/image/5/', PICTURE)
    with library.session() as db:
        db.add(
            Project(
                id=PID, url=site_data.PROJECT_URL, title='x', added_via=AddedVia.SUBSCRIPTION,
                media_mode_audio=MediaMode.AUTO, media_mode_video=MediaMode.MANUAL, media_mode_attach=MediaMode.AUTO,
            )
        )  # fmt: skip
        db.commit()
    ProjectSync(library, client).run(PID)

    downloads.enqueue_project(PID)
    wait_until_idle(downloads)

    with library.session() as db:
        picture = db.scalars(select(Media)).one()
        assert db.get(Post, 100).date == datetime(2026, 12, 31, 21, 30, tzinfo=UTC)
    # Half past nine in the evening UTC is already the next year in Moscow.
    assert picture.local_path == 'projects/fictional-almanac/2027-01-01 [100] Пост 100/images/5.jpg'
