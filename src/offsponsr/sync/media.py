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
# In the player frame: data-url="/post/video/?video_id=<uuid>?poster_id=<uuid>"
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

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value for name, value in attrs if value}
        if tag == 'img':
            # The site lazy-loads pictures; whichever attribute holds the address will do.
            url = values.get('src') or values.get('data-src')
            if url:
                self.found.append(MediaRef(MediaKind.IMAGE, _without_query(url), url))
        elif tag == 'iframe':
            url = values.get('src') or values.get('data-src')
            if url:
                self.found.append(self._frame(url, values.get('data-url', '')))

    @staticmethod
    def _frame(url: str, data_url: str) -> MediaRef:
        parts = urlsplit(url)
        if parts.hostname in KINESCOPE_HOSTS:
            video_id = _VIDEO_ID.search(data_url)
            # The video's UUID where the frame gives it, the id of the embed otherwise.
            return MediaRef(MediaKind.VIDEO, video_id.group(1) if video_id else parts.path.strip('/'), url)
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
