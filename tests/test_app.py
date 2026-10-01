import pytest

from offsponsr import __version__
from offsponsr.app import parse_args, window_url


def test_parse_args_defaults():
    assert parse_args([]).dev is False
    assert parse_args(['--dev']).dev is True


def test_version_flag(capsys):
    with pytest.raises(SystemExit):
        parse_args(['--version'])

    assert capsys.readouterr().out.strip() == f'offsponsr {__version__}'


def test_window_url_carries_launch_token():
    assert window_url('http://127.0.0.1:5000', 'abc') == 'http://127.0.0.1:5000/?token=abc'
