import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from offsponsr.auth import NoLibraryError, NotSignedInError
from offsponsr.library.models import AddedVia, MediaMode, Post, Project
from offsponsr.sync.events import EventBus
from offsponsr.sync.service import (
    InvalidAddressError,
    ProjectNotFoundError,
    RunningSync,
    SyncFailure,
    SyncState,
    project_address,
)

from . import site_data
from .fakes import PROJECT_PAGE_URL, SUBSCRIBED_URL, FakeFeed, posts_url

PID = site_data.PROJECT_ID
OTHER_ID = 5151
OTHER_URL = 'second-project'


def wait_until_idle(sync, timeout=10):
    deadline = time.monotonic() + timeout
    while sync.is_busy():
        assert time.monotonic() < deadline, 'The sync did not finish in time'
        time.sleep(0.01)


def record(events):
    """Everything published from now on, as a list that fills up."""
    listener = events.subscribe()
    seen = []

    def drain():
        while (event := listener.get(0.05)) is not None:
            seen.append(event)
        return seen

    return drain


def project_rows(library):
    with library.session() as db:
        return {project.id: project for project in db.scalars(select(Project))}


def post_count(library, project_id=PID):
    with library.session() as db:
        return len(db.scalars(select(Post).where(Post.project_id == project_id)).all())


@pytest.fixture
def second_project(sponsr):
    """A second made-up project on the fake site, reachable by its address but not subscribed to."""
    props = site_data.project_page_props()
    props['project'] = {**props['project'], 'id': OTHER_ID, 'project_url': OTHER_URL, 'project_title': 'Второй проект'}
    sponsr.page(f'https://sponsr.ru/{OTHER_URL}/', lambda: site_data.project_page_html(props))
    sponsr.api(
        f'https://sponsr.ru/api/v2/content/levels?project_id={OTHER_ID}'
        '&orderBy=level_price&orderByType=asc&withoutPagination=true',
        lambda: {'total': 0, 'list': []},
    )
    sponsr.api(
        f'https://sponsr.ru/api/v2/content/playlist?project_id={OTHER_ID}&withoutPagination=true',
        lambda: {'total': 0, 'list': []},
    )
    feed = FakeFeed(OTHER_ID)
    feed.publish(700, '<p>Открытый пост второго проекта</p>', level_id=None)
    sponsr.serve_feed(feed)
    return feed


@pytest.mark.parametrize(
    'text',
    [
        'fictional-almanac',
        '  fictional-almanac  ',
        '/fictional-almanac/',
        'https://sponsr.ru/fictional-almanac/',
        'https://sponsr.ru/fictional-almanac',
        'http://www.sponsr.ru/fictional-almanac/9005/dlinnoe-esse/',
        'sponsr.ru/fictional-almanac/collections/',
        'https://sponsr.ru/fictional-almanac/?utm_source=x#top',
    ],
)
def test_project_address(text):
    assert project_address(text) == 'fictional-almanac'


@pytest.mark.parametrize(
    'text', ['', '   ', 'https://example.com/fictional-almanac/', 'https://sponsr.ru/', 'two words']
)
def test_not_a_project_address(text):
    with pytest.raises(InvalidAddressError):
        project_address(text)


def test_subscriptions_are_offered(sync_service, signed_in, library):
    [choice] = sync_service.subscriptions()

    assert (choice.id, choice.url, choice.title) == (PID, site_data.PROJECT_URL, 'Вымышленный альманах')
    assert (choice.owner_name, choice.level_name) == ('Автор Выдуманный', 'Читатель')
    assert choice.in_library is False


def test_subscriptions_need_a_library_and_a_sign_in(sync_service, account, libraries, tmp_path):
    with pytest.raises(NoLibraryError):
        sync_service.subscriptions()

    libraries.create(tmp_path / 'library')

    with pytest.raises(NotSignedInError):
        sync_service.subscriptions()


def test_adding_a_subscription_downloads_it(sync_service, signed_in, library):
    added = sync_service.add_projects([PID])
    wait_until_idle(sync_service)

    assert added == [PID]
    project = project_rows(library)[PID]
    assert (project.url, project.added_via) == (site_data.PROJECT_URL, AddedVia.SUBSCRIPTION)
    # Audio and attachments come with the sync, video waits for the button.
    assert (project.media_mode_audio, project.media_mode_video, project.media_mode_attach) == (
        MediaMode.AUTO,
        MediaMode.MANUAL,
        MediaMode.AUTO,
    )
    assert project.subscription_level_id == site_data.LEVEL_BASIC
    assert project.last_paid == datetime(2026, 9, 21, 10, 15, tzinfo=UTC)
    assert project.last_synced_at is not None
    assert post_count(library) == 6
    assert sync_service.state() == SyncState()
    assert sync_service.subscriptions()[0].in_library is True


def test_adding_what_is_there_already_does_nothing(sync_service, signed_in, library, sponsr):
    sync_service.add_projects([PID])
    wait_until_idle(sync_service)
    requests_before = len(sponsr.calls(posts_url()))

    assert sync_service.add_projects([PID, PID]) == []
    wait_until_idle(sync_service)

    assert len(sponsr.calls(posts_url())) == requests_before


def test_unknown_subscription_is_skipped(sync_service, signed_in, library):
    assert sync_service.add_projects([999]) == []
    assert project_rows(library) == {}


@pytest.mark.parametrize('address', [OTHER_URL, f'https://sponsr.ru/{OTHER_URL}/'])
def test_adding_a_project_by_its_address(sync_service, signed_in, library, second_project, address):
    added = sync_service.add_projects([], address)
    wait_until_idle(sync_service)

    assert added == [OTHER_ID]
    project = project_rows(library)[OTHER_ID]
    assert (project.url, project.title, project.added_via) == (OTHER_URL, 'Второй проект', AddedVia.URL)
    assert project.subscription_level_id is None
    assert post_count(library, OTHER_ID) == 1


def test_adding_subscriptions_and_an_address_together(sync_service, signed_in, library, second_project):
    added = sync_service.add_projects([PID], OTHER_URL)
    wait_until_idle(sync_service)

    assert added == [PID, OTHER_ID]
    assert (post_count(library), post_count(library, OTHER_ID)) == (6, 1)
    assert sync_service.state().failures == ()


def test_address_that_is_not_one(sync_service, signed_in, library):
    with pytest.raises(InvalidAddressError):
        sync_service.add_projects([PID], 'https://example.com/x/')

    assert project_rows(library) == {}


def test_address_of_a_project_that_does_not_exist(sync_service, signed_in, library, sponsr):
    sponsr.routes['https://sponsr.ru/nobody-home/'] = lambda request: (404, '<html>404</html>', [])

    with pytest.raises(ProjectNotFoundError):
        sync_service.add_projects([], 'nobody-home')

    assert project_rows(library) == {}


def test_update_all(sync_service, signed_in, library, second_project, sponsr):
    sync_service.add_projects([PID], OTHER_URL)
    wait_until_idle(sync_service)
    with library.session() as db:
        db.get(Project, OTHER_ID).sync_enabled = False
        db.commit()
    second_project.publish(701, '<p>Ещё один</p>')
    sponsr.requests.clear()

    sync_service.start()
    wait_until_idle(sync_service)

    # Only the project that has syncing switched on was touched.
    assert any(f'project_id={PID}&' in request.url for request in sponsr.requests)
    assert not any(f'project_id={OTHER_ID}&' in request.url for request in sponsr.requests)
    assert post_count(library, OTHER_ID) == 1


def test_update_one_project(sync_service, signed_in, library, second_project):
    sync_service.add_projects([PID], OTHER_URL)
    wait_until_idle(sync_service)
    second_project.publish(701, '<p>Ещё один</p>')

    sync_service.start([OTHER_ID, 999])
    wait_until_idle(sync_service)

    assert post_count(library, OTHER_ID) == 2


def test_nothing_to_update(sync_service, signed_in, library, sponsr):
    assert sync_service.start([]) == SyncState()
    assert sync_service.start() == SyncState()
    assert sync_service.is_busy() is False


def test_progress_is_announced(sync_service, signed_in, library, events, sponsr):
    feed = FakeFeed()
    for number in range(25):
        feed.publish(100 + number, f'<p>Пост {number}</p>')
    sponsr.serve_feed(feed)
    drain = record(events)

    sync_service.add_projects([PID])
    wait_until_idle(sync_service)

    seen = drain()
    states = [event['state'] for event in seen if event['type'] == 'sync']
    title = 'Вымышленный альманах'
    running = lambda done, total: {'project_id': PID, 'title': title, 'posts_done': done, 'posts_total': total}  # noqa: E731
    assert [state['running'] for state in states] == [
        None,  # Queued.
        running(0, None),
        running(0, None),
        running(20, 25),
        running(25, 25),
        None,
    ]
    assert states[0]['queue'] == [PID]
    assert states[-1] == {'running': None, 'queue': [], 'failures': [], 'cancelling': False}
    # The list of projects changed when the project was added and again when its sync ended.
    assert [event['type'] for event in seen].count('projects') == 2


def test_site_that_changed_fails_one_project_and_not_the_next(sync_service, signed_in, library, second_project, sponsr):
    sponsr.routes[PROJECT_PAGE_URL] = lambda request: (200, '<html>redesigned</html>', [])

    sync_service.add_projects([PID], OTHER_URL)
    wait_until_idle(sync_service)

    assert sync_service.state().failures == (SyncFailure(PID, 'Вымышленный альманах', 'site_changed'),)
    assert post_count(library) == 0
    assert post_count(library, OTHER_ID) == 1


def test_expired_session_stops_the_whole_queue(sync_service, signed_in, library, second_project, sponsr):
    sync_service.add_projects([PID], OTHER_URL)
    wait_until_idle(sync_service)
    sponsr.revoke_tokens()
    sponsr.sign_out('good')

    sync_service.start()
    wait_until_idle(sync_service)

    state = sync_service.state()
    assert [failure.code for failure in state.failures] == ['session_expired']
    assert state.queue == ()
    assert signed_in.state().expired is True


def test_failures_are_forgotten_when_a_new_run_starts(sync_service, signed_in, library, sponsr):
    working = sponsr.routes[PROJECT_PAGE_URL]
    sponsr.routes[PROJECT_PAGE_URL] = lambda request: (200, '<html>redesigned</html>', [])
    sync_service.add_projects([PID])
    wait_until_idle(sync_service)
    assert len(sync_service.state().failures) == 1
    sponsr.routes[PROJECT_PAGE_URL] = working

    sync_service.start([PID])
    wait_until_idle(sync_service)

    assert sync_service.state() == SyncState()
    assert post_count(library) == 6


def test_cancel(sync_service, signed_in, library, sponsr, events):
    feed = FakeFeed()
    for number in range(65):
        feed.publish(100 + number, f'<p>Пост {number}</p>')
    sponsr.serve_feed(feed)

    def cancel_while_serving_page_two(request):
        state = sync_service.cancel()
        assert state.cancelling is True
        return 200, feed.posts_page(2), []

    sponsr.api(posts_url(page=2), lambda: None)
    sponsr.routes[posts_url(page=2)] = cancel_while_serving_page_two

    sync_service.add_projects([PID])
    wait_until_idle(sync_service)

    # The page in flight was saved, nothing after it was asked for, and nobody calls it a failure.
    assert post_count(library) == 40
    assert sync_service.state() == SyncState()
    assert not sponsr.calls(posts_url(page=3))
    assert project_rows(library)[PID].last_synced_at is None


def test_cancel_with_nothing_running(sync_service, signed_in, library):
    assert sync_service.cancel() == SyncState()


def test_shutdown_stops_a_running_sync(sync_service, signed_in, library, sponsr):
    feed = FakeFeed()
    for number in range(65):
        feed.publish(100 + number, f'<p>Пост {number}</p>')
    sponsr.serve_feed(feed)

    sync_service.add_projects([PID])
    sync_service.shutdown()

    # The worker is gone by the time shutdown returns, however far it got.
    assert sync_service.is_busy() is False
    assert post_count(library) < 65
    assert project_rows(library)[PID].last_synced_at is None


def test_state_json():
    state = SyncState(
        running=RunningSync(1, 'Проект', 20, 45),
        queue=(2, 3),
        failures=(SyncFailure(4, 'Другой', 'site_changed'),),
    )

    assert state.to_json() == {
        'running': {'project_id': 1, 'title': 'Проект', 'posts_done': 20, 'posts_total': 45},
        'queue': [2, 3],
        'failures': [{'project_id': 4, 'title': 'Другой', 'code': 'site_changed'}],
        'cancelling': False,
    }


def test_event_bus():
    bus = EventBus()
    first, second = bus.subscribe(), bus.subscribe()

    bus.publish({'type': 'projects'})
    second.close()
    bus.publish({'type': 'sync'})

    assert [first.get(0.01), first.get(0.01), first.get(0.01)] == [{'type': 'projects'}, {'type': 'sync'}, None]
    assert [second.get(0.01), second.get(0.01)] == [{'type': 'projects'}, None]

    bus.close()

    with pytest.raises(EOFError):
        first.get(0.01)
    with pytest.raises(EOFError):
        bus.subscribe().get(0.01)


def test_subscriptions_trouble_fails_the_first_project(sync_service, signed_in, library, sponsr):
    sync_service.add_projects([PID])
    wait_until_idle(sync_service)
    sponsr.routes[SUBSCRIBED_URL] = lambda request: (200, {'unexpected': True}, [])

    sync_service.start([PID])
    wait_until_idle(sync_service)

    assert [failure.code for failure in sync_service.state().failures] == ['site_changed']
