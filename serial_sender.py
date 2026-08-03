import os
import threading
import time
import serial
from config import BAUDRATE, INTERVAL_MS, FRAME_SIZE
from logger import get_logger
from protocol import pack_frame


class SerialSender:
    def __init__(self):
        self.ser = None
        self._stop_event = threading.Event()
        self._thread = None
        self._logger = get_logger(__name__)

    def open(self, port: str, baudrate: int = BAUDRATE) -> None:
        self.ser = serial.Serial(port, baudrate, bytesize=8, parity='N', stopbits=1, timeout=1)
        self._logger.info(f'串口已打开: {port} @ {baudrate}')

    def close(self) -> None:
        self.stop()
        if self.ser and self.ser.is_open:
            self.ser.close()
            self._logger.info('串口已关闭')
        self.ser = None

    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def send_bin(self, file_path: str, on_progress=None, on_log=None) -> None:
        if not self.is_open():
            raise RuntimeError('串口未打开')

        if not os.path.exists(file_path):
            raise FileNotFoundError(f'文件不存在: {file_path}')

        if self._thread and self._thread.is_alive():
            raise RuntimeError('发送正在进行中')

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._send_loop,
            args=(file_path, on_progress, on_log),
            daemon=True,
        )
        self._thread.start()

    def _send_loop(self, file_path: str, on_progress, on_log) -> None:
        total_size = os.path.getsize(file_path)
        sent_bytes = 0
        self._logger.info(f'开始发送: {file_path} ({total_size} bytes)')
        if on_log:
            on_log(f'开始发送: {file_path} ({total_size} bytes)')

        stopped = False
        with open(file_path, 'rb') as f:
            while True:
                if self._stop_event.is_set():
                    stopped = True
                    self._logger.info('发送被用户停止')
                    if on_log:
                        on_log('发送已停止')
                    break

                chunk = f.read(FRAME_SIZE)
                if not chunk:
                    break

                frame = pack_frame(chunk)
                self.ser.write(frame)
                sent_bytes += len(chunk)

                if on_progress:
                    on_progress(sent_bytes, total_size)
                if on_log:
                    on_log(f'已发送 {sent_bytes}/{total_size} bytes')

                if len(chunk) == FRAME_SIZE:
                    time.sleep(INTERVAL_MS / 1000.0)

        if not stopped:
            self._logger.info(f'发送完成: {sent_bytes}/{total_size} bytes')
            if on_log:
                on_log(f'发送完成: {sent_bytes}/{total_size} bytes')

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
