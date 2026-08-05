import os
import sys
import tempfile

APP_NAME = 'SerialBinSender'

# 帧格式：帧头 + 字节数(2) + 命令(1) + 数据(N) + CRC32(4)
# 字节数 = 命令(1) + 数据(N) + CRC32(4)
FRAME_HEADER = b'\xAA\x55'
LENGTH_SIZE = 2
CMD_SIZE = 1
CRC_SIZE = 4
HEADER_SIZE = len(FRAME_HEADER)

# 串口参数
BAUDRATE = 115200
READ_TIMEOUT_S = 1.0
WRITE_TIMEOUT_S = 2.0

# 主机命令
CMD_A5 = 0xA5  # 主机申请下发字节数 N
CMD_5A = 0x5A  # 从机回复收到
CMD_A6 = 0xA6  # 主机申请 bin 文件信息（长度/总包数/CRC32）
CMD_6A = 0x6A  # 从机回复 bin 文件信息
CMD_A7 = 0xA7  # 主机申请第 x 个 bin 数据包
CMD_7A = 0x7A  # 从机发送第 x 个 bin 数据包

# 6A 数据段：文件长度(4) + 总包数(4) + CRC32(4)
A6_INFO_SIZE = 12

# 5A 回复状态
A5_ACK_OK = 0xA5   # N 正常，已收到
A5_ACK_ERR = 0x00  # N 异常（>512 或 ==0）

# N 的范围：0 < N < 513
MIN_PACKET_SIZE = 1
MAX_PACKET_SIZE = 512

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
