from pathlib import Path

import pytest

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


def test_interface_settings_round_trip(config_store):
    config_store.save(AppConfig(theme='dark', feed_view='list', hide_closed=True))

    assert config_store.load() == AppConfig(theme='dark', feed_view='list', hide_closed=True)


def test_unknown_and_bad_settings_fall_back_to_defaults(config_store):
    config_store.path.parent.mkdir(parents=True)
    config_store.path.write_text(
        '{"library_path": "D:/x", "theme": "pink", "feed_view": 3, "hide_closed": "yes", "from_the_future": 1}',
        encoding='utf-8',
    )

    assert config_store.load() == AppConfig(library_path='D:/x')


def test_update_changes_only_what_is_named(config_store):
    config_store.save(AppConfig(library_path='D:/x', theme='dark'))

    updated = config_store.update(feed_view='tile')

    assert updated == AppConfig(library_path='D:/x', theme='dark', feed_view='tile')
    assert config_store.load() == updated


def test_ffmpeg_path_is_kept_and_can_be_taken_back(config_store):
    config_store.update(ffmpeg_path='C:/tools/ffmpeg.exe')
    assert config_store.load() == AppConfig(ffmpeg_path='C:/tools/ffmpeg.exe')

    assert config_store.update(ffmpeg_path=None) == AppConfig()

    with pytest.raises(ValueError, match='ffmpeg_path'):
        config_store.update(ffmpeg_path=5)


def test_update_refuses_bad_values(config_store):
    with pytest.raises(ValueError, match='theme'):
        config_store.update(theme='pink')

    assert config_store.load() == AppConfig()
