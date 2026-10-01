import subprocess
import sys
import webbrowser
from pathlib import Path

import pytest

from offsponsr import shell as shell_module
from offsponsr.shell import Shell, ShellError, is_openable, is_web_link


@pytest.fixture
def launched(monkeypatch):
    """What the shell asked the system to run, instead of running it."""
    calls = []
    monkeypatch.setattr(subprocess, 'Popen', lambda command: calls.append(command))
    monkeypatch.setattr(webbrowser, 'open', lambda url: calls.append(['browser', url]))
    if sys.platform == 'win32':
        monkeypatch.setattr(shell_module.os, 'startfile', lambda path: calls.append(['startfile', path]))
    return calls


def test_web_links():
    assert is_web_link('https://sponsr.ru/project/1/')
    assert is_web_link('http://example.com')
    assert is_web_link('mailto:author@example.com')
    for other in ('file:///etc/passwd', 'javascript:alert(1)', 'mailto:', 'https://', '/relative', ''):
        assert not is_web_link(other)


def test_what_may_be_opened():
    assert is_openable(Path('Книга.PDF'))
    assert is_openable(Path('выпуск.mp3'))
    for other in ('setup.exe', 'run.bat', 'archive.zip', 'page.html', 'script.ps1', 'no-extension'):
        assert not is_openable(Path(other))


def test_open_url(launched):
    Shell().open_url('https://example.com/a?b=1')

    assert launched == [['browser', 'https://example.com/a?b=1']]


def test_open_url_refuses_what_is_not_a_web_link(launched):
    with pytest.raises(ShellError):
        Shell().open_url('file:///C:/Windows/system32/calc.exe')

    assert launched == []


def test_open_file(launched, tmp_path):
    book = tmp_path / 'Книга.pdf'
    book.write_bytes(b'%PDF')

    Shell().open_file(book)

    [command] = launched
    assert command[-1] == str(book)


def test_open_file_refuses_programs_and_missing_files(launched, tmp_path):
    program = tmp_path / 'setup.exe'
    program.write_bytes(b'MZ')

    with pytest.raises(ShellError):
        Shell().open_file(program)
    with pytest.raises(ShellError):
        Shell().open_file(tmp_path / 'missing.pdf')

    assert launched == []


def test_reveal(launched, tmp_path):
    book = tmp_path / 'Книга.pdf'
    book.write_bytes(b'%PDF')

    Shell().reveal(book)

    [command] = launched
    if sys.platform == 'win32':
        assert command == ['explorer', f'/select,{book}']
    elif sys.platform == 'darwin':
        assert command == ['open', '-R', str(book)]
    else:
        assert command == ['xdg-open', str(tmp_path)]


@pytest.mark.skipif(sys.platform != 'win32', reason='The long-path prefix exists only on Windows')
def test_the_windows_shell_gets_paths_without_the_long_prefix(launched, tmp_path):
    book = tmp_path / 'Книга.pdf'
    book.write_bytes(b'%PDF')
    prefixed = Path('\\\\?\\' + str(book))

    Shell().reveal(prefixed)
    Shell().open_file(prefixed)

    assert launched == [['explorer', f'/select,{book}'], ['startfile', str(book)]]


def test_a_system_without_the_program_is_reported(monkeypatch, tmp_path):
    def missing(command):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr(subprocess, 'Popen', missing)

    with pytest.raises(ShellError):
        Shell().reveal(tmp_path / 'file.pdf')
