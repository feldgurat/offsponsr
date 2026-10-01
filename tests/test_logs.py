import logging

from offsponsr.config import CONFIG_DIR_ENV
from offsponsr.logs import setup_logging


def test_log_goes_to_a_file_in_the_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path / 'config'))
    root = logging.getLogger()
    before = root.handlers[:], root.level
    try:
        path = setup_logging()
        logging.getLogger('offsponsr.test').info('Привет из теста')
        for handler in root.handlers:
            handler.close()
    finally:
        # Put pytest's own handlers back.
        root.handlers[:], root.level = before[0], before[1]

    assert path == tmp_path / 'config' / 'offsponsr.log'
    assert 'INFO offsponsr.test: Привет из теста' in path.read_text(encoding='utf-8')
