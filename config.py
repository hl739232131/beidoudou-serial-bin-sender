import os
import sys
import tempfile

APP_NAME = 'SerialBinSender'
FRAME_HEADER = b'\xAA\x55'
FRAME_SIZE = 128
CRC_SIZE = 4
FRAME_TOTAL_SIZE = 2 + FRAME_SIZE + CRC_SIZE
BAUDRATE = 115200
INTERVAL_MS = 50
READ_TIMEOUT_S = 1.0
WRITE_TIMEOUT_S = 2.0
DEFAULT_LOG_LEVEL = 'INFO'


def _base_dir() -> str:
    """打包成 exe 后以可执行文件所在目录为基准，否则以源码目录为基准。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE_NAME = 'serial-bin-sender.log'
LOG_FILE = os.path.join(LOG_DIR, LOG_FILE_NAME)


def fallback_log_files() -> list:
    """程序目录不可写时（如 Program Files 下的安装目录）备选的日志文件路径。"""
    dirs = []
    if sys.platform == 'win32':
        local_appdata = os.environ.get('LOCALAPPDATA')
        if local_appdata:
            dirs.append(os.path.join(local_appdata, APP_NAME))
    dirs.append(os.path.join(tempfile.gettempdir(), APP_NAME))
    return [os.path.join(d, LOG_FILE_NAME) for d in dirs]
