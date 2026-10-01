"""Addresses the UI loads the library's files from (served by api/files.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from offsponsr.library.models import MediaKind, MediaState
from offsponsr.media.downloader import site_url

if TYPE_CHECKING:
    from offsponsr.library.models import Media, Post, Project

# What the UI shows right in the page. Attachments are never served to it: they open in other programs.
SHOWN_KINDS = (MediaKind.IMAGE, MediaKind.AUDIO, MediaKind.VIDEO)


def media_url(media: Media) -> str | None:
    """Where the UI gets the file from, once it is in the library."""
    if media.state != MediaState.DONE or not media.local_path or media.kind not in SHOWN_KINDS:
        return None
    return f'/media/{media.id}'


def _picture(local_path: str | None, local_url: str, remote: str | None) -> str | None:
    """The copy in the library; until it is downloaded, the picture's public address on the site."""
    if local_path:
        return local_url
    return site_url(remote) if remote else None


def post_cover_url(post: Post) -> str | None:
    return _picture(post.cover_path, f'/media/posts/{post.id}/cover', post.cover_url)


def project_logo_url(project: Project) -> str | None:
    return _picture(project.logo_path, f'/media/projects/{project.id}/logo', project.logo_url)


def project_cover_url(project: Project) -> str | None:
    return _picture(project.cover_path, f'/media/projects/{project.id}/cover', project.cover_url)
