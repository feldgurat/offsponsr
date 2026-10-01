from pathlib import Path

from offsponsr.config import CONFIG_DIR_ENV, AppConfig, ConfigStore, user_config_dir


def test_missing_config_is_default(config_store):
    assert config_store.load() == AppConfig(library_path=None)


def test_config_round_trip(config_store):
    config_store.save(AppConfig(library_path='D:/Книги/offsponsr'))

    assert config_store.load() == AppConfig(library_path='D:/Книги/offsponsr')
    assert not config_store.path.with_name('config.json.tmp').exists()


def test_damaged_config_is_default(config_store):
    config_store.path.parent.mkdir(parents=True)

    for damaged in ('{not json', '[]', '{"library_path": 5}'):
        config_store.path.write_text(damaged, encoding='utf-8')

        assert config_store.load() == AppConfig(library_path=None)


def test_config_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path))

    assert user_config_dir() == tmp_path
    assert ConfigStore().path == tmp_path / 'config.json'


def test_config_dir_default(monkeypatch):
    monkeypatch.delenv(CONFIG_DIR_ENV, raising=False)

    directory = user_config_dir()

    assert directory.name == 'offsponsr'
    assert directory.is_absolute()
    assert isinstance(directory, Path)
