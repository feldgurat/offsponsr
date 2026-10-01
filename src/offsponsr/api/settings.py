"""The user's settings for the interface; they live with the user, not in a library."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from offsponsr.config import ConfigStore


class Settings(BaseModel):
    theme: Literal['system', 'light', 'dark']
    # How the posts of a project are laid out.
    feed_view: Literal['stream', 'feed', 'tile', 'list']
    hide_closed: bool


class SettingsChange(BaseModel):
    """A field left out stays as it is."""

    theme: Literal['system', 'light', 'dark'] | None = None
    feed_view: Literal['stream', 'feed', 'tile', 'list'] | None = None
    hide_closed: bool | None = None


def settings_router(config: ConfigStore) -> APIRouter:
    router = APIRouter()

    @router.get('/settings')
    def settings() -> Settings:
        return Settings.model_validate(config.load(), from_attributes=True)

    @router.patch('/settings')
    def change_settings(body: SettingsChange) -> Settings:
        return Settings.model_validate(config.update(**body.model_dump(exclude_none=True)), from_attributes=True)

    return router
