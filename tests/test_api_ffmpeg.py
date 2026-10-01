"""The API for ffmpeg: its state, installing one with winget, pointing at one."""

import time

import pytest

from offsponsr.library.models import MediaKind, MediaState
from offsponsr.media import kinescope
from offsponsr.media.ffmpeg_setup import PLATFORM

from . import site_data
from .fakes import FFMPEG_VERSION
from .test_api_reading import media_of, wait_for_downloads
from .test_sync_service import wait_until_idle


@pytest.fixture
def reader(session_client, signed_in, sync_service):
    """A session with the made-up project synced into the library; no media downloaded."""
    session_client.post('/api/projects', json={'subscription_ids': [site_data.PROJECT_ID]})
    wait_until_idle(sync_service)
    return session_client


def fake_video(http, url, dest, **options):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b'video')


def wait_for_install(client, timeout=10):
    deadline = time.monotonic() + timeout
    while (state := client.get('/api/ffmpeg').json())['installing']:
        assert time.monotonic() < deadline, 'The installation did not finish in time'
        time.sleep(0.01)
    return state


def test_ffmpeg_requires_session(client):
    assert client.get('/api/ffmpeg').status_code == 401
    assert client.post('/api/ffmpeg/install').status_code == 401
    assert client.post('/api/ffmpeg/choose').status_code == 401
    assert client.delete('/api/ffmpeg/choice').status_code == 401
    assert client.post('/api/ffmpeg/check').status_code == 401


def test_ffmpeg_status(session_client, machine):
    found = {
        'found': True,
        'path': str(machine.ffmpeg),
        'version': FFMPEG_VERSION,
        'chosen': False,
        'can_install': True,
        'installing': False,
        'error': None,
        'platform': PLATFORM,
    }
    assert session_client.get('/api/ffmpeg').json() == found

    machine.ffmpeg = machine.winget = None
    assert session_client.get('/api/ffmpeg').json() == found | {
        'found': False,
        'path': None,
        'version': None,
        'can_install': False,
    }


def test_installing_ffmpeg_brings_back_the_videos_that_waited_for_it(reader, machine, downloads, library, monkeypatch):
    machine.ffmpeg = None
    video_id = media_of(library, MediaKind.VIDEO).id
    reader.post(f'/api/media/{video_id}/download')
    wait_for_downloads(downloads)
    video = media_of(library, MediaKind.VIDEO)
    assert (video.state, video.error) == (MediaState.ERROR, 'no_ffmpeg')

    monkeypatch.setattr(kinescope, 'download', fake_video)
    machine.go.clear()
    started = reader.post('/api/ffmpeg/install').json()
    assert (started['installing'], started['found']) == (True, False)

    machine.go.set()
    installed = wait_for_install(reader)
    wait_for_downloads(downloads)

    assert (installed['found'], installed['path'], installed['error']) == (True, str(machine.ffmpeg), None)
    assert media_of(library, MediaKind.VIDEO).state is MediaState.DONE


def test_failed_install_is_told(session_client, machine):
    machine.ffmpeg = None
    machine.installs = 'fails'

    session_client.post('/api/ffmpeg/install')

    assert wait_for_install(session_client)['error'] == 'install_failed'


def test_install_without_winget(session_client, machine):
    machine.ffmpeg = machine.winget = None

    response = session_client.post('/api/ffmpeg/install')

    assert response.status_code == 409
    assert response.json() == {'code': 'no_winget'}


def test_user_points_at_their_ffmpeg(session_client, machine, program_picker, config_store):
    # The dialog was closed without a choice: nothing changes.
    assert session_client.post('/api/ffmpeg/choose').json()['chosen'] is False

    mine = machine.make_ffmpeg('mine/ffmpeg.exe')
    program_picker.choice = mine
    chosen = session_client.post('/api/ffmpeg/choose').json()

    assert (chosen['path'], chosen['chosen']) == (str(mine), True)
    assert config_store.load().ffmpeg_path == str(mine)

    forgotten = session_client.delete('/api/ffmpeg/choice').json()
    assert (forgotten['path'], forgotten['chosen']) == (str(machine.ffmpeg), False)


def test_the_path_to_ffmpeg_cannot_be_sent_by_the_page(session_client, machine, config_store):
    """Only the system's dialog names the file the app will run."""
    mine = machine.make_ffmpeg('mine/ffmpeg.exe')

    session_client.post('/api/ffmpeg/choose', json={'path': str(mine)})
    assert session_client.patch('/api/settings', json={'ffmpeg_path': str(mine)}).json().get('ffmpeg_path') is None

    assert config_store.load().ffmpeg_path is None


def test_a_file_that_is_not_ffmpeg_is_refused(session_client, machine, program_picker, tmp_path, config_store):
    program_picker.choice = tmp_path / 'ffmpeg.exe'
    program_picker.choice.write_bytes(b'something else')

    response = session_client.post('/api/ffmpeg/choose')

    assert response.status_code == 422
    assert response.json() == {'code': 'not_ffmpeg'}
    assert config_store.load().ffmpeg_path is None


def test_looking_again_brings_back_the_videos(reader, machine, downloads, library, monkeypatch):
    machine.ffmpeg = None
    reader.post(f'/api/media/{media_of(library, MediaKind.VIDEO).id}/download')
    wait_for_downloads(downloads)
    assert reader.post('/api/ffmpeg/check').json()['found'] is False
    assert media_of(library, MediaKind.VIDEO).state is MediaState.ERROR

    monkeypatch.setattr(kinescope, 'download', fake_video)
    machine.ffmpeg = machine.make_ffmpeg('by-hand/ffmpeg')

    assert reader.post('/api/ffmpeg/check').json()['found'] is True
    wait_for_downloads(downloads)
    assert media_of(library, MediaKind.VIDEO).state is MediaState.DONE
