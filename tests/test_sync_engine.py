from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from offsponsr.auth import SiteUnavailableError
from offsponsr.library.models import (
    Account,
    AddedVia,
    Level,
    Media,
    MediaKind,
    MediaMode,
    MediaState,
    Post,
    PostStatus,
    PostTag,
    Project,
    SyncRun,
    Tag,
)
from offsponsr.sponsr import SponsrClient
from offsponsr.sync.engine import FULL_PASS_EVERY, ProjectSync, SyncCancelled, SyncProgress

from . import site_data
from .fakes import FakeFeed, more_posts_url, posts_url

PID = site_data.PROJECT_ID
LONG_TEXT = '<p>' + 'Очень длинный текст. ' * 40 + '</p>'


@pytest.fixture
def feed(sponsr):
    feed = FakeFeed()
    sponsr.serve_feed(feed)
    return feed


@pytest.fixture
def client(signed_in):
    return SponsrClient(signed_in, pause=0, sleep=lambda seconds: None)


@pytest.fixture
def project(library):
    with library.session() as db:
        db.add(
            Project(
                id=PID,
                url=site_data.PROJECT_URL,
                title='Ещё без названия',
                added_via=AddedVia.SUBSCRIPTION,
                media_mode_audio=MediaMode.AUTO,
                media_mode_video=MediaMode.MANUAL,
                media_mode_attach=MediaMode.AUTO,
            )
        )
        db.commit()
    return PID


@pytest.fixture
def sync(library, client, project):
    return ProjectSync(library, client)


def post_requests(sponsr):
    """Which pages of the two lists were asked for, in order."""
    pages = []
    for request in sponsr.requests:
        if '/content/posts/?' in request.url:
            pages.append(('posts', int(request.url.split('&page=')[1].split('&')[0])))
        elif '/more-posts/' in request.url:
            pages.append(('texts', int(request.url.split('offset=')[1]) // 20 + 1))
    return pages


def posts(library):
    with library.session() as db:
        return {post.id: post for post in db.scalars(select(Post))}


def media(library, post_id):
    with library.session() as db:
        return {m.kind: m for m in db.scalars(select(Media).where(Media.post_id == post_id))}


def test_first_sync_stores_the_whole_feed(sync, library, sponsr):
    # No FakeFeed here: the fake site serves the six posts of site_data.
    stats = sync.run(PID)

    stored = posts(library)
    assert set(stored) == {9001, 9002, 9003, 9004, 9005, 9006}
    assert (stats.full, stats.pages, stats.posts_seen, stats.posts_new) == (True, 1, 6, 6)

    short = stored[site_data.POST_SHORT]
    assert short.html == site_data.FULL_TEXTS[site_data.POST_SHORT]
    assert short.html_is_full is True
    assert short.title == 'Короткая заметка'
    assert short.date == datetime(2026, 9, 30, 18, 15, tzinfo=UTC)
    assert short.updated_at_site == datetime(2026, 9, 30, 18, 15, tzinfo=UTC)
    assert short.level_id == site_data.LEVEL_BASIC
    assert short.status is PostStatus.ACTIVE
    assert short.available is True
    assert short.raw_json['cnt_likes'] == 3
    assert 'text' not in short.raw_json


def test_long_post_gets_its_whole_text_without_marks(sync, library):
    stats = sync.run(PID)

    long = posts(library)[site_data.POST_LONG]
    assert long.html == site_data.FULL_TEXTS[site_data.POST_LONG]
    assert long.html_is_full is True
    assert long.fetched_at is not None
    assert long.updated_at_site == datetime(2026, 9, 29, 12, 30, tzinfo=UTC)
    assert stats.texts_fetched == 1


def test_closed_post_is_stored_without_text(sync, library):
    sync.run(PID)

    closed = posts(library)[site_data.POST_CLOSED]
    assert closed.available is False
    assert closed.html is None
    assert closed.html_is_full is False
    assert closed.status is PostStatus.ACTIVE
    assert closed.level_id == site_data.LEVEL_HIDDEN
    assert closed.title == 'Закрытый материал для старшего уровня'


def test_media_of_the_posts(sync, library):
    sync.run(PID)

    picture = media(library, site_data.POST_SHORT)[MediaKind.IMAGE]
    assert picture.state is MediaState.PENDING
    assert picture.source_url.startswith('https://media.sponsr.ru/project/4242/post/9006/image/31/')
    assert picture.local_path is None

    video = media(library, site_data.POST_VIDEO)[MediaKind.VIDEO]
    assert (video.source_id, video.source_url) == (site_data.VIDEO_ID, site_data.KINESCOPE_EMBED)

    audio = media(library, site_data.POST_AUDIO)[MediaKind.AUDIO]
    assert (audio.source_id, audio.title, audio.size, audio.duration) == ('6001', 'Альманах, выпуск 12', 48211234, 1835)
    assert audio.source_url.startswith('/uploads/files/p4242/9003/')

    assert media(library, site_data.POST_CLOSED) == {}


def test_project_card_levels_and_collections(sync, library, signed_in):
    sync.run(PID)

    with library.session() as db:
        project = db.get(Project, PID)
        levels = {level.id: level for level in db.scalars(select(Level))}
        tags = {tag.id: tag for tag in db.scalars(select(Tag))}
        links = {(link.post_id, link.tag_id) for link in db.scalars(select(PostTag))}
        account = db.scalars(select(Account)).one()

    assert project.title == 'Вымышленный альманах'
    assert project.intent == 'на выдуманные тексты'
    assert project.description_html == '<p>Альманах, которого <b>не существует</b>.</p>'
    assert project.raw_json['image'] == '/images/projects/42/4242/bg.webp?5d41402abc4b2a76'
    assert project.last_synced_at is not None

    assert (levels[site_data.LEVEL_BASIC].name, levels[site_data.LEVEL_BASIC].price) == ('Читатель', 300)
    assert [levels[i].visible for i in (site_data.LEVEL_BASIC, site_data.LEVEL_HIDDEN, site_data.LEVEL_DELETED)] == [
        True,
        False,
        False,
    ]
    assert {tag_id: (tag.name, tag.count) for tag_id, tag in tags.items()} == {
        site_data.TAG_ESSAYS: ('Эссе', 1),
        site_data.TAG_TALKS: ('Лекции', 2),
    }
    assert links == {
        (site_data.POST_LONG, site_data.TAG_ESSAYS),
        (site_data.POST_VIDEO, site_data.TAG_TALKS),
        (site_data.POST_AUDIO, site_data.TAG_TALKS),
    }
    assert account.nickname == 'reader'


def test_subscription_details_are_recorded(library, client, project):
    [subscription] = client.subscriptions()

    ProjectSync(library, client).run(PID, subscription)

    with library.session() as db:
        stored = db.get(Project, PID)
    assert stored.subscription_level_id == site_data.LEVEL_BASIC
    assert stored.last_paid == datetime(2026, 9, 21, 10, 15, tzinfo=UTC)


def test_run_is_recorded(sync, library):
    sync.run(PID)

    with library.session() as db:
        [run] = db.scalars(select(SyncRun)).all()
    assert run.scope == f'project:{PID}'
    assert run.error is None
    assert run.finished_at >= run.started_at
    assert run.stats_json == {
        'full': True,
        'pages': 1,
        'posts_seen': 6,
        'posts_new': 6,
        'posts_changed': 0,
        'texts_fetched': 1,
        'posts_deleted': 0,
    }


def test_progress_is_reported(library, client, project, feed):
    for number in range(45):
        feed.publish(100 + number, f'<p>Пост {number}</p>')
    seen = []

    ProjectSync(library, client, on_progress=seen.append).run(PID)

    assert seen == [
        SyncProgress(PID, 0, None),
        SyncProgress(PID, 20, 45),
        SyncProgress(PID, 40, 45),
        SyncProgress(PID, 45, 45),
    ]


def test_whole_texts_are_asked_only_for_pages_that_need_them(sync, sponsr, feed):
    for number in range(45):
        # Only the 31st post, on the second page, is long.
        feed.publish(100 + number, LONG_TEXT if number == 14 else f'<p>Пост {number}</p>', long=number == 14)

    stats = sync.run(PID)

    assert post_requests(sponsr) == [('posts', 1), ('posts', 2), ('texts', 2), ('posts', 3)]
    assert stats.texts_fetched == 1


def test_second_sync_stops_at_the_first_page_with_nothing_new(sync, library, sponsr, feed):
    for number in range(45):
        feed.publish(100 + number, LONG_TEXT, long=True)
    sync.run(PID)
    sponsr.requests.clear()

    stats = sync.run(PID)

    assert post_requests(sponsr) == [('posts', 1)]
    assert (stats.full, stats.pages, stats.posts_new, stats.posts_changed, stats.texts_fetched) == (False, 1, 0, 0, 0)
    assert len(posts(library)) == 45


def test_new_posts_are_picked_up(sync, library, sponsr, feed):
    for number in range(45):
        feed.publish(100 + number, f'<p>Пост {number}</p>')
    sync.run(PID)
    feed.publish(500, LONG_TEXT, long=True)
    sponsr.requests.clear()

    stats = sync.run(PID)

    # The first page has the new post, the second has nothing new, and that is where it stops.
    assert post_requests(sponsr) == [('posts', 1), ('texts', 1), ('posts', 2)]
    assert (stats.posts_new, stats.texts_fetched) == (1, 1)
    assert posts(library)[500].html == LONG_TEXT


def test_edited_post_is_fetched_again(sync, library, feed):
    feed.publish(100, f'<p>Было</p>{site_data.IMAGE}{site_data.VIDEO}')
    sync.run(PID)
    with library.session() as db:
        video = db.scalars(select(Media).where(Media.kind == MediaKind.VIDEO)).one()
        video.state = MediaState.DONE
        video.local_path = 'projects/x/video/a.mp4'
        db.commit()
    feed.edit(100, LONG_TEXT, long=True)

    stats = sync.run(PID)

    edited = posts(library)[100]
    assert edited.html == LONG_TEXT
    assert edited.updated_at_site == datetime(2026, 2, 2, tzinfo=UTC)
    assert (stats.posts_new, stats.posts_changed, stats.texts_fetched) == (0, 1, 1)
    # The picture is gone with the old text; the video was already downloaded, so its row stays.
    kept = media(library, 100)
    assert set(kept) == {MediaKind.VIDEO}
    assert kept[MediaKind.VIDEO].local_path == 'projects/x/video/a.mp4'


def test_views_are_refreshed_without_calling_it_a_change(sync, library, feed):
    feed.publish(100, '<p>Пост</p>')
    sync.run(PID)
    feed.entries[0][0]['views'] = 999

    stats = sync.run(PID)

    assert posts(library)[100].views == 999
    assert stats.posts_changed == 0


def test_post_that_is_closed_later_keeps_its_text(sync, library, feed):
    feed.publish(100, LONG_TEXT, long=True)
    sync.run(PID)
    feed.close(100)

    sync.run(PID)

    closed = posts(library)[100]
    assert closed.available is False
    assert closed.status is PostStatus.UNAVAILABLE
    assert closed.html == LONG_TEXT
    assert closed.html_is_full is True


def test_post_that_opens_later_gets_its_text(sync, library, feed):
    feed.publish_closed(100)
    sync.run(PID)
    assert posts(library)[100].html is None
    feed.delete(100)
    feed.publish(100, LONG_TEXT, long=True)

    stats = sync.run(PID)

    opened = posts(library)[100]
    assert (opened.available, opened.status, opened.html) == (True, PostStatus.ACTIVE, LONG_TEXT)
    assert stats.texts_fetched == 1


def test_reopened_post_becomes_active_again(sync, library, feed):
    listed = feed.publish(100, LONG_TEXT, long=True)
    sync.run(PID)
    feed.close(100)
    sync.run(PID)
    feed.delete(100)
    feed.entries.insert(0, (listed, LONG_TEXT))

    sync.run(PID)

    assert posts(library)[100].status is PostStatus.ACTIVE
    assert posts(library)[100].available is True


def test_deleted_posts_are_noticed_on_a_full_pass(sync, library, sponsr, feed):
    for number in range(45):
        feed.publish(100 + number, f'<p>Пост {number}</p>')
    sync.run(PID)
    feed.delete(100)  # The oldest one, on the last page.

    # One full pass, then nine that only look at the top of the list.
    for _ in range(FULL_PASS_EVERY - 1):
        assert sync.run(PID).full is False
    assert posts(library)[100].status is PostStatus.ACTIVE

    sponsr.requests.clear()
    stats = sync.run(PID)

    assert stats.full is True
    assert stats.posts_deleted == 1
    assert post_requests(sponsr) == [('posts', 1), ('posts', 2), ('posts', 3)]
    gone = posts(library)[100]
    assert gone.status is PostStatus.DELETED_ON_SITE
    assert gone.html == '<p>Пост 0</p>'
    # And the count starts over.
    assert sync.run(PID).full is False


def test_post_that_comes_back_is_active_again(sync, library, feed):
    listed = feed.publish(100, '<p>Пост</p>')
    feed.publish(101, '<p>Другой</p>')
    sync.run(PID)
    feed.delete(100)
    for _ in range(FULL_PASS_EVERY):
        sync.run(PID)
    assert posts(library)[100].status is PostStatus.DELETED_ON_SITE
    feed.entries.insert(0, (listed, '<p>Пост</p>'))

    sync.run(PID)

    assert posts(library)[100].status is PostStatus.ACTIVE


def test_cancelled_sync_keeps_what_it_saved_and_the_next_one_finishes(library, client, project, sponsr, feed):
    for number in range(45):
        feed.publish(100 + number, LONG_TEXT, long=True)
    progress = []
    stopping = ProjectSync(library, client, on_progress=progress.append, should_stop=lambda: len(progress) >= 2)

    with pytest.raises(SyncCancelled):
        stopping.run(PID)

    assert len(posts(library)) == 20
    with library.session() as db:
        [run] = db.scalars(select(SyncRun)).all()
        assert run.error == 'SyncCancelled'
        assert run.stats_json['posts_seen'] == 20
        assert db.get(Project, PID).last_synced_at is None

    sponsr.requests.clear()
    stats = ProjectSync(library, client).run(PID)

    # A full pass again, but the texts of the first page are already there.
    assert stats.full is True
    assert post_requests(sponsr) == [('posts', 1), ('posts', 2), ('texts', 2), ('posts', 3), ('texts', 3)]
    assert len(posts(library)) == 45
    assert all(post.html_is_full for post in posts(library).values())


def test_text_missing_from_the_legacy_list_is_asked_again_next_time(sync, library, sponsr, feed):
    feed.publish(100, LONG_TEXT, long=True)
    feed.missing_from_legacy.add(100)

    stats = sync.run(PID)

    waiting = posts(library)[100]
    assert stats.texts_fetched == 0
    assert waiting.html_is_full is False
    assert waiting.html == LONG_TEXT[: len(LONG_TEXT) // 2]
    assert waiting.updated_at_site is None

    feed.missing_from_legacy.clear()
    sponsr.requests.clear()
    stats = sync.run(PID)

    assert post_requests(sponsr) == [('posts', 1), ('texts', 1)]
    assert stats.texts_fetched == 1
    assert posts(library)[100].html == LONG_TEXT
    assert posts(library)[100].updated_at_site is not None


def test_site_trouble_stops_the_sync_and_is_recorded(sync, library, sponsr, feed):
    for number in range(45):
        feed.publish(100 + number, f'<p>Пост {number}</p>')
    sponsr.routes[posts_url(page=2)] = lambda request: (500, {}, [])

    with pytest.raises(SiteUnavailableError):
        sync.run(PID)

    assert len(posts(library)) == 20
    with library.session() as db:
        [run] = db.scalars(select(SyncRun)).all()
        assert run.error == 'SiteUnavailableError'
        assert db.get(Project, PID).last_synced_at is None


def test_unknown_project(library, client):
    with pytest.raises(LookupError):
        ProjectSync(library, client).run(404)


def test_sync_never_asks_for_a_single_post(sync, sponsr):
    sync.run(PID)

    for request in sponsr.requests:
        assert f'/{site_data.PROJECT_URL}/90' not in request.url
        assert '/content/posts/90' not in request.url
    assert more_posts_url() in [request.url for request in sponsr.requests]
