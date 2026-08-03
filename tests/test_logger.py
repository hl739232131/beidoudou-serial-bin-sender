import os
import logging
import config
from logger import get_logger


def test_log_directory_created(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'LOG_FILE', str(tmp_path / 'logs' / 'test.log'))
    logger = get_logger('test_log_dir')
    logger.info('hello')
    assert os.path.exists(tmp_path / 'logs')


def test_logger_has_handlers():
    logger = get_logger('test_handlers')
    assert len(logger.handlers) > 0
    assert logger.level == logging.INFO
