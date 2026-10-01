"""Getting an ffmpeg: what the app finds, what the user points at, what winget installs."""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from offsponsr.media import ffmpeg, ffmpeg_setup
from offsponsr.media.ffmpeg import ffmpeg_version
from offsponsr.media.ffmpeg_setup import (
    INSTALL_TIMEOUT,
    PLATFORM,
    WINGET_PACKAGE,
    FfmpegSetup,
    FfmpegSetupError,
    find_winget,
    install_command,
    run_winget,
)

from .fakes import FFMPEG_VERSION


def wait_for_install(setup, timeout=10):
    deadline = time.monotonic() + timeout
    while setup.state().installing:
        assert time.monotonic() < deadline, 'The installation did not finish in time'
        time.sleep(0.01)


def events_of(listener):
    events = []
    while (event := listener.get(0)) is not None:
        events.append(event)
    return events


@pytest.fixture
def ready(ffmpeg_setup):
    """How many times the setup said that there is an ffmpeg to work with."""
    calls = []
    ffmpeg_setup.when_ready(lambda: calls.append(1))
    return calls


def test_state_tells_what_was_found(ffmpeg_setup, machine):
    assert ffmpeg_setup.path() == machine.ffmpeg
    assert ffmpeg_setup.state().to_json() == {
        'found': True,
        'path': str(machine.ffmpeg),
        'version': FFMPEG_VERSION,
        'chosen': False,
        'can_install': True,
        'installing': False,
        'error': None,
        'platform': PLATFORM,
    }


def test_state_of_a_machine_with_nothing(ffmpeg_setup, machine):
    machine.ffmpeg = machine.winget = None

    assert ffmpeg_setup.path() is None
    assert ffmpeg_setup.state().to_json() == {
        'found': False,
        'path': None,
        'version': None,
        'chosen': False,
        'can_install': False,
        'installing': False,
        'error': None,
        'platform': PLATFORM,
    }


def test_version_is_asked_once_per_file(config_store, events, machine):
    asked = []

    def version(path):
        asked.append(path)
        return machine.version(path)

    setup = FfmpegSetup(config_store, events, find=machine.find, version=version, winget=machine.find_winget)

    assert [setup.state().version for _ in range(3)] == [FFMPEG_VERSION] * 3
    assert asked == [machine.ffmpeg]

    # Another file is another question.
    machine.ffmpeg = machine.make_ffmpeg('newer/ffmpeg')
    setup.state()
    assert asked[1:] == [machine.ffmpeg]


def test_install_puts_an_ffmpeg_in_place(ffmpeg_setup, machine, events, ready):
    machine.ffmpeg = None
    listener = events.subscribe()
    machine.go.clear()

    started = ffmpeg_setup.install()
    assert (started.installing, started.path) == (True, None)
    # Asking again while winget is at it starts nothing new.
    assert ffmpeg_setup.install().installing

    machine.go.set()
    wait_for_install(ffmpeg_setup)

    assert machine.runs == [machine.winget]
    state = ffmpeg_setup.state()
    assert (state.path, state.version, state.error) == (machine.ffmpeg, FFMPEG_VERSION, None)
    assert machine.ffmpeg is not None
    assert ready == [1]
    told = [(event['state']['installing'], event['state']['found']) for event in events_of(listener)]
    assert told == [(True, False), (False, True)]


def test_failed_install_is_reported(ffmpeg_setup, machine, ready):
    machine.ffmpeg = None
    machine.installs = 'fails'

    ffmpeg_setup.install()
    wait_for_install(ffmpeg_setup)

    state = ffmpeg_setup.state()
    assert (state.path, state.error) == (None, 'install_failed')
    assert ready == []

    # The next try starts with a clean slate.
    machine.installs = 'ok'
    assert ffmpeg_setup.install().error is None
    wait_for_install(ffmpeg_setup)
    assert ffmpeg_setup.state().error is None


def test_install_that_takes_too_long_is_reported(ffmpeg_setup, machine):
    machine.ffmpeg = None
    machine.installs = 'hangs'

    ffmpeg_setup.install()
    wait_for_install(ffmpeg_setup)

    assert ffmpeg_setup.state().error == 'install_timeout'


def test_winget_that_does_not_start_is_reported(config_store, events, machine):
    machine.ffmpeg = None

    def run(winget):
        raise OSError('no such program')

    setup = FfmpegSetup(config_store, events, find=machine.find, winget=machine.find_winget, run=run)
    setup.install()
    wait_for_install(setup)

    assert setup.state().error == 'install_failed'


def test_what_counts_is_whether_ffmpeg_is_found_not_what_winget_said(config_store, events, machine):
    machine.ffmpeg = None

    def run(winget):
        # winget ends with an error when the package is installed already.
        machine.ffmpeg = machine.make_ffmpeg('already/ffmpeg.exe')
        return 0x8A150061

    setup = FfmpegSetup(
        config_store, events, find=machine.find, version=machine.version, winget=machine.find_winget, run=run
    )
    setup.install()
    wait_for_install(setup)

    state = setup.state()
    assert (state.path, state.error) == (machine.ffmpeg, None)


def test_install_needs_winget(ffmpeg_setup, machine):
    machine.winget = None

    with pytest.raises(FfmpegSetupError) as failure:
        ffmpeg_setup.install()

    assert failure.value.code == 'no_winget'
    assert machine.runs == []


def test_an_installation_that_ends_after_the_app_closed_starts_nothing(ffmpeg_setup, machine, ready):
    machine.ffmpeg = None
    machine.go.clear()
    ffmpeg_setup.install()

    ffmpeg_setup.shutdown()
    machine.go.set()
    wait_for_install(ffmpeg_setup)

    assert ready == []


def test_user_points_at_their_ffmpeg(ffmpeg_setup, machine, config_store, events, ready):
    mine = machine.make_ffmpeg('mine/FFmpeg.exe')
    listener = events.subscribe()

    state = ffmpeg_setup.choose(mine)

    assert (state.path, state.chosen) == (mine, True)
    assert config_store.load().ffmpeg_path == str(mine)
    assert ffmpeg_setup.path() == mine
    assert ready == [1]
    [event] = events_of(listener)
    assert (event['type'], event['state']['path']) == ('ffmpeg', str(mine))


def test_only_an_ffmpeg_can_be_pointed_at(config_store, events, machine, tmp_path):
    asked = []

    def version(path):
        asked.append(path)
        return machine.version(path)

    setup = FfmpegSetup(config_store, events, find=machine.find, version=version)
    # Something else under a name that is not ffmpeg's is not even run.
    other = machine.make_ffmpeg('mine/setup.exe')
    impostor = tmp_path / 'ffmpeg.exe'
    impostor.write_bytes(b'something else')

    for path in (other, impostor, tmp_path / 'gone' / 'ffmpeg.exe'):
        with pytest.raises(FfmpegSetupError) as failure:
            setup.choose(path)
        assert failure.value.code == 'not_ffmpeg'

    assert asked == [impostor]
    assert config_store.load().ffmpeg_path is None


def test_the_choice_can_be_taken_back(ffmpeg_setup, machine, config_store):
    ffmpeg_setup.choose(machine.make_ffmpeg('mine/ffmpeg'))

    state = ffmpeg_setup.forget_choice()

    assert (state.path, state.chosen) == (machine.ffmpeg, False)
    assert config_store.load().ffmpeg_path is None


def test_a_chosen_ffmpeg_that_is_gone_gives_way_to_the_found_one(ffmpeg_setup, machine):
    mine = machine.make_ffmpeg('mine/ffmpeg')
    ffmpeg_setup.choose(mine)
    mine.unlink()

    state = ffmpeg_setup.state()

    assert (state.path, state.chosen) == (machine.ffmpeg, False)


def test_looking_again_tells_that_ffmpeg_has_turned_up(ffmpeg_setup, machine, ready):
    machine.ffmpeg = None
    assert ffmpeg_setup.check().path is None
    assert ready == []

    # The user has installed one by their own means.
    machine.ffmpeg = machine.make_ffmpeg('by-hand/ffmpeg')

    assert ffmpeg_setup.check().path == machine.ffmpeg
    assert ready == [1]


def test_winget_command():
    command = install_command(Path('winget.exe'))

    assert command[:4] == ['winget.exe', 'install', '--id', WINGET_PACKAGE]
    assert {'--exact', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity'} < set(
        command
    )
    assert command[command.index('--source') + 1] == 'winget'


def test_winget_runs_without_a_shell_and_not_forever(monkeypatch):
    calls = []

    def run(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(command, 1, b'No package found', b'')

    monkeypatch.setattr(ffmpeg_setup.subprocess, 'run', run)

    assert run_winget(Path('winget.exe')) == 1

    [(command, options)] = calls
    assert command == install_command(Path('winget.exe'))
    assert 'shell' not in options
    assert options['timeout'] == INSTALL_TIMEOUT
    assert options['stdin'] == subprocess.DEVNULL


def test_winget_is_looked_for_on_windows_only(monkeypatch):
    monkeypatch.setattr(ffmpeg_setup.shutil, 'which', lambda name: f'somewhere/{name}.exe')

    assert find_winget() == (Path('somewhere/winget.exe') if sys.platform == 'win32' else None)

    monkeypatch.setattr(ffmpeg_setup.shutil, 'which', lambda name: None)
    assert find_winget() is None


def test_version_is_what_ffmpeg_says(monkeypatch):
    calls = []

    def run(command, **options):
        calls.append((command, options))
        said = b'ffmpeg version 9.0.2-essentials_build-www.gyan.dev Copyright (c) 2000-2026 the FFmpeg developers\n'
        return subprocess.CompletedProcess(command, 0, said, b'')

    monkeypatch.setattr(ffmpeg.subprocess, 'run', run)

    assert ffmpeg_version(Path('ffmpeg')) == '9.0.2-essentials_build-www.gyan.dev'
    [(command, options)] = calls
    assert command == ['ffmpeg', '-version']
    assert 'shell' not in options
    assert options['timeout'] == ffmpeg.VERSION_TIMEOUT


@pytest.mark.parametrize(
    'outcome',
    [
        subprocess.CompletedProcess([], 0, b'Usage: setup [options]', b''),
        OSError('not a program'),
        subprocess.TimeoutExpired('ffmpeg', 1),
    ],
)
def test_what_does_not_answer_like_ffmpeg_has_no_version(monkeypatch, outcome):
    def run(command, **options):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(ffmpeg.subprocess, 'run', run)

    assert ffmpeg_version(Path('ffmpeg')) is None
