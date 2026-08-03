import os
import threading
from typing import Callable, Optional

import serial

from config import BAUDRATE, FRAME_SIZE, INTERVAL_MS, READ_TIMEOUT_S, WRITE_TIMEOUT_S
from logger import get_logger
from protocol import pack_frame

ProgressCallback = Optional[Callable[[int, int], None]]
LogCallback = Optional[Callable[[str], None]]
FinishedCallback = Optional[Callable[[bool, str], None]]


class SerialSender:
    def __init__(self) -> None:
        self.ser: Optional[serial.Serial] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # 保护 self.ser，避免关闭串口与写入串口相互穿插
        self._port_lock = threading.Lock()
        self._logger = get_logger(__name__)

    def open(self, port: str, baudrate: int = BAUDRATE,
             write_timeout: float = WRITE_TIMEOUT_S) -> None:
        with self._port_lock:
            self.ser = serial.Serial(
                port, baudrate, bytesize=8, parity='N', stopbits=1,
                timeout=READ_TIMEOUT_S, write_timeout=write_timeout,
            )
        self._logger.info(f'串口已打开: {port} @ {baudrate}')

    def close(self) -> None:
        self.stop()
        with self._port_lock:
            if self.ser is not None and self.ser.is_open:
                self.ser.close()
                self._logger.info('串口已关闭')
            self.ser = None

    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def is_sending(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def send_bin(self, file_path: str, on_progress: ProgressCallback = None,
                 on_log: LogCallback = None,
                 on_finished: FinishedCallback = None) -> None:
        if not self.is_open():
            raise RuntimeError('串口未打开')

        if not os.path.exists(file_path):
            raise FileNotFoundError(f'文件不存在: {file_path}')

        if self.is_sending():
            raise RuntimeError('发送正在进行中')

        # 上一次的线程已结束，回收句柄后再启动新线程
        self._thread = None
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._send_loop,
            args=(file_path, on_progress, on_log, on_finished),
            daemon=True,
        )
        self._thread.start()

    def _safe_call(self, callback, *args) -> None:
        """回调由调用方提供，其异常不应影响发送流程的错误判定。"""
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            self._logger.exception('回调执行失败')

    def _write_frame(self, frame: bytes) -> bool:
        """写入一帧；若期间已请求停止或串口被关闭则返回 False。"""
        with self._port_lock:
            if self._stop_event.is_set():
                return False
            if self.ser is None or not self.ser.is_open:
                raise RuntimeError('串口已关闭')
            self.ser.write(frame)
        return True

    def _send_loop(self, file_path: str, on_progress: ProgressCallback,
                   on_log: LogCallback, on_finished: FinishedCallback) -> None:
        sent_bytes = 0
        total_size = 0
        success = False
        message = ''
        try:
            total_size = os.path.getsize(file_path)
            start_message = f'开始发送: {file_path} ({total_size} bytes)'
            self._logger.info(start_message)
            self._safe_call(on_log, start_message)

            stopped = False
            with open(file_path, 'rb') as f:
                while not stopped:
                    if self._stop_event.is_set():
                        stopped = True
                        break

                    chunk = f.read(FRAME_SIZE)
                    if not chunk:
                        break

                    if not self._write_frame(pack_frame(chunk)):
                        stopped = True
                        break

                    sent_bytes += len(chunk)
                    self._safe_call(on_progress, sent_bytes, total_size)
                    self._safe_call(on_log, f'已发送 {sent_bytes}/{total_size} bytes')

                    if len(chunk) == FRAME_SIZE and self._stop_event.wait(INTERVAL_MS / 1000.0):
                        stopped = True

            success = not stopped
            if stopped:
                message = f'发送已停止: {sent_bytes}/{total_size} bytes'
            else:
                message = f'发送完成: {sent_bytes}/{total_size} bytes'
            self._logger.info(message)
            self._safe_call(on_log, message)
        except serial.SerialTimeoutException as e:
            success = False
            message = f'发送超时: {e}'
            self._logger.exception(f'发送超时，已发送 {sent_bytes}/{total_size} bytes')
            self._safe_call(on_log, message)
        except Exception as e:
            success = False
            message = f'发送失败: {e}'
            self._logger.exception(f'发送异常，已发送 {sent_bytes}/{total_size} bytes')
            self._safe_call(on_log, message)
        finally:
            self._safe_call(on_finished, success, message)

    def stop(self) -> None:
        """请求停止发送，立即返回；发送线程会通过 on_finished 上报结果。"""
        if self.is_sending():
            self._logger.info('已请求停止发送')
        self._stop_event.set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """等待发送线程结束；仅在确实结束后才释放线程句柄。"""
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        if thread.is_alive():
            return False
        if self._thread is thread:
            self._thread = None
        return True
