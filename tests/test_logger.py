import os
import logging
import config
import logger as logger_module
from logger import get_log_file_path, get_logger


def close_handlers(logger: logging.Logger) -> None:
    """关闭并移除处理器，避免 Windows 上文件句柄未释放导致临时目录无法清理。"""
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def blocked_path(tmp_path, name: str) -> str:
    """指向一个已存在普通文件的子路径，makedirs/FileHandler 必然失败。"""
    blocker = tmp_path / name
    blocker.write_text('not a directory')
    return str(blocker / 'logs' / 'test.log')


def test_log_directory_created(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'LOG_FILE', str(tmp_path / 'logs' / 'test.log'))
    logger = get_logger('test_log_dir')
    try:
        logger.info('hello')
        assert os.path.exists(tmp_path / 'logs')
        assert os.path.exists(tmp_path / 'logs' / 'test.log')
        assert get_log_file_path() == str(tmp_path / 'logs' / 'test.log')
    finally:
        close_handlers(logger)


def test_logger_falls_back_to_second_location(tmp_path, monkeypatch):
    """主日志目录不可写时（如 --windowed 打包后装在只读目录），应改用备选目录。"""
    monkeypatch.setattr(config, 'LOG_FILE', blocked_path(tmp_path, 'blocker'))
    fallback = str(tmp_path / 'fallback' / 'test.log')
    monkeypatch.setattr(config, 'fallback_log_files', lambda: [fallback])

    logger = get_logger('test_logger_fallback_file')
    try:
        logger.info('hello')
        assert any(isinstance(h, logging.FileHandler) for h in logger.handlers)
        assert os.path.exists(fallback)
        assert get_log_file_path() == fallback
    finally:
        close_handlers(logger)


def test_logger_falls_back_to_console(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'LOG_FILE', blocked_path(tmp_path, 'blocker'))
    monkeypatch.setattr(
        config, 'fallback_log_files',
        lambda: [blocked_path(tmp_path, 'blocker2')],
    )
    monkeypatch.setattr(logger_module, '_log_file_path', None)

    logger = get_logger('test_logger_fallback')
    try:
        logger.info('hello')
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], logging.StreamHandler)
        assert not isinstance(logger.handlers[0], logging.FileHandler)
        assert get_log_file_path() is None
    finally:
        close_handlers(logger)


def test_logger_without_stdstreams_still_writes_file(tmp_path, monkeypatch):
    """PyInstaller --windowed 下 sys.stdout/stderr 为 None，日志必须仍落到文件。"""
    monkeypatch.setattr(config, 'LOG_FILE', str(tmp_path / 'windowed' / 'test.log'))
    monkeypatch.setattr(logger_module.sys, 'stdout', None)
    monkeypatch.setattr(logger_module.sys, 'stderr', None)

    logger = get_logger('test_logger_windowed')
    try:
        logger.info('hello')
        handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(handlers) == 1
        assert not any(
            type(h) is logging.StreamHandler for h in logger.handlers
        )
        handlers[0].flush()
        assert 'hello' in (tmp_path / 'windowed' / 'test.log').read_text(encoding='utf-8')
    finally:
        close_handlers(logger)


def test_logger_has_handlers():
    logger = get_logger('test_handlers')
    try:
        assert len(logger.handlers) > 0
        assert logger.level == logging.INFO
    finally:
        close_handlers(logger)
