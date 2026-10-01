"""Downloads a video from Kinescope, the player sponsr.ru embeds.

The way in — embed page, `playerOptions`, signed HLS or DASH manifest, byte-range segments,
ffmpeg to join picture and sound — is ported from sponsrdump (BSD-3-Clause, © Igor Starikov).
What is new here: only the wanted quality's playlist is fetched, neighbouring byte ranges are
asked for in one request, and an interrupted download picks up where it stopped.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests

from offsponsr.media.ffmpeg import mux
from offsponsr.media.files import DownloadCancelled, DownloadError, fetch

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

log = logging.getLogger(__name__)

SPONSR_REFERER = 'https://sponsr.ru/'
KINESCOPE_REFERER = 'https://kinescope.io/'
TIMEOUT = (10, 60)

# Neighbouring byte ranges of one file are fetched together, up to this many bytes a request.
# It is also the most an interrupted download has to fetch again.
MAX_SPAN = 16 * 1024 * 1024

_PLAYER_OPTIONS = re.compile(r'var playerOptions\s*=\s*(\{.*?\});', re.DOTALL)
_HLS_STREAM = re.compile(r'#EXT-X-STREAM-INF:[^\n]*?RESOLUTION=(\d+)x(\d+)[^\n]*\n([^\n#][^\n]*)')
_HLS_AUDIO = re.compile(r'#EXT-X-MEDIA:TYPE=AUDIO[^\n]*?URI="([^"]+)"')
_HLS_MAP = re.compile(r'#EXT-X-MAP:URI="([^"]+)"(?:,BYTERANGE="(\d+)(?:@(\d+))?")?')
_HLS_BYTERANGE = re.compile(r'#EXT-X-BYTERANGE:(\d+)(?:@(\d+))?')
_XML_NAMESPACE = re.compile(r'xmlns(:[^=]*)?="[^"]+"')


@dataclass(frozen=True)
class Span:
    """A piece of a file to download: bytes `first..last` of `url`, or all of it if `first` is None."""

    url: str
    first: int | None = None
    last: int | None = None

    @property
    def size(self) -> int | None:
        return None if self.first is None or self.last is None else self.last - self.first + 1


@dataclass(frozen=True)
class Stream:
    """One quality of a video (or its sound, with no height) and where its playlist is."""

    height: int
    width: int
    # An HLS media playlist to fetch; None when the spans came with the manifest (DASH).
    playlist_url: str | None = None
    spans: tuple[Span, ...] = ()


@dataclass(frozen=True)
class Video:
    title: str | None
    # Qualities, lowest first.
    streams: tuple[Stream, ...]
    sound: Stream | None


def _get(http: requests.Session, url: str, referer: str) -> str:
    try:
        response = http.get(url, headers={'Referer': referer}, timeout=TIMEOUT)
    except requests.RequestException as error:
        raise DownloadError('site_unavailable', str(error)) from error
    if response.status_code in (401, 403):
        raise DownloadError('forbidden', f'HTTP {response.status_code}')
    if response.status_code == 404:
        raise DownloadError('not_found', 'HTTP 404')
    if not response.ok:
        raise DownloadError('site_unavailable', f'HTTP {response.status_code}')
    return response.text


def resolve(http: requests.Session, embed_url: str) -> Video:
    """Find out what a Kinescope embed (`https://kinescope.io/<id>`) offers."""
    page = _get(http, embed_url, SPONSR_REFERER)
    found = _PLAYER_OPTIONS.search(page)
    if not found:
        raise DownloadError('player_changed', 'no player options on the embed page')
    try:
        item = json.loads(found.group(1))['playlist'][0]
        sources = item['sources']
    except (ValueError, KeyError, IndexError, TypeError):
        raise DownloadError('player_changed', 'unreadable player options') from None

    title = item.get('title') if isinstance(item.get('title'), str) else None
    if hls_url := (sources.get('hls') or {}).get('src'):
        streams, sound = parse_master(_get(http, hls_url, KINESCOPE_REFERER), hls_url)
    elif dash_url := (sources.get('dash') or {}).get('src'):
        streams, sound = parse_mpd(_get(http, dash_url, KINESCOPE_REFERER))
    else:
        raise DownloadError('player_changed', 'neither HLS nor DASH among the sources')
    if not streams:
        raise DownloadError('player_changed', 'no video streams in the manifest')
    return Video(title=title, streams=tuple(sorted(streams, key=lambda stream: stream.height)), sound=sound)


def parse_master(master: str, master_url: str) -> tuple[list[Stream], Stream | None]:
    """The qualities and the sound track an HLS master playlist lists."""
    streams = [
        Stream(height=int(height), width=int(width), playlist_url=urljoin(master_url, playlist.strip()))
        for width, height, playlist in _HLS_STREAM.findall(master)
    ]
    sound_urls = _HLS_AUDIO.findall(master)
    sound = Stream(height=0, width=0, playlist_url=urljoin(master_url, sound_urls[0].strip())) if sound_urls else None
    return streams, sound


def parse_media(media: str, media_url: str) -> list[Span]:
    """The pieces an HLS media playlist is made of, the init segment first."""
    spans: list[Span] = []
    # Where the previous range of each file ended: a BYTERANGE without an offset continues from there.
    cursors: dict[str, int] = {}

    def span(url: str, length: str | None, offset: str | None) -> Span:
        if length is None:
            return Span(url)
        first = int(offset) if offset is not None else cursors.get(url, 0)
        last = first + int(length) - 1
        cursors[url] = last + 1
        return Span(url, first, last)

    if init := _HLS_MAP.search(media):
        spans.append(span(urljoin(media_url, init.group(1)), init.group(2), init.group(3)))

    pending: tuple[str, str | None] | None = None
    for raw_line in media.splitlines():
        line = raw_line.strip()
        if byterange := _HLS_BYTERANGE.match(line):
            pending = (byterange.group(1), byterange.group(2))
        elif line and not line.startswith('#'):
            url = urljoin(media_url, line)
            spans.append(span(url, *pending) if pending else Span(url))
            pending = None
    return spans


def parse_mpd(xml: str) -> tuple[list[Stream], Stream | None]:
    """The same from a DASH manifest, which lists the pieces of every quality itself."""
    try:
        root = ET.fromstring(_XML_NAMESPACE.sub('', xml))
    except ET.ParseError:
        raise DownloadError('player_changed', 'unreadable DASH manifest') from None

    streams: list[Stream] = []
    sounds: list[tuple[int, Stream]] = []
    for adaptation in root.iter('AdaptationSet'):
        mime = adaptation.get('mimeType', '')
        for representation in adaptation.findall('Representation'):
            base = (representation.findtext('BaseURL') or '').strip()
            spans: list[Span] = []
            segments = representation.find('SegmentList')
            for segment in segments if segments is not None else ():
                name = segment.get('sourceURL') or segment.get('media')
                byte_range = segment.get('range') or segment.get('mediaRange')
                # A range without a file name is a range of the base URL itself (typical for sound).
                url = f'{base}{name}' if name else base
                if not url:
                    continue
                if byte_range and '-' in byte_range:
                    first, _, last = byte_range.partition('-')
                    spans.append(Span(url, int(first), int(last)))
                else:
                    spans.append(Span(url))
            if mime.startswith('video'):
                height = int(representation.get('height', 0))
                streams.append(Stream(height, int(representation.get('width', 0)), spans=tuple(spans)))
            elif mime.startswith('audio'):
                rate = int(representation.get('audioSamplingRate', 0))
                sounds.append((rate, Stream(0, 0, spans=tuple(spans))))
    # The best sound there is: it costs little next to the picture.
    sound = max(sounds, key=lambda item: item[0])[1] if sounds else None
    return streams, sound


def pick_stream(streams: tuple[Stream, ...], max_height: int | None) -> Stream:
    """The best quality, or the best one not taller than `max_height`; the smallest if all are taller."""
    if max_height is not None:
        fitting = [stream for stream in streams if stream.height <= max_height]
        return fitting[-1] if fitting else streams[0]
    return streams[-1]


def coalesce(spans: list[Span], max_span: int | None = None) -> list[Span]:
    """Join byte ranges that follow one another in the same file into fewer, bigger requests."""
    max_span = MAX_SPAN if max_span is None else max_span
    joined: list[Span] = []
    for span in spans:
        previous = joined[-1] if joined else None
        if (
            previous is not None
            and previous.url == span.url
            and previous.last is not None
            and span.first == previous.last + 1
            and span.last is not None
            and previous.first is not None
            and span.last - previous.first + 1 <= max_span
        ):
            joined[-1] = Span(span.url, previous.first, span.last)
        else:
            joined.append(span)
    return joined


def _spans_of(http: requests.Session, stream: Stream) -> list[Span]:
    if stream.playlist_url is None:
        return coalesce(list(stream.spans))
    return coalesce(parse_media(_get(http, stream.playlist_url, KINESCOPE_REFERER), stream.playlist_url))


def _download_stream(
    http: requests.Session,
    spans: list[Span],
    target: Path,
    on_bytes: Callable[[int], None] | None,
    should_stop: Callable[[], bool] | None,
) -> None:
    """Write the spans one after another into `target`, continuing an earlier unfinished try.

    A sidecar file remembers how many spans are complete and how long the file was then; a
    span that was cut short is fetched again from its start.
    """
    progress_file = target.with_name(f'{target.name}.progress')
    done, size = 0, 0
    if target.exists() and progress_file.exists():
        try:
            saved = json.loads(progress_file.read_text(encoding='utf-8'))
            done, size = int(saved['spans']), int(saved['size'])
        except (ValueError, KeyError, TypeError):
            done, size = 0, 0
    if not target.exists() or target.stat().st_size < size or done > len(spans):
        done, size = 0, 0
    with target.open('ab') as output:
        output.truncate(size)
    if on_bytes and size:
        on_bytes(size)

    piece = target.with_name(f'{target.name}.span')
    for index in range(done, len(spans)):
        if should_stop and should_stop():
            raise DownloadCancelled
        span = spans[index]
        piece.unlink(missing_ok=True)
        fetch(
            http,
            span.url,
            piece,
            headers={'Referer': KINESCOPE_REFERER},
            first_byte=span.first or 0,
            last_byte=span.last,
            on_bytes=on_bytes,
            should_stop=should_stop,
        )
        with target.open('ab') as output, piece.open('rb') as source:
            while block := source.read(1024 * 1024):
                output.write(block)
        piece.unlink()
        size = target.stat().st_size
        progress_file.write_text(json.dumps({'spans': index + 1, 'size': size}), encoding='utf-8')


def download(
    http: requests.Session,
    embed_url: str,
    dest: Path,
    *,
    work_dir: Path,
    work_name: str,
    ffmpeg: Path,
    max_height: int | None = None,
    on_progress: Callable[[int, int | None], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Stream:
    """Download the video behind `embed_url` into `dest` (an .mp4). Returns the quality that was taken.

    Unfinished pieces live in `work_dir` under `work_name`, so calling again with the same
    name after an interruption continues instead of starting over.
    """
    video = resolve(http, embed_url)
    stream = pick_stream(video.streams, max_height)
    log.info('Video qualities %s, taking %sp', [s.height for s in video.streams], stream.height)

    parts = [(work_dir / f'{work_name}.video', _spans_of(http, stream))]
    if video.sound is not None:
        parts.append((work_dir / f'{work_name}.sound', _spans_of(http, video.sound)))

    sizes = [span.size for _, spans in parts for span in spans]
    total = None if any(size is None for size in sizes) else sum(size for size in sizes if size is not None)
    got = 0

    def on_bytes(count: int) -> None:
        nonlocal got
        got += count
        if on_progress:
            on_progress(got, total)

    for target, spans in parts:
        _download_stream(http, spans, target, on_bytes, should_stop)

    muxed = work_dir / f'{work_name}.mux.mp4'
    mux(ffmpeg, [target for target, _ in parts], muxed)
    dest.parent.mkdir(parents=True, exist_ok=True)
    muxed.replace(dest)
    for target, _ in parts:
        target.unlink(missing_ok=True)
        target.with_name(f'{target.name}.progress').unlink(missing_ok=True)
    return stream
