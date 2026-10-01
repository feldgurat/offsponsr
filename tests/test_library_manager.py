import shutil

import pytest

from offsponsr.library import FolderNotEmptyError, Library, LibraryManager
from offsponsr.library.lock import LibraryLock


def is_unlocked(root):
    lock = LibraryLock(root)
    lock.acquire()
    lock.release()
    return True


def test_nothing_to_reopen_on_first_run(libraries):
    libraries.open_last()

    assert libraries.current is None
    assert libraries.last_failure is None


def test_created_library_is_reopened_on_next_run(libraries, config_store, tmp_path):
    created = libraries.create(tmp_path / 'library')
    libraries.close()

    next_run = LibraryManager(config_store)
    next_run.open_last()
    try:
        assert next_run.current.id == created.id
        assert next_run.last_failure is None
    finally:
        next_run.close()


def test_reopen_reports_a_library_that_is_gone(libraries, config_store, tmp_path):
    root = libraries.create(tmp_path / 'library').root
    libraries.close()
    shutil.rmtree(root)

    next_run = LibraryManager(config_store)
    next_run.open_last()

    assert next_run.current is None
    assert next_run.last_failure.code == 'missing'
    assert next_run.last_failure.path == root


def test_opening_a_library_clears_the_failure(libraries, config_store, tmp_path):
    root = libraries.create(tmp_path / 'library').root
    libraries.close()
    shutil.rmtree(root)
    next_run = LibraryManager(config_store)
    next_run.open_last()

    next_run.create(tmp_path / 'another')
    try:
        assert next_run.last_failure is None
    finally:
        next_run.close()


def test_switching_closes_the_previous_library(libraries, config_store, tmp_path):
    first = libraries.create(tmp_path / 'first')
    second = libraries.create(tmp_path / 'second')

    assert libraries.current is second
    assert is_unlocked(first.root)
    assert config_store.load().library_path == str(second.root)


def test_failed_switch_keeps_the_current_library(libraries, config_store, tmp_path):
    current = libraries.create(tmp_path / 'library')
    busy = tmp_path / 'busy'
    busy.mkdir()
    (busy / 'file.txt').write_text('x', encoding='utf-8')

    with pytest.raises(FolderNotEmptyError):
        libraries.create(busy)

    assert libraries.current is current
    assert config_store.load().library_path == str(current.root)
    with current.session() as session:
        session.connection()


def test_opening_the_open_library_again_is_a_no_op(libraries, tmp_path):
    current = libraries.create(tmp_path / 'library')

    assert libraries.open(tmp_path / 'library') is current


def test_open_existing_library(libraries, tmp_path):
    root = tmp_path / 'library'
    Library.create(root).close()

    opened = libraries.open(root)

    assert libraries.current is opened
    assert opened.root == root
