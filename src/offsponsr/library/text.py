"""Plain text out of a post's HTML: for the short previews in the feeds."""

from __future__ import annotations

import re
from html.parser import HTMLParser

# Tags that end a line of text; their neighbours must not run together into one word.
_BLOCKS = frozenset(
    {
        'p', 'div', 'br', 'li', 'ul', 'ol', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'tr', 'td', 'th', 'figure', 'figcaption', 'hr',
    }
)  # fmt: skip
# Their content is not text to read.
_SILENT = frozenset({'script', 'style', 'iframe'})
_SPACES = re.compile(r'\s+')

ELLIPSIS = '…'


class _Text(HTMLParser):
    def __init__(self, limit: int) -> None:
        super().__init__(convert_charrefs=True)
        self.pieces: list[str] = []
        self.length = 0
        self._limit = limit
        self._silent = 0

    @property
    def full(self) -> bool:
        return self.length > self._limit

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SILENT:
            self._silent += 1
        elif tag in _BLOCKS:
            self.pieces.append(' ')

    def handle_endtag(self, tag: str) -> None:
        if tag in _SILENT:
            self._silent = max(0, self._silent - 1)
        elif tag in _BLOCKS:
            self.pieces.append(' ')

    def handle_data(self, data: str) -> None:
        if not self._silent and not self.full:
            self.pieces.append(data)
            self.length += len(data)


def plain_text(html: str | None, limit: int) -> str:
    """The beginning of the text without markup, at most `limit` characters, cut at a word."""
    if not html:
        return ''
    parser = _Text(limit)
    parser.feed(html)
    parser.close()
    text = _SPACES.sub(' ', ''.join(parser.pieces)).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # Back to the end of the last whole word, unless that throws away most of the text.
    space = cut.rfind(' ')
    if space > limit // 2:
        cut = cut[:space]
    return cut.rstrip(' ,;:—-') + ELLIPSIS
