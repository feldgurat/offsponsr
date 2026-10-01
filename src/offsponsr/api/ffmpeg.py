"""ffmpeg: whether there is one, installing one, pointing at one."""

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from offsponsr.media.ffmpeg_setup import FfmpegSetup, FfmpegState

# Shows the system file dialog for picking a program; None if the user cancelled it.
ProgramPicker = Callable[[], Path | None]


class FfmpegInfo(BaseModel):
    found: bool
    path: str | None
    version: str | None
    # The path is the one the user pointed at, not one the app found.
    chosen: bool
    # The app can install ffmpeg by itself: there is a winget.
    can_install: bool
    installing: bool
    # The code of why the last installation failed.
    error: str | None
    platform: Literal['windows', 'macos', 'linux']


def _info(state: FfmpegState) -> FfmpegInfo:
    return FfmpegInfo.model_validate(state.to_json())


def ffmpeg_router(setup: FfmpegSetup, pick_program: ProgramPicker) -> APIRouter:
    router = APIRouter()

    @router.get('/ffmpeg')
    def ffmpeg() -> FfmpegInfo:
        """Whether there is an ffmpeg to join videos with."""
        return _info(setup.state())

    @router.post('/ffmpeg/check')
    def check() -> FfmpegInfo:
        """Look for ffmpeg again; if it has turned up, the videos that waited for it are queued."""
        return _info(setup.check())

    @router.post('/ffmpeg/install')
    def install() -> FfmpegInfo:
        """Start installing ffmpeg with winget. The UI asks the user before calling this."""
        return _info(setup.install())

    @router.post('/ffmpeg/choose')
    def choose() -> FfmpegInfo:
        """Let the user point at their ffmpeg in the system's file dialog.

        The path never comes from the page: what gets run is only what the user picked themselves.
        """
        picked = pick_program()
        return _info(setup.choose(picked) if picked else setup.state())

    @router.delete('/ffmpeg/choice')
    def forget_choice() -> FfmpegInfo:
        return _info(setup.forget_choice())

    return router
