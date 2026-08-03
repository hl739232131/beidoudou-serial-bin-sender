import os
import logging
import config
from logger import get_logger


def close_handlers(logger: logging.Logger) -> None:
    """关闭并移除处理器，避免 Windows 上文件句柄未释放导致临时目录无法清理。"""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_log_directory_created(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'LOG_FILE', str(tmp_path / 'logs' / 'test.log'))
    logger = get_logger('test_log_dir')
    try:
        logger.info('hello')
        assert os.path.exists(tmp_path / 'logs')
        assert os.path.exists(tmp_path / 'logs' / 'test.log')
    finally:
        close_handlers(logger)


def test_logger_falls_back_to_console(tmp_path, monkeypatch):
    # 把日志文件路径指向一个已存在的文件的子路径，makedirs/FileHandler 必然失败
    blocker = tmp_path / 'blocker'
    blocker.write_text('not a directory')
    monkeypatch.setattr(config, 'LOG_FILE', str(blocker / 'logs' / 'test.log'))

    logger = get_logger('test_logger_fallback')
    try:
        logger.info('hello')
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
        assert not isinstance(logger.handlers[0], logging.FileHandler)
    finally:
        close_handlers(logger)


def test_logger_has_handlers():
    logger = get_logger('test_handlers')
    try:
        assert len(logger.handlers) > 0
        assert logger.level == logging.INFO
    finally:
        close_handlers(logger)
