from pathlib import Path

import pytest
import webview
from webview.util import parse_file_type

from offsponsr import __version__
from offsponsr.app import parse_args, pick_program, window_url


def test_parse_args_defaults():
    assert parse_args([]).dev is False
    assert parse_args(['--dev']).dev is True


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        parse_args(['--version'])

    assert capsys.readouterr().out.strip() == f'offsponsr {__version__}'


def test_window_url_carries_launch_token():
    assert window_url('http://127.0.0.1:5000', 'abc') == 'http://127.0.0.1:5000/?token=abc'


def test_program_dialog(monkeypatch, tmp_path):
    class Window:
        choice = None

        def create_file_dialog(self, kind, file_types=()):
            # The window refuses filters it can't read; the real check is the window's own.
            self.asked = (kind, [parse_file_type(file_type) for file_type in file_types])
            return self.choice

    window = Window()
    monkeypatch.setattr(webview, 'windows', [window])

    assert pick_program() is None
    kind, filters = window.asked
    assert kind == webview.FileDialog.OPEN
    assert len(filters) == 1

    window.choice = (str(tmp_path / 'ffmpeg.exe'),)
    assert pick_program() == Path(tmp_path / 'ffmpeg.exe')
