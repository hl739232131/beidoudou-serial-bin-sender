import logging
import os
import config


def _make_file_handler(formatter: logging.Formatter):
    """创建文件日志处理器；目录不可写时返回 None，让程序退化为仅控制台日志。"""
    try:
        log_dir = os.path.dirname(config.LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handler = logging.FileHandler(config.LOG_FILE, encoding='utf-8')
    except OSError:
        return None
    handler.setFormatter(formatter)
    return handler


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, config.DEFAULT_LOG_LEVEL, logging.INFO))

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = _make_file_handler(formatter)
    if file_handler is not None:
        logger.addHandler(file_handler)
    else:
        logger.warning(f'无法写入日志文件 {config.LOG_FILE}，仅输出到控制台')

    return logger
