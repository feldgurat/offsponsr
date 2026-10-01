"""Finds what a post refers to besides its text: pictures, video, audio, attached files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from offsponsr.library.models import MediaKind

if TYPE_CHECKING:
    from offsponsr.sponsr.models import PostFile

KINESCOPE_HOSTS = ('kinescope.io',)
# A frame's address on the site itself comes without a host.
SITE_HOSTS = (None, 'sponsr.ru', 'www.sponsr.ru')
SITE_PLAYER_PATH = '/post/video'
# In the player frame: data-url="/post/video/?video_id=<uuid>?poster_id=<uuid>"; in older posts
# the same address is the frame's `src`.
_VIDEO_ID = re.compile(r'video_id=([0-9a-fA-F-]{36})')

AUDIO_CATEGORY = 'podcast'


@dataclass(frozen=True)
class MediaRef:
    kind: MediaKind
    # What tells this item from the post's other items of its kind, and stays the same between syncs.
    source_id: str
    source_url: str
    title: str | None = None
    size: int | None = None
    duration: int | None = None


def _without_query(url: str) -> str:
    """Addresses of the same picture differ in their query (a cache stamp); the rest is its identity."""
    parts = urlsplit(url)
    return f'{parts.netloc}{parts.path}'


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[MediaRef] = []
        # For each item found: where its tag starts in the text, as (line, column), and the tag's name.
        self.places: list[tuple[int, int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value for name, value in attrs if value}
        if tag == 'img':
            # The site lazy-loads pictures; whichever attribute holds the address will do.
            url = values.get('src') or values.get('data-src')
            if url:
                self._add(tag, MediaRef(MediaKind.IMAGE, _without_query(url), url))
        elif tag == 'iframe':
            url = values.get('src') or values.get('data-src')
            if url:
                self._add(tag, self._frame(url, values.get('data-url', '')))

    def _add(self, tag: str, ref: MediaRef) -> None:
        self.found.append(ref)
        self.places.append((*self.getpos(), tag))

    @staticmethod
    def _frame(url: str, data_url: str) -> MediaRef:
        parts = urlsplit(url)
        if parts.hostname in KINESCOPE_HOSTS:
            video_id = _VIDEO_ID.search(data_url)
            # The video's UUID where the frame gives it, the id of the embed otherwise.
            return MediaRef(MediaKind.VIDEO, video_id.group(1) if video_id else parts.path.strip('/'), url)
        if parts.hostname in SITE_HOSTS and parts.path.rstrip('/') == SITE_PLAYER_PATH:
            # Older posts point at the site's own player page; Kinescope serves the same video by its UUID.
            video_id = _VIDEO_ID.search(url)
            if video_id:
                return MediaRef(MediaKind.VIDEO, video_id.group(1), f'https://{KINESCOPE_HOSTS[0]}/{video_id.group(1)}')
        # Somebody else's player (YouTube and the like): shown online, never downloaded.
        return MediaRef(MediaKind.EMBED, _without_query(url), url)


def media_in_html(html: str | None) -> list[MediaRef]:
    """Pictures, videos and third-party players in a post's text, in the order they appear."""
    if not html:
        return []
    collector = _Collector()
    collector.feed(html)
    collector.close()
    return _unique(collector.found)


MEDIA_ATTRIBUTE = 'data-media'


def mark_media(html: str, ids: dict[tuple[MediaKind, str], int]) -> str:
    """The same text with every picture and player frame labelled with the id of its media row.

    `ids` maps (kind, source_id), as `media_in_html` gives them, to ids. The label is how the UI
    tells which file to show in place of an address on the site.
    """
    collector = _Collector()
    collector.feed(html)
    collector.close()

    # The parser counts lines by `\n` alone, so that is how its positions turn back into offsets.
    line_starts = [0]
    newline = html.find('\n')
    while newline != -1:
        line_starts.append(newline + 1)
        newline = html.find('\n', newline + 1)

    pieces = []
    done = 0
    for ref, (line, column, tag) in zip(collector.found, collector.places, strict=True):
        media_id = ids.get((ref.kind, ref.source_id))
        if media_id is None:
            continue
        # Right after the tag's name: `<img` + ` data-media="7"`.
        at = line_starts[line - 1] + column + 1 + len(tag)
        pieces += [html[done:at], f' {MEDIA_ATTRIBUTE}="{media_id}"']
        done = at
    pieces.append(html[done:])
    return ''.join(pieces)


def media_in_files(files: list[PostFile]) -> list[MediaRef]:
    """Audio and attachments that come with a post as files."""
    found = []
    for file in files:
        is_audio = file.category == AUDIO_CATEGORY or (file.mime or '').startswith('audio/')
        found.append(
            MediaRef(
                kind=MediaKind.AUDIO if is_audio else MediaKind.ATTACH,
                source_id=str(file.id),
                source_url=file.path,
                title=file.title or file.name,
                size=file.size,
                duration=file.duration,
            )
        )
    return _unique(found)


def _unique(refs: list[MediaRef]) -> list[MediaRef]:
    seen = set()
    unique = []
    for ref in refs:
        key = (ref.kind, ref.source_id)
        if key not in seen:
            seen.add(key)
            unique.append(ref)
    return unique
