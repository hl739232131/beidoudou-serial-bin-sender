import logging
import os
import sys
from typing import List, Optional

import config

# 实际生效的日志文件路径；仅控制台输出时为 None
_log_file_path: Optional[str] = None


def _candidate_log_files() -> List[str]:
    candidates = [config.LOG_FILE]
    for path in config.fallback_log_files():
        if path not in candidates:
            candidates.append(path)
    return candidates


def _make_file_handler(formatter: logging.Formatter):
    """依次尝试各候选路径创建文件日志处理器；全部不可写时返回 None。"""
    global _log_file_path
    for path in _candidate_log_files():
        try:
            log_dir = os.path.dirname(path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            handler = logging.FileHandler(path, encoding='utf-8')
        except OSError:
            continue
        handler.setFormatter(formatter)
        _log_file_path = path
        return handler
    return None


def _make_console_handler(formatter: logging.Formatter):
    """--windowed 打包后 stdout/stderr 为 None，此时不要挂空的控制台处理器。"""
    if sys.stderr is None:
        return None
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    return handler


def get_log_file_path() -> Optional[str]:
    """返回当前生效的日志文件路径；若日志只写到控制台则返回 None。"""
    return _log_file_path


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, config.DEFAULT_LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    console_handler = _make_console_handler(formatter)
    if console_handler is not None:
        logger.addHandler(console_handler)

    file_handler = _make_file_handler(formatter)
    if file_handler is not None:
        logger.addHandler(file_handler)
    else:
        # 没有任何可写位置时，至少保证 logger 不会因为无处理器而向 root 冒泡
        if console_handler is None:
            logger.addHandler(logging.NullHandler())
        logger.warning(
            f'无法写入日志文件（已尝试 {"、".join(_candidate_log_files())}），仅输出到控制台'
        )

    return logger
