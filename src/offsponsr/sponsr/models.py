"""What sponsr.ru's answers look like, cut down to what the app uses.

The endpoints are unofficial: fields come and go, so everything not named here is ignored
and nearly everything named is optional. Field names are the app's; aliases are the site's.
"""

from __future__ import annotations

import re
from datetime import datetime  # noqa: TC003 - pydantic needs it at runtime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import AliasPath, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

# The legacy endpoint scatters these two invisible direction marks between the words.
_INVISIBLE_MARKS = re.compile('[\u200e\u200f]')


def strip_marks(html: str | None) -> str | None:
    return None if html is None else _INVISIBLE_MARKS.sub('', html)


def _whole_number(value: Any) -> Any:
    """The site sends numbers as text now and then: '300', '1234.56'."""
    if isinstance(value, str):
        try:
            return int(Decimal(value).to_integral_value(ROUND_HALF_UP))
        except InvalidOperation:
            return value
    if isinstance(value, float):
        return round(value)
    return value


WholeNumber = Annotated[int | None, BeforeValidator(_whole_number)]


class SiteModel(BaseModel):
    model_config = ConfigDict(extra='ignore', populate_by_name=True, frozen=True)


class Logo(SiteModel):
    """Paths on sponsr.ru, relative to the site root."""

    x1: str | None = Field(None, alias='1x')
    x2: str | None = Field(None, alias='2x')


class SubscriptionLevel(SiteModel):
    id: int
    name: str
    price: WholeNumber = None


class Subscription(SiteModel):
    """A project the account pays for."""

    id: int
    url: str
    title: str
    owner_name: str | None = Field(None, validation_alias=AliasPath('owner', 'name'))
    logo: Logo | None = None
    level: SubscriptionLevel | None = None
    last_paid: datetime | None = None
    status: str | None = None
    months: int | None = None
    # The site's answer as it came, minus the author's email, which the app has no business keeping.
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @model_validator(mode='before')
    @classmethod
    def _keep_raw(cls, data: Any) -> Any:
        if isinstance(data, dict) and 'raw' not in data:
            raw = dict(data)
            if isinstance(raw.get('owner'), dict):
                raw['owner'] = {key: value for key, value in raw['owner'].items() if key != 'email'}
            return {**data, 'raw': raw}
        return data


class PostTag(SiteModel):
    id: int = Field(alias='tag_id')
    name: str = Field(validation_alias=AliasPath('tag', 'tag_name'))


class PostFile(SiteModel):
    id: int
    # `podcast` for audio; attachments come under other names.
    category: str | None = None
    mime: str | None = None
    name: str | None = None
    title: str | None = None
    # Relative to the site root.
    path: str
    size: WholeNumber = None
    # Seconds.
    duration: WholeNumber = None
    kinescope_id: str | None = None


class VideoPoster(SiteModel):
    # `kinescope`, `youtube`, ...
    type: str
    iframe_src: str | None = None
    poster_url: str | None = None


class Post(SiteModel):
    """A post as the post list gives it.

    A post the account can't read comes with little more than its id, title and date.
    """

    id: int
    project_id: int
    level_id: int | None = None
    date: datetime
    title: str
    available: bool
    # None when the account can't read the post.
    html: str | None = Field(None, validation_alias=AliasPath('text', 'text'))
    # False: `html` is the whole text. True: only its beginning. None: there is no text.
    text_truncated: bool | None = None
    content_type: str | None = None
    teaser: str | None = None
    image: str | None = None
    status: str | None = None
    pinned: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    views: int | None = None
    duration_text: int | None = None
    duration_podcast: int | None = None
    duration_video: int | None = None
    tags: list[PostTag] = Field(default_factory=list)
    files: list[PostFile] = Field(default_factory=list)
    video_posters: list[VideoPoster] = Field(default_factory=list)
    # The site's answer as it came, minus the text, which is kept separately.
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @model_validator(mode='before')
    @classmethod
    def _keep_raw(cls, data: Any) -> Any:
        if isinstance(data, dict) and 'raw' not in data:
            return {**data, 'raw': {key: value for key, value in data.items() if key != 'text'}}
        return data

    @property
    def has_full_text(self) -> bool:
        return self.html is not None and self.text_truncated is False


class PostsPage(SiteModel):
    total: int
    page: int
    limit: int
    posts: list[Post] = Field(alias='list')


class FullText(SiteModel):
    """A post as the legacy list gives it: the whole text, invisible marks removed."""

    id: int = Field(alias='post_id')
    html: Annotated[str | None, BeforeValidator(strip_marks)] = Field(None, alias='post_text')
    available: bool = Field(default=True, alias='_available')


class FullTextsPage(SiteModel):
    total: int = Field(alias='rows_count')
    posts: list[FullText] = Field(alias='rows')


class Level(SiteModel):
    id: int
    project_id: int
    name: str = Field(alias='level_name')
    price: WholeNumber = Field(None, alias='level_price')
    description_html: str | None = Field(None, alias='level_description')
    # `visible` or `hidden`.
    visibility: str | None = Field(None, alias='level_visible')
    # `active` or `deleted`.
    status: str | None = Field(None, alias='level_status')

    @property
    def visible(self) -> bool:
        return self.visibility == 'visible' and self.status != 'deleted'


class Collection(SiteModel):
    """A tag; the site shows a project's tags as its collections."""

    id: int
    project_id: int
    name: str = Field(alias='tag_name')
    count: int = 0
    image: str | None = None


class ProjectCard(SiteModel):
    id: int
    url: str = Field(alias='project_url')
    title: str = Field(alias='project_title')
    intent: str | None = Field(None, alias='project_intent')
    description_html: str | None = Field(None, validation_alias=AliasPath('description', 'description'))
    # Paths on sponsr.ru, relative to the site root.
    cover: str | None = Field(None, alias='image')
    logo: Logo | None = None
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @model_validator(mode='before')
    @classmethod
    def _keep_raw(cls, data: Any) -> Any:
        if isinstance(data, dict) and 'raw' not in data:
            return {**data, 'raw': dict(data)}
        return data


class SiteUser(SiteModel):
    id: int
    nickname: str | None = None


class ProjectPage(SiteModel):
    """What a project's page says: the project, its levels and who is looking."""

    project: ProjectCard
    levels: list[Level] = Field(default_factory=list, alias='projectLevels')
    # None when the page was loaded without a signed-in session.
    user: SiteUser | None = None
