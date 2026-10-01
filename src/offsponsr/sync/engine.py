"""Brings one project in the library up to date with sponsr.ru."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from offsponsr.library.models import (
    Account,
    Level,
    Media,
    MediaKind,
    MediaState,
    Post,
    PostStatus,
    PostTag,
    Project,
    SyncRun,
    Tag,
)
from offsponsr.sync.media import MediaRef, media_in_files, media_in_html

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from offsponsr.library import Library
    from offsponsr.sponsr import SponsrClient
    from offsponsr.sponsr.models import Post as SitePost
    from offsponsr.sponsr.models import Subscription

log = logging.getLogger(__name__)

# A usual sync stops at the first page with nothing new on it. Every so often it reads the
# whole list instead: that is the only way to notice old posts that were edited or deleted.
FULL_PASS_EVERY = 10


class SyncCancelled(Exception):
    """The user stopped the sync. What was saved so far stays."""


@dataclass
class SyncStats:
    # Whether the whole list of posts was read, not just its beginning.
    full: bool
    pages: int = 0
    posts_seen: int = 0
    posts_new: int = 0
    posts_changed: int = 0
    texts_fetched: int = 0
    posts_deleted: int = 0


@dataclass(frozen=True)
class SyncProgress:
    project_id: int
    posts_done: int
    # None until the first page of posts has told how many there are.
    posts_total: int | None


def run_scope(project_id: int) -> str:
    return f'project:{project_id}'


class ProjectSync:
    def __init__(
        self,
        library: Library,
        client: SponsrClient,
        *,
        on_progress: Callable[[SyncProgress], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._library = library
        self._client = client
        self._on_progress = on_progress or (lambda progress: None)
        self._should_stop = should_stop or (lambda: False)
        self._now = now

    def run(self, project_id: int, subscription: Subscription | None = None) -> SyncStats:
        """Sync the project; `subscription` is the account's subscription to it, if there is one."""
        with self._library.session() as db:
            project = db.get(Project, project_id)
            if project is None:
                raise LookupError(f'No project {project_id} in the library')

            stats = SyncStats(full=self._full_pass_is_due(db, project))
            run = SyncRun(started_at=self._now(), scope=run_scope(project_id))
            db.add(run)
            db.commit()
            self._on_progress(SyncProgress(project_id, 0, None))

            try:
                self._refresh_project(db, project, subscription)
                self._walk_posts(db, project, stats)
                project.last_synced_at = self._now()
            except BaseException as error:
                # Pages already saved stay saved; only the unfinished one is dropped.
                db.rollback()
                run.error = type(error).__name__
                raise
            finally:
                run.finished_at = self._now()
                run.stats_json = asdict(stats)
                db.commit()
            return stats

    def _check_stop(self) -> None:
        if self._should_stop():
            raise SyncCancelled

    @staticmethod
    def _full_pass_is_due(db: Session, project: Project) -> bool:
        if project.last_synced_at is None:
            return True
        recent = db.scalars(
            select(SyncRun)
            .where(SyncRun.scope == run_scope(project.id), SyncRun.error.is_(None), SyncRun.finished_at.is_not(None))
            .order_by(SyncRun.id.desc())
            .limit(FULL_PASS_EVERY - 1)
        ).all()
        return len(recent) >= FULL_PASS_EVERY - 1 and not any((run.stats_json or {}).get('full') for run in recent)

    def _refresh_project(self, db: Session, project: Project, subscription: Subscription | None) -> None:
        """The project's card, its levels and its collections."""
        self._check_stop()
        page = self._client.project(project.url)
        card = page.project
        project.title = card.title
        project.intent = card.intent
        project.description_html = card.description_html
        project.raw_json = card.raw
        if subscription is not None:
            project.subscription_level_id = subscription.level.id if subscription.level else None
            project.last_paid = subscription.last_paid

        if page.user is not None and page.user.nickname:
            account = db.scalars(select(Account)).first()
            if account is not None and account.user_id == page.user.id:
                account.nickname = page.user.nickname

        self._check_stop()
        for site_level in self._client.levels(project.id):
            level = db.get(Level, site_level.id) or Level(id=site_level.id, project_id=project.id)
            level.name = site_level.name
            level.price = site_level.price
            level.description_html = site_level.description_html
            level.visible = site_level.visible
            db.add(level)

        self._check_stop()
        listed = set()
        for collection in self._client.collections(project.id):
            tag = db.get(Tag, collection.id) or Tag(id=collection.id, project_id=project.id)
            tag.name = collection.name
            tag.count = collection.count
            db.add(tag)
            listed.add(collection.id)
        for tag in db.scalars(select(Tag).where(Tag.project_id == project.id)):
            if tag.id not in listed:
                # No longer among the project's collections; the posts may still carry it.
                tag.count = 0
        db.commit()

    def _walk_posts(self, db: Session, project: Project, stats: SyncStats) -> None:
        seen: set[int] = set()
        reached_the_end = False
        page_number = 1
        while True:
            self._check_stop()
            page = self._client.posts(project.id, page_number)
            if not page.posts:
                reached_the_end = True
                break

            known = {post.id: post for post in db.scalars(select(Post).where(Post.id.in_([p.id for p in page.posts])))}
            waiting_for_text: list[tuple[Post, SitePost]] = []
            anything_new = False
            for site_post in page.posts:
                post = known.get(site_post.id)
                is_new = post is None
                if post is None:
                    post = Post(id=site_post.id, project_id=project.id)
                    db.add(post)
                changed, wants_text = self._apply(db, post, site_post, is_new=is_new)
                stats.posts_new += is_new
                stats.posts_changed += changed and not is_new
                anything_new = anything_new or is_new or changed or wants_text
                if wants_text:
                    waiting_for_text.append((post, site_post))

            if waiting_for_text:
                self._check_stop()
                stats.texts_fetched += self._fetch_texts(db, project, page_number, waiting_for_text)

            db.commit()
            seen.update(post.id for post in page.posts)
            stats.pages += 1
            stats.posts_seen += len(page.posts)
            self._on_progress(SyncProgress(project.id, stats.posts_seen, page.total))

            if stats.posts_seen >= page.total:
                reached_the_end = True
                break
            if not stats.full and not anything_new:
                break
            page_number += 1

        if stats.full and reached_the_end:
            stats.posts_deleted = self._mark_deleted(db, project, seen)
            db.commit()

    def _apply(self, db: Session, post: Post, site_post: SitePost, *, is_new: bool) -> tuple[bool, bool]:
        """Bring a post's row in line with the site's list. Returns (changed, wants the whole text)."""
        was_available = None if is_new else post.available
        changed = is_new or post.updated_at_site != site_post.updated_at or was_available != site_post.available

        post.available = site_post.available
        post.level_id = site_post.level_id
        post.date = site_post.date
        post.title = site_post.title
        post.teaser = site_post.teaser
        post.views = site_post.views
        post.duration_text = site_post.duration_text
        post.duration_audio = site_post.duration_podcast
        post.duration_video = site_post.duration_video
        post.content_type = site_post.content_type
        post.pinned = site_post.pinned
        post.raw_json = site_post.raw
        if post.status == PostStatus.DELETED_ON_SITE:
            # It is on the list again.
            post.status = PostStatus.ACTIVE
        self._set_tags(db, post, site_post)

        if not site_post.available:
            post.updated_at_site = site_post.updated_at
            if post.html_is_full:
                # It was readable once: keep the text, say that the site no longer gives it.
                post.status = PostStatus.UNAVAILABLE
            return changed, False

        if post.status == PostStatus.UNAVAILABLE:
            post.status = PostStatus.ACTIVE

        if site_post.has_full_text:
            if changed or not post.html_is_full or post.html != site_post.html:
                self._set_text(db, post, site_post, site_post.html)
            post.updated_at_site = site_post.updated_at
            return changed, False

        # The list gave only the beginning of the text.
        wants_text = changed or not post.html_is_full
        if post.html is None:
            post.html = site_post.html
            post.html_is_full = False
        if not wants_text:
            post.updated_at_site = site_post.updated_at
        # Otherwise `updated_at_site` is set when the whole text arrives: until then the row
        # must keep looking out of date, so that the next sync asks for the text again.
        return changed, wants_text

    def _fetch_texts(
        self, db: Session, project: Project, page_number: int, waiting: list[tuple[Post, SitePost]]
    ) -> int:
        texts = {text.id: text for text in self._client.full_texts(project.id, page_number).posts}
        fetched = 0
        for post, site_post in waiting:
            text = texts.get(post.id)
            if text is None or not text.available or not text.html:
                # The list moved between the two requests, or the text didn't come; next sync retries.
                log.info('No whole text for a post on page %s of project %s', page_number, project.id)
                continue
            self._set_text(db, post, site_post, text.html)
            post.updated_at_site = site_post.updated_at
            fetched += 1
        return fetched

    def _set_text(self, db: Session, post: Post, site_post: SitePost, html: str | None) -> None:
        post.html = html
        post.html_is_full = True
        post.fetched_at = self._now()
        self._set_media(db, post, media_in_html(html) + media_in_files(site_post.files))

    @staticmethod
    def _set_media(db: Session, post: Post, refs: list[MediaRef]) -> None:
        """Make the post's media rows match what the post refers to now."""
        current = {
            (media.kind, media.source_id): media for media in db.scalars(select(Media).where(Media.post == post))
        }
        wanted = set()
        for ref in refs:
            key = (ref.kind, ref.source_id)
            wanted.add(key)
            media = current.get(key)
            if media is None:
                state = MediaState.SKIPPED if ref.kind == MediaKind.EMBED else MediaState.PENDING
                media = Media(post=post, kind=ref.kind, source_id=ref.source_id, state=state)
                db.add(media)
            media.source_url = ref.source_url
            media.title = ref.title
            media.size = ref.size
            media.duration = ref.duration
        for key, media in current.items():
            # Something already downloaded keeps its row, so the file is never left ownerless.
            if key not in wanted and media.local_path is None:
                db.delete(media)

    @staticmethod
    def _set_tags(db: Session, post: Post, site_post: SitePost) -> None:
        wanted = {tag.id: tag.name for tag in site_post.tags}
        for tag_id, name in wanted.items():
            if db.get(Tag, tag_id) is None:
                # A tag the project doesn't list among its collections.
                db.add(Tag(id=tag_id, project_id=post.project_id, name=name, count=0))
        current = {link.tag_id: link for link in db.scalars(select(PostTag).where(PostTag.post == post))}
        for tag_id in wanted.keys() - current.keys():
            db.add(PostTag(post=post, tag_id=tag_id))
        for tag_id in current.keys() - wanted.keys():
            db.delete(current[tag_id])

    @staticmethod
    def _mark_deleted(db: Session, project: Project, seen: set[int]) -> int:
        """Posts the library has and the site's list no longer does stay, marked as deleted there."""
        kept = db.scalars(select(Post).where(Post.project_id == project.id, Post.status != PostStatus.DELETED_ON_SITE))
        gone = [post for post in kept if post.id not in seen]
        for post in gone:
            post.status = PostStatus.DELETED_ON_SITE
        return len(gone)
