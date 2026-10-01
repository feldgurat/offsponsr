"""The small parts of the downloader: names and folders, one file with resume, ffmpeg."""

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest
import requests

from offsponsr.config import CONFIG_DIR_ENV
from offsponsr.library.paths import (
    MAX_MEDIA_NAME_CHARS,
    MAX_POST_FOLDER_CHARS,
    long_path,
    post_folder,
    project_assets_folder,
    safe_name,
    truncate_filename,
    unique_name,
)
from offsponsr.media import ffmpeg, files
from offsponsr.media.ffmpeg import FfmpegError, find_ffmpeg, mux
from offsponsr.media.files import DownloadCancelled, DownloadError, fetch

URL = 'https://media.sponsr.ru/some/file.bin'
CONTENT = bytes(range(256)) * 40  # 10240 bytes, every position tellable from its neighbours


@pytest.fixture
def http():
    return requests.Session()


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(files, 'RETRY_DELAY', 0)


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        ('Обычное название', 'Обычное название'),
        ('Что? Где: "когда"/*', 'Что_ Где_ _когда___'),
        ('a<b>c|d\\e', 'a_b_c_d_e'),
        ('  много   пробелов\tи\nпереносов  ', 'много пробелов и переносов'),
        ('Заканчивается точкой...', 'Заканчивается точкой'),
        ('CON', '_CON'),
        ('nul.txt', '_nul.txt'),
        ('COM1.backup.zip', '_COM1.backup.zip'),
        ('console', 'console'),
        ('', '_'),
        ('...', '_'),
        ('с\x00управляющими\x07символами', 'с_управляющими_символами'),
    ],
)
def test_safe_name(name, expected):
    assert safe_name(name) == expected


def test_safe_name_is_cut_by_bytes_and_keeps_the_extension():
    name = safe_name('я' * 300 + '.mp3')

    assert name.endswith('.mp3')
    assert len(name.encode()) <= 255
    assert name.startswith('я' * 100)


def test_cut_never_splits_a_letter_or_leaves_a_trailing_space():
    assert truncate_filename('привет', 5) == 'пр'
    assert safe_name('ab ' + 'я' * 10, 3) == 'ab'
    assert truncate_filename('short.txt', 255) == 'short.txt'


@pytest.mark.parametrize(
    ('name', 'taken', 'expected'),
    [
        ('a.mp3', set(), 'a.mp3'),
        ('a.mp3', {'a.mp3'}, 'a (2).mp3'),
        ('A.mp3', {'a.mp3', 'a (2).mp3'}, 'A (3).mp3'),
        ('без расширения', {'без расширения'}, 'без расширения (2)'),
    ],
)
def test_unique_name(name, taken, expected):
    assert unique_name(name, taken) == expected


def test_post_folder():
    # 21:30 UTC is already the next day by the site's clock.
    folder = post_folder(
        'some-project', 185607, datetime(2026, 9, 29, 21, 30, tzinfo=UTC), 'Между: Вьетнамом и Турцией?'
    )

    assert folder == PurePosixPath('projects/some-project/2026-09-30 [185607] Между_ Вьетнамом и Турцией_')
    assert project_assets_folder('some-project') == PurePosixPath('projects/some-project/_project')


def test_post_folder_name_stays_short():
    folder = post_folder('p', 1, datetime(2026, 1, 1, tzinfo=UTC), 'Очень длинное название. ' * 30)

    assert len(folder.name) <= MAX_POST_FOLDER_CHARS
    assert folder.name.startswith('2026-01-01 [1] Очень длинное')
    assert not folder.name.endswith((' ', '.'))


def test_long_names_are_cut_by_characters_and_keep_the_extension():
    name = safe_name('Очень длинное название видео. ' * 10 + '.mp4', MAX_MEDIA_NAME_CHARS)

    assert len(name) <= MAX_MEDIA_NAME_CHARS
    assert name.endswith('.mp4')
    assert name.startswith('Очень длинное название видео')
    assert safe_name('короткое.mp4', MAX_MEDIA_NAME_CHARS) == 'короткое.mp4'


@pytest.mark.skipif(sys.platform != 'win32', reason='only Windows limits the length of a path')
def test_files_can_be_written_however_deep_the_library_sits(tmp_path):
    deep = tmp_path.joinpath(*['очень-глубокая-папка'] * 14)
    assert len(str(deep)) > 260
    target = long_path(deep / 'file.txt')

    target.parent.mkdir(parents=True)
    target.write_text('written', encoding='utf-8')
    moved = long_path(deep / 'moved.txt')
    target.replace(moved)

    assert moved.read_text(encoding='utf-8') == 'written'
    assert moved.stat().st_size == 7
    # A short path is left as it is.
    assert long_path(tmp_path / 'short.txt') == tmp_path / 'short.txt'


def test_fetch_whole_file(sponsr, http, tmp_path):
    ranges = sponsr.serve_file(URL, CONTENT)
    seen = []

    size = fetch(http, URL, tmp_path / 'f.part', on_bytes=seen.append)

    assert size == len(CONTENT)
    assert (tmp_path / 'f.part').read_bytes() == CONTENT
    assert sum(seen) == len(CONTENT)
    assert ranges == [None]


def test_fetch_continues_a_partial_file(sponsr, http, tmp_path):
    ranges = sponsr.serve_file(URL, CONTENT)
    part = tmp_path / 'f.part'
    part.write_bytes(CONTENT[:4000])
    seen = []

    fetch(http, URL, part, on_bytes=seen.append)

    assert part.read_bytes() == CONTENT
    assert ranges == ['bytes=4000-']
    assert sum(seen) == len(CONTENT) - 4000


def test_fetch_of_a_file_that_is_already_whole(sponsr, http, tmp_path):
    ranges = sponsr.serve_file(URL, CONTENT)
    part = tmp_path / 'f.part'
    part.write_bytes(CONTENT)

    assert fetch(http, URL, part) == len(CONTENT)
    assert part.read_bytes() == CONTENT
    assert ranges == [f'bytes={len(CONTENT)}-']


def test_fetch_starts_over_when_the_partial_file_is_longer_than_the_real_one(sponsr, http, tmp_path):
    sponsr.serve_file(URL, CONTENT)
    part = tmp_path / 'f.part'
    part.write_bytes(CONTENT + b'leftover from another file')

    fetch(http, URL, part)

    assert part.read_bytes() == CONTENT


def test_fetch_starts_over_when_the_server_ignores_the_range(sponsr, http, tmp_path):
    sponsr.patterns.append((URL, lambda request: (200, CONTENT, [], {'Content-Length': str(len(CONTENT))})))
    part = tmp_path / 'f.part'
    part.write_bytes(b'stale')

    fetch(http, URL, part)

    assert part.read_bytes() == CONTENT


def test_fetch_a_span(sponsr, http, tmp_path):
    ranges = sponsr.serve_file(URL, CONTENT)
    part = tmp_path / 'f.part'

    size = fetch(http, URL, part, first_byte=1000, last_byte=2999)

    assert size == 2000
    assert part.read_bytes() == CONTENT[1000:3000]
    assert ranges == ['bytes=1000-2999']

    # And the rest of a span that was cut short.
    part.write_bytes(CONTENT[1000:1500])
    fetch(http, URL, part, first_byte=1000, last_byte=2999)

    assert part.read_bytes() == CONTENT[1000:3000]
    assert ranges[-1] == 'bytes=1500-2999'


def test_fetch_sends_the_given_headers(sponsr, http, tmp_path):
    sponsr.serve_file(URL, CONTENT)

    fetch(http, URL, tmp_path / 'f.part', headers={'Referer': 'https://kinescope.io/'})

    assert sponsr.requests[-1].headers['Referer'] == 'https://kinescope.io/'


def test_fetch_retries_a_dropped_connection_and_continues(sponsr, http, tmp_path, monkeypatch):
    # Small blocks, so that some of the file is on disk by the time the connection drops.
    monkeypatch.setattr(files, 'BLOCK', 1000)
    ranges = sponsr.serve_file(URL, CONTENT)
    usual = sponsr.patterns[-1][1]
    calls = []

    def flaky(request):
        calls.append(request)
        if len(calls) == 1:
            # Promise the whole file, deliver a part of it, as a connection that drops does.
            return 200, CONTENT[:3000], [], {'Content-Length': str(len(CONTENT))}
        return usual(request)

    sponsr.patterns[-1] = (URL, flaky)
    part = tmp_path / 'f.part'

    fetch(http, URL, part)

    assert part.read_bytes() == CONTENT
    assert ranges == ['bytes=3000-']


def test_fetch_gives_up_on_a_connection_that_keeps_dropping(sponsr, http, tmp_path):
    def dead(request):
        raise requests.ConnectionError('reset')

    sponsr.patterns.append((URL, dead))

    with pytest.raises(DownloadError) as raised:
        fetch(http, URL, tmp_path / 'f.part')

    assert raised.value.code == 'site_unavailable'
    assert len(sponsr.requests) == files.RETRIES + 1


@pytest.mark.parametrize(('status', 'code'), [(403, 'forbidden'), (404, 'not_found'), (500, 'site_unavailable')])
def test_fetch_refused(sponsr, http, tmp_path, status, code):
    sponsr.patterns.append((URL, lambda request: (status, b'', [])))

    with pytest.raises(DownloadError) as raised:
        fetch(http, URL, tmp_path / 'f.part')

    assert raised.value.code == code
    assert not (tmp_path / 'f.part').exists()


def test_fetch_can_be_stopped_and_keeps_what_it_got(sponsr, http, tmp_path, monkeypatch):
    monkeypatch.setattr(files, 'BLOCK', 1000)
    sponsr.serve_file(URL, CONTENT)
    part = tmp_path / 'f.part'
    blocks = []

    with pytest.raises(DownloadCancelled):
        fetch(http, URL, part, on_bytes=blocks.append, should_stop=lambda: len(blocks) >= 3)

    assert part.read_bytes() == CONTENT[:3000]


def test_find_ffmpeg_prefers_the_setting(tmp_path, monkeypatch):
    configured = tmp_path / 'my-ffmpeg'
    configured.write_bytes(b'')
    monkeypatch.setattr(ffmpeg.shutil, 'which', lambda name: str(tmp_path / 'system-ffmpeg'))

    assert find_ffmpeg(str(configured)) == configured
    # A setting that points nowhere is passed over.
    assert find_ffmpeg(str(tmp_path / 'gone')) == tmp_path / 'system-ffmpeg'


def test_find_ffmpeg_falls_back_to_the_apps_own(tmp_path, monkeypatch):
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))
    monkeypatch.setattr(ffmpeg.shutil, 'which', lambda name: None)

    assert find_ffmpeg() is None

    own = tmp_path / 'ffmpeg' / ffmpeg.EXECUTABLE
    own.parent.mkdir()
    own.write_bytes(b'')

    assert find_ffmpeg() == own


def test_mux_runs_ffmpeg_without_a_shell(tmp_path, monkeypatch):
    calls = []

    def run(command, **options):
        calls.append((command, options))
        Path(command[-1]).write_bytes(b'muxed')
        return subprocess.CompletedProcess(command, 0, b'', b'')

    monkeypatch.setattr(ffmpeg.subprocess, 'run', run)
    video, sound, dest = tmp_path / 'в идео.video', tmp_path / 'sound', tmp_path / 'out file.mp4'

    mux(Path('ffmpeg'), [video, sound], dest)

    [(command, options)] = calls
    assert command == [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
        '-i', str(video), '-i', str(sound),
        '-c', 'copy', '-movflags', '+faststart', '-f', 'mp4', str(dest),
    ]  # fmt: skip
    assert 'shell' not in options
    assert dest.read_bytes() == b'muxed'


def test_mux_failure_reports_what_ffmpeg_said_and_leaves_no_file(tmp_path, monkeypatch):
    def run(command, **options):
        Path(command[-1]).write_bytes(b'half')
        return subprocess.CompletedProcess(command, 1, b'', b'Invalid data found when processing input')

    monkeypatch.setattr(ffmpeg.subprocess, 'run', run)
    dest = tmp_path / 'out.mp4'

    with pytest.raises(FfmpegError, match='Invalid data found'):
        mux(Path('ffmpeg'), [tmp_path / 'v'], dest)

    assert not dest.exists()
