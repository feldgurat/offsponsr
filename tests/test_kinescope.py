"""Kinescope: reading its manifests (on fixtures taken from sponsrdump) and downloading a video."""

import json
from pathlib import Path

import pytest
import requests

from offsponsr.media import files, kinescope
from offsponsr.media.files import DownloadCancelled, DownloadError
from offsponsr.media.kinescope import (
    Span,
    Stream,
    coalesce,
    download,
    parse_master,
    parse_media,
    parse_mpd,
    pick_stream,
    resolve,
)

FIXTURES = Path(__file__).parent / 'fixtures' / 'kinescope'
EMBED = 'https://kinescope.io/aBcDeFgHiJkLmNoPqRsTuV'
MASTER = (
    'https://kinescope.io/25df393d-09bf-43a3-b466-7d222c6ce9b9/master.m3u8?expires=1780640928&sign=7b17afd553c3c390'
)
CDN = 'https://edge-msk-1.kinescopecdn.net/videos/869b5dec/assets'


def fixture(name):
    return (FIXTURES / name).read_text(encoding='utf-8')


@pytest.fixture
def http():
    return requests.Session()


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(files, 'RETRY_DELAY', 0)


def test_master_playlist():
    streams, sound = parse_master(fixture('master.m3u8'), MASTER)

    assert [(stream.width, stream.height) for stream in streams] == [(1280, 720), (640, 360), (854, 480)]
    base = 'https://kinescope.io/25df393d-09bf-43a3-b466-7d222c6ce9b9/media.m3u8'
    assert streams[1].playlist_url == f'{base}?quality=360&type=video&sign=013765110b7d5e64&expires=1780640800'
    assert sound.playlist_url == f'{base}?quality=720&type=audio&lang=en&sign=013765110b7d5e64&expires=1780640800'


def test_master_playlist_without_sound():
    master = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=640x360\nmedia.m3u8\n'

    streams, sound = parse_master(master, MASTER)

    assert len(streams) == 1
    assert sound is None


def test_media_playlist():
    spans = parse_media(fixture('media_video.m3u8'), MASTER)

    init_url = f'{CDN}/019e7bce/360p.mp4?kinescope_project_id=d4e65216'
    segment_url = f'{init_url}&kcd=AAAAAABAr0A'
    assert spans == [
        Span(init_url, 0, 770),
        Span(segment_url, 771, 280269),
        Span(segment_url, 280270, 766793),
        Span(segment_url, 766794, 1310367),
    ]


def test_media_playlist_ranges_without_offsets_continue_one_another():
    media = '\n'.join(
        ['#EXTM3U', '#EXT-X-BYTERANGE:100@50', 'a.mp4', '#EXT-X-BYTERANGE:200', 'a.mp4', '#EXT-X-BYTERANGE:10', 'b.mp4']
    )

    assert parse_media(media, 'https://cdn.test/v/media.m3u8') == [
        Span('https://cdn.test/v/a.mp4', 50, 149),
        Span('https://cdn.test/v/a.mp4', 150, 349),
        Span('https://cdn.test/v/b.mp4', 0, 9),
    ]


def test_media_playlist_of_whole_files():
    media = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:4,\nseg1.m4s\n#EXTINF:4,\nseg2.m4s\n'

    assert parse_media(media, 'https://cdn.test/v/media.m3u8') == [
        Span('https://cdn.test/v/init.mp4'),
        Span('https://cdn.test/v/seg1.m4s'),
        Span('https://cdn.test/v/seg2.m4s'),
    ]


def test_dash_manifest():
    streams, sound = parse_mpd(fixture('some_mpd.xml'))

    assert [(stream.width, stream.height) for stream in streams] == [(852, 480), (1280, 720), (1920, 1080), (640, 360)]
    small = streams[0]
    assert small.playlist_url is None
    assert len(small.spans) == 4
    assert small.spans[0].url.endswith('/0/79028566/480p.mp4?kinescope_project_id=86eba8a9-f684-493b-a8e7-b80963caf355')
    assert (small.spans[0].first, small.spans[0].last) == (36, 794)
    assert (small.spans[1].first, small.spans[1].last) == (795, 606083)
    assert '&kcd=AAAAAABAr0A' in small.spans[1].url
    assert sound is not None
    assert all(span.first is not None for span in sound.spans)


def test_unreadable_dash_manifest():
    with pytest.raises(DownloadError) as raised:
        parse_mpd('<MPD><Period>')

    assert raised.value.code == 'player_changed'


def test_neighbouring_ranges_are_joined():
    spans = [
        Span('init', 0, 99),
        Span('a', 100, 199),
        Span('a', 200, 499),
        Span('a', 600, 699),  # A gap: not joined.
        Span('b', 700, 799),  # Another file.
        Span('b', 800, 899),
        Span('whole'),
        Span('whole'),
    ]

    assert coalesce(spans) == [
        Span('init', 0, 99),
        Span('a', 100, 499),
        Span('a', 600, 699),
        Span('b', 700, 899),
        Span('whole'),
        Span('whole'),
    ]


def test_joined_ranges_stay_under_the_limit():
    spans = [Span('a', start, start + 99) for start in range(0, 1000, 100)]

    assert coalesce(spans, max_span=300) == [
        Span('a', 0, 299),
        Span('a', 300, 599),
        Span('a', 600, 899),
        Span('a', 900, 999),
    ]


@pytest.mark.parametrize(
    ('max_height', 'expected'),
    [(None, 720), (1080, 720), (720, 720), (719, 480), (480, 480), (400, 360), (360, 360), (240, 360)],
)
def test_quality_choice(max_height, expected):
    streams = tuple(Stream(height, 0) for height in (360, 480, 720))

    assert pick_stream(streams, max_height).height == expected


def test_resolve_hls(sponsr, http):
    sponsr.routes[EMBED] = lambda request: (200, fixture('kinescope_embed.html'), [])
    sponsr.routes[MASTER] = lambda request: (200, fixture('master.m3u8'), [])

    video = resolve(http, EMBED)

    assert video.title == 'KZS_V_323.mp4'
    assert [stream.height for stream in video.streams] == [360, 480, 720]
    assert video.sound is not None
    embed_request, master_request = sponsr.requests
    assert embed_request.headers['Referer'] == 'https://sponsr.ru/'
    assert master_request.headers['Referer'] == 'https://kinescope.io/'


def test_resolve_dash(sponsr, http):
    mpd_url = (
        'https://kinescope.io/25df393d-09bf-43a3-b466-7d222c6ce9b9/master.mpd?expires=1780640928&sign=7b17afd553c3c390'
    )
    sponsr.routes[EMBED] = lambda request: (200, fixture('kinescope_embed_dash.html'), [])
    sponsr.routes[mpd_url] = lambda request: (200, fixture('some_mpd.xml'), [])

    video = resolve(http, EMBED)

    assert [stream.height for stream in video.streams] == [360, 480, 720, 1080]


@pytest.mark.parametrize(
    ('reply', 'code'),
    [
        ((200, fixture('kinescope_embed_nosource.html'), []), 'player_changed'),
        ((200, '<html>no player here</html>', []), 'player_changed'),
        ((200, '<script>var playerOptions = {"playlist": []};</script>', []), 'player_changed'),
        ((403, '<html>403</html>', []), 'forbidden'),
        ((404, '<html>404</html>', []), 'not_found'),
        ((502, '<html>502</html>', []), 'site_unavailable'),
    ],
)
def test_resolve_failures(sponsr, http, reply, code):
    sponsr.routes[EMBED] = lambda request: reply

    with pytest.raises(DownloadError) as raised:
        resolve(http, EMBED)

    assert raised.value.code == code


def test_resolve_when_kinescope_is_unreachable(http):
    with pytest.raises(DownloadError) as raised:
        resolve(http, EMBED)

    assert raised.value.code == 'site_unavailable'


class FakeVideo:
    """A made-up video on a made-up CDN: two qualities and a sound track, served in byte ranges."""

    MASTER = 'https://kinescope.io/video-id/master.m3u8?sign=1'

    def __init__(self, sponsr):
        self.files = {
            '360p': bytes([1]) * 1000 + bytes([2]) * 5000,
            '720p': bytes([3]) * 1000 + bytes([4]) * 9000,
            'sound': bytes([5]) * 500 + bytes([6]) * 2500,
        }
        self.ranges = {
            name: sponsr.serve_file(f'https://cdn.test/{name}.mp4', content) for name, content in self.files.items()
        }
        options = {'playlist': [{'title': 'Лекция.mp4', 'sources': {'hls': {'src': self.MASTER}}}]}
        sponsr.routes[EMBED] = lambda request: (200, f'<script>var playerOptions = {json.dumps(options)};</script>', [])
        master = '\n'.join(
            [
                '#EXTM3U',
                '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="x",URI="media.m3u8?type=audio"',
                '#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1280x720,AUDIO="a"',
                'media.m3u8?quality=720',
                '#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=640x360,AUDIO="a"',
                'media.m3u8?quality=360',
            ]
        )
        sponsr.routes[self.MASTER] = lambda request: (200, master, [])
        for query, name in (('quality=360', '360p'), ('quality=720', '720p'), ('type=audio', 'sound')):
            playlist = self.playlist(name)
            sponsr.routes[f'https://kinescope.io/video-id/media.m3u8?{query}'] = lambda request, text=playlist: (
                200,
                text,
                [],
            )

    def playlist(self, name):
        """An init segment and the rest in pieces of 1000 bytes, as byte ranges of one file."""
        size = len(self.files[name])
        init = 1000 if name != 'sound' else 500
        lines = ['#EXTM3U', f'#EXT-X-MAP:URI="https://cdn.test/{name}.mp4?init",BYTERANGE="{init}@0"']
        for start in range(init, size, 1000):
            length = min(1000, size - start)
            lines += ['#EXTINF:4,', f'#EXT-X-BYTERANGE:{length}@{start}', f'https://cdn.test/{name}.mp4?kcd=1']
        return '\n'.join(lines)


@pytest.fixture
def fake_video(sponsr):
    return FakeVideo(sponsr)


@pytest.fixture
def fake_mux(monkeypatch):
    """Instead of ffmpeg: the output is the inputs one after another."""
    calls = []

    def mux(ffmpeg, inputs, dest):
        calls.append((ffmpeg, [source.name for source in inputs]))
        dest.write_bytes(b''.join(source.read_bytes() for source in inputs))

    monkeypatch.setattr(kinescope, 'mux', mux)
    return calls


def test_download_best_quality(http, tmp_path, fake_video, fake_mux):
    work = tmp_path / 'tmp'
    work.mkdir()
    dest = tmp_path / 'library' / 'video' / 'Лекция.mp4'
    progress = []

    stream = download(
        http, EMBED, dest, work_dir=work, work_name='media-7', ffmpeg=Path('ffmpeg'),
        on_progress=lambda done, total: progress.append((done, total)),
    )  # fmt: skip

    assert stream.height == 720
    assert dest.read_bytes() == fake_video.files['720p'] + fake_video.files['sound']
    assert fake_mux == [(Path('ffmpeg'), ['media-7.video', 'media-7.sound'])]
    # The init segment on its own, then everything else in one request: the ranges follow one another.
    assert fake_video.ranges['720p'] == ['bytes=0-999', 'bytes=1000-9999']
    assert fake_video.ranges['sound'] == ['bytes=0-499', 'bytes=500-2999']
    assert fake_video.ranges['360p'] == []
    total = len(fake_video.files['720p']) + len(fake_video.files['sound'])
    assert progress[-1] == (total, total)
    assert all(done <= total for done, total in progress)
    # Nothing is left in the work folder.
    assert list(work.iterdir()) == []


def test_download_with_a_quality_limit(http, tmp_path, fake_video, fake_mux):
    dest = tmp_path / 'out.mp4'

    stream = download(http, EMBED, dest, work_dir=tmp_path, work_name='m', ffmpeg=Path('ffmpeg'), max_height=480)

    assert stream.height == 360
    assert dest.read_bytes() == fake_video.files['360p'] + fake_video.files['sound']


def test_interrupted_download_continues(http, tmp_path, fake_video, fake_mux, monkeypatch):
    # Small requests, so the video is several of them and can be stopped in the middle.
    monkeypatch.setattr(kinescope, 'MAX_SPAN', 3000)
    dest = tmp_path / 'out.mp4'
    progress = []

    with pytest.raises(DownloadCancelled):
        download(
            http, EMBED, dest, work_dir=tmp_path, work_name='m', ffmpeg=Path('ffmpeg'),
            on_progress=lambda done, total: progress.append(done),
            should_stop=lambda: bool(progress) and progress[-1] >= 4000,
        )  # fmt: skip

    assert not dest.exists()
    assert fake_mux == []
    assert fake_video.ranges['720p'] == ['bytes=0-999', 'bytes=1000-3999']
    assert (tmp_path / 'm.video').stat().st_size == 4000
    fake_video.ranges['720p'].clear()
    progress.clear()

    download(
        http, EMBED, dest, work_dir=tmp_path, work_name='m', ffmpeg=Path('ffmpeg'),
        on_progress=lambda done, total: progress.append(done),
    )  # fmt: skip

    # Only what was missing is asked for, and the progress starts from what was there.
    assert fake_video.ranges['720p'] == ['bytes=4000-6999', 'bytes=7000-9999']
    assert progress[0] == 4000
    assert dest.read_bytes() == fake_video.files['720p'] + fake_video.files['sound']


def test_span_that_was_cut_short_is_fetched_again(http, tmp_path, fake_video, fake_mux, monkeypatch):
    monkeypatch.setattr(kinescope, 'MAX_SPAN', 3000)
    # As after a crash: the file is longer than the progress note says, by a part of the next span.
    (tmp_path / 'm.video').write_bytes(fake_video.files['720p'][:4000] + b'half a span')
    (tmp_path / 'm.video.progress').write_text(json.dumps({'spans': 2, 'size': 4000}), encoding='utf-8')
    dest = tmp_path / 'out.mp4'

    download(http, EMBED, dest, work_dir=tmp_path, work_name='m', ffmpeg=Path('ffmpeg'))

    assert fake_video.ranges['720p'] == ['bytes=4000-6999', 'bytes=7000-9999']
    assert dest.read_bytes() == fake_video.files['720p'] + fake_video.files['sound']


def test_video_without_a_sound_track(http, tmp_path, fake_video, fake_mux, sponsr):
    master = '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=640x360\nmedia.m3u8?quality=360\n'
    sponsr.routes[FakeVideo.MASTER] = lambda request: (200, master, [])
    dest = tmp_path / 'out.mp4'

    download(http, EMBED, dest, work_dir=tmp_path, work_name='m', ffmpeg=Path('ffmpeg'))

    assert dest.read_bytes() == fake_video.files['360p']
    assert fake_mux == [(Path('ffmpeg'), ['m.video'])]


def test_failed_segment_fails_the_download(http, tmp_path, fake_video, fake_mux, sponsr):
    sponsr.patterns.append(('https://cdn.test/720p.mp4?kcd=1', lambda request: (403, b'', [])))

    with pytest.raises(DownloadError) as raised:
        download(http, EMBED, tmp_path / 'out.mp4', work_dir=tmp_path, work_name='m', ffmpeg=Path('ffmpeg'))

    assert raised.value.code == 'forbidden'
    assert fake_mux == []
