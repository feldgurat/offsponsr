import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from offsponsr.library import (
    FolderNotEmptyError,
    Library,
    LibraryExistsError,
    LibraryLockedError,
    LibraryMissingError,
    LibraryTooNewError,
    NotALibraryError,
)
from offsponsr.library.library import FORMAT_VERSION
from offsponsr.library.lock import LibraryLock
from offsponsr.library.models import AddedVia, Base, Level, MediaMode, Project


@pytest.fixture
def root(tmp_path):
    return tmp_path / 'Библиотека'


@pytest.fixture
def library(root):
    library = Library.create(root)
    yield library
    library.close()


def make_project(**overrides):
    fields = {
        'id': 7,
        'url': 'someproject',
        'title': 'Проект',
        'added_via': AddedVia.SUBSCRIPTION,
        'media_mode_audio': MediaMode.AUTO,
        'media_mode_video': MediaMode.MANUAL,
        'media_mode_attach': MediaMode.MANUAL,
    }
    return Project(**(fields | overrides))


def test_create_lays_out_the_folder(library, root):
    manifest = json.loads((root / 'library.json').read_text(encoding='utf-8'))

    assert manifest['format'] == FORMAT_VERSION
    assert uuid.UUID(manifest['id'])
    assert library.id == manifest['id']
    assert (root / 'offsponsr.db').is_file()
    assert library.projects_dir == root / 'projects'
    assert library.projects_dir.is_dir()
    assert library.tmp_dir == root / '.tmp'
    assert library.tmp_dir.is_dir()


def test_create_builds_the_schema(library):
    with library.session() as session:
        tables = set(inspect(session.connection()).get_table_names())

    assert set(Base.metadata.tables) <= tables


def test_create_in_existing_empty_folder(root):
    root.mkdir()
    (root / 'desktop.ini').write_text('', encoding='utf-8')
    (root / '.DS_Store').write_text('', encoding='utf-8')

    Library.create(root).close()

    assert (root / 'library.json').is_file()


def test_create_refuses_a_folder_with_files(root):
    root.mkdir()
    (root / 'notes.txt').write_text('mine', encoding='utf-8')

    with pytest.raises(FolderNotEmptyError) as raised:
        Library.create(root)

    assert raised.value.code == 'not_empty'
    assert raised.value.path == root
    assert [entry.name for entry in root.iterdir()] == ['notes.txt']


def test_create_refuses_an_existing_library(library, root):
    with pytest.raises(LibraryExistsError):
        Library.create(root)


def test_open_missing_folder(root):
    with pytest.raises(LibraryMissingError):
        Library.open(root)


def test_open_folder_that_is_not_a_library(root):
    root.mkdir()

    with pytest.raises(NotALibraryError):
        Library.open(root)

    assert list(root.iterdir()) == []


@pytest.mark.parametrize('manifest', ['{broken', '{}', '{"format": "x", "id": "1", "created_at": "2026-01-01"}'])
def test_open_with_damaged_manifest(root, manifest):
    root.mkdir()
    (root / 'library.json').write_text(manifest, encoding='utf-8')

    with pytest.raises(NotALibraryError):
        Library.open(root)


def test_library_opens_once_at_a_time(library, root):
    with pytest.raises(LibraryLockedError):
        Library.open(root)

    library.close()

    reopened = Library.open(root)
    assert reopened.id == library.id
    reopened.close()


def test_open_refuses_a_newer_folder_format(library, root):
    library.close()
    manifest = json.loads((root / 'library.json').read_text(encoding='utf-8'))
    manifest['format'] = FORMAT_VERSION + 1
    (root / 'library.json').write_text(json.dumps(manifest), encoding='utf-8')

    with pytest.raises(LibraryTooNewError):
        Library.open(root)


def test_open_refuses_a_newer_database_schema(library, root):
    with library.session() as session:
        session.execute(text("UPDATE alembic_version SET version_num = 'from-the-future'"))
        session.commit()
    library.close()

    with pytest.raises(LibraryTooNewError):
        Library.open(root)

    # The failed attempt must not leave the library locked.
    lock = LibraryLock(root)
    lock.acquire()
    lock.release()


def test_data_survives_reopening(library, root):
    paid = datetime(2026, 9, 30, 21, 15, tzinfo=timezone(timedelta(hours=3)))
    with library.session() as session:
        session.add(make_project(last_paid=paid, raw_json={'owner': {'name': 'Автор'}}))
        session.commit()
    library.close()

    reopened = Library.open(root)
    with reopened.session() as session:
        project = session.get(Project, 7)
        stored_mode = session.execute(text('SELECT media_mode_video FROM project')).scalar_one()
    reopened.close()

    assert project.title == 'Проект'
    assert project.added_via is AddedVia.SUBSCRIPTION
    assert project.sync_enabled is True
    assert project.video_quality is None
    assert project.raw_json == {'owner': {'name': 'Автор'}}
    # Stored as UTC, read back aware.
    assert project.last_paid == paid
    assert project.last_paid.tzinfo is UTC
    # Enums are stored by value, so the data stays readable without the Python names.
    assert stored_mode == 'manual'


def test_naive_datetimes_are_rejected(library):
    with library.session() as session:
        session.add(make_project(last_paid=datetime(2026, 9, 30, 21, 15)))  # noqa: DTZ001

        with pytest.raises(Exception, match='naive datetime'):
            session.commit()


def test_foreign_keys_are_enforced(library):
    with library.session() as session:
        session.add(Level(id=1, project_id=404, name='Нет такого проекта'))

        with pytest.raises(IntegrityError):
            session.commit()


def test_deleting_a_project_deletes_its_levels(library):
    with library.session() as session:
        session.add(make_project())
        session.add(Level(id=1, project_id=7, name='Базовый', price=300))
        session.commit()

        session.execute(text('DELETE FROM project WHERE id = 7'))
        session.commit()

        assert session.execute(text('SELECT count(*) FROM level')).scalar_one() == 0
