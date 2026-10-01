import shutil

from fastapi.testclient import TestClient

from offsponsr.api import create_app
from offsponsr.library import Library, LibraryManager

from .conftest import LAUNCH_TOKEN


def test_library_api_requires_session(client):
    assert client.get('/api/library').status_code == 401
    assert client.post('/api/library/create', json={'path': 'x'}).status_code == 401
    assert client.post('/api/library/open', json={'path': 'x'}).status_code == 401
    assert client.post('/api/dialogs/folder').status_code == 401


def test_no_library_on_first_run(session_client):
    assert session_client.get('/api/library').json() == {'library': None, 'last_failure': None}


def test_folder_dialog(session_client, folder_picker, tmp_path):
    assert session_client.post('/api/dialogs/folder').json() == {'path': None}

    folder_picker.choice = tmp_path / 'chosen'

    assert session_client.post('/api/dialogs/folder').json() == {'path': str(tmp_path / 'chosen')}


def test_create_library(session_client, libraries, tmp_path):
    root = tmp_path / 'library'

    response = session_client.post('/api/library/create', json={'path': str(root)})

    assert response.status_code == 200
    assert response.json() == {'id': libraries.current.id, 'path': str(root)}
    assert session_client.get('/api/library').json() == {'library': response.json(), 'last_failure': None}


def test_create_library_in_a_folder_with_files(session_client, libraries, tmp_path):
    (tmp_path / 'file.txt').write_text('x', encoding='utf-8')

    response = session_client.post('/api/library/create', json={'path': str(tmp_path)})

    assert response.status_code == 409
    assert response.json() == {'code': 'not_empty', 'path': str(tmp_path)}
    assert libraries.current is None


def test_open_library(session_client, tmp_path):
    root = tmp_path / 'library'
    Library.create(root).close()

    response = session_client.post('/api/library/open', json={'path': str(root)})

    assert response.status_code == 200
    assert response.json()['path'] == str(root)


def test_open_a_folder_that_is_not_a_library(session_client, tmp_path):
    response = session_client.post('/api/library/open', json={'path': str(tmp_path)})

    assert response.status_code == 409
    assert response.json()['code'] == 'not_a_library'


def test_status_reports_why_the_last_library_did_not_open(config_store, folder_picker, web_dir, tmp_path):
    first_run = LibraryManager(config_store)
    root = first_run.create(tmp_path / 'library').root
    first_run.close()
    shutil.rmtree(root)

    libraries = LibraryManager(config_store)
    libraries.open_last()
    client = TestClient(create_app(LAUNCH_TOKEN, libraries, folder_picker, web_dir), base_url='http://127.0.0.1')
    client.post('/api/session', json={'token': LAUNCH_TOKEN})

    assert client.get('/api/library').json() == {
        'library': None,
        'last_failure': {'path': str(root), 'code': 'missing'},
    }
