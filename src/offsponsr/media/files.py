"""Downloads one file over HTTP into a `.part` file, picking up where an earlier try stopped."""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

log = logging.getLogger(__name__)

# Seconds to connect, seconds to wait for the next bytes.
TIMEOUT = (10, 60)
BLOCK = 256 * 1024

# A dropped connection is tried again this many times, each try continuing the same file.
RETRIES = 3
RETRY_DELAY = 2.0

_CONTENT_RANGE = re.compile(r'bytes (\d+)-(\d+)/(\d+|\*)')
_UNSATISFIED_RANGE = re.compile(r'bytes \*/(\d+)')


class DownloadCancelled(Exception):
    """The user stopped the download. What was written so far stays for the next try."""


class DownloadError(Exception):
    """The file couldn't be downloaded. `code` is what the UI keys its message on."""

    def __init__(self, code: str, detail: str = '') -> None:
        super().__init__(f'{code}: {detail}' if detail else code)
        self.code = code


def _error_for(status: int) -> DownloadError:
    if status in (401, 403):
        return DownloadError('forbidden', f'HTTP {status}')
    if status in (404, 410):
        return DownloadError('not_found', f'HTTP {status}')
    return DownloadError('site_unavailable', f'HTTP {status}')


def fetch(
    http: requests.Session,
    url: str,
    part: Path,
    *,
    headers: Mapping[str, str] | None = None,
    first_byte: int = 0,
    last_byte: int | None = None,
    on_bytes: Callable[[int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Append bytes `first_byte..last_byte` of `url` (the whole of it by default) to `part`.

    `part` may already hold the beginning of that span from an earlier try; only the rest is
    asked for. `on_bytes` is told how many bytes each block added. Returns the size of the span.
    """
    attempt = 0
    while True:
        try:
            return _fetch_once(http, url, part, headers or {}, first_byte, last_byte, on_bytes, should_stop)
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as error:
            attempt += 1
            if attempt > RETRIES:
                raise DownloadError('site_unavailable', str(error)) from error
            log.warning('Download interrupted (%s); continuing', type(error).__name__)
            sleep(RETRY_DELAY)


def _fetch_once(
    http: requests.Session,
    url: str,
    part: Path,
    headers: Mapping[str, str],
    first_byte: int,
    last_byte: int | None,
    on_bytes: Callable[[int], None] | None,
    should_stop: Callable[[], bool] | None,
) -> int:
    have = part.stat().st_size if part.exists() else 0
    wanted = None if last_byte is None else last_byte - first_byte + 1
    if wanted is not None and have >= wanted:
        return have

    request_headers = dict(headers)
    start = first_byte + have
    if start or last_byte is not None:
        request_headers['Range'] = f'bytes={start}-{"" if last_byte is None else last_byte}'
        # A compressed answer would make byte positions meaningless.
        request_headers['Accept-Encoding'] = 'identity'

    with http.get(url, headers=request_headers, stream=True, timeout=TIMEOUT) as response:
        status = response.status_code
        if status == 416 and have:
            # Nothing past what we have: the earlier try had already got the whole file.
            complete = _UNSATISFIED_RANGE.match(response.headers.get('Content-Range', ''))
            if complete and int(complete.group(1)) == start:
                return have
            part.unlink()
            return _fetch_once(http, url, part, headers, first_byte, last_byte, on_bytes, should_stop)
        if status == 200 and (have or first_byte):
            if first_byte:
                # A span from the middle was asked for and the server sent everything.
                raise DownloadError('site_unavailable', 'the server ignored the byte range')
            # The server sent the file from its start: begin again.
            have = 0
            mode = 'wb'
        elif status in (200, 206):
            mode = 'ab'
        else:
            raise _error_for(status)

        expected = _expected_size(response, have, wanted)
        with part.open(mode) as output:
            for block in response.iter_content(BLOCK):
                if should_stop and should_stop():
                    raise DownloadCancelled
                output.write(block)
                have += len(block)
                if on_bytes:
                    on_bytes(len(block))

    if expected is not None and have != expected:
        # The connection closed early without an error; the caller's retry continues from here.
        raise requests.ConnectionError(f'got {have} bytes of {expected}')
    return have


def _expected_size(response: requests.Response, have: int, wanted: int | None) -> int | None:
    """How big the span should be once this response has been read to its end."""
    if wanted is not None:
        return wanted
    content_range = _CONTENT_RANGE.match(response.headers.get('Content-Range', ''))
    if content_range and content_range.group(3) != '*':
        return int(content_range.group(3))
    length = response.headers.get('Content-Length')
    if length and length.isdigit() and response.headers.get('Content-Encoding') in (None, 'identity'):
        return have + int(length)
    return None
