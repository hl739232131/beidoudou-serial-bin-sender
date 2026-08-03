import os
import threading
from enum import Enum
from typing import Callable, Optional

import serial

from config import BAUDRATE, FRAME_SIZE, INTERVAL_MS, READ_TIMEOUT_S, WRITE_TIMEOUT_S
from logger import get_logger
from protocol import pack_frame


class SendResult(Enum):
    """发送结束的三种状态，供 UI 区分「正常结束」「用户中断」「出错」。"""
    COMPLETED = 'completed'
    STOPPED = 'stopped'
    FAILED = 'failed'

    @property
    def is_error(self) -> bool:
        return self is SendResult.FAILED


ProgressCallback = Callable[[int, int], None]
LogCallback = Callable[[str], None]
FinishedCallback = Callable[[SendResult, str], None]


class SerialSender:
    def __init__(self) -> None:
        self.ser: Optional[serial.Serial] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # 保护 self.ser 这个引用本身，不覆盖阻塞的 write 调用
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
            ser = self.ser
            self.ser = None
        # close() 由 GUI 线程调用，锁外执行避免与发送线程的 write 相互等待
        if ser is not None and ser.is_open:
            ser.close()
            self._logger.info('串口已关闭')

    def is_open(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def is_sending(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def send_bin(self, file_path: str,
                 on_progress: Optional[ProgressCallback] = None,
                 on_log: Optional[LogCallback] = None,
                 on_finished: Optional[FinishedCallback] = None) -> None:
        if not self.is_open():
            raise RuntimeError('串口未打开')

        if not os.path.exists(file_path):
            raise FileNotFoundError(f'文件不存在: {file_path}')

        if self.is_sending():
            raise RuntimeError('发送正在进行中')

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
            ser = self.ser
            if ser is None or not ser.is_open:
                raise RuntimeError('串口已关闭')

        # 锁外写入：write 可能阻塞到 write_timeout，不能让 close() 一起卡住
        try:
            ser.write(frame)
        except Exception:
            # 停止/关闭与写入竞争时写入失败属于正常中断，不算错误
            if self._stop_event.is_set():
                return False
            raise
        return True

    def _wait_interval(self) -> bool:
        """帧间隔等待；返回 True 表示等待期间收到了停止请求。"""
        return self._stop_event.wait(INTERVAL_MS / 1000.0)

    def _send_loop(self, file_path: str, on_progress: Optional[ProgressCallback],
                   on_log: Optional[LogCallback],
                   on_finished: Optional[FinishedCallback]) -> None:
        sent_bytes = 0
        total_size = 0
        result = SendResult.FAILED
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

                    if len(chunk) == FRAME_SIZE and self._wait_interval():
                        stopped = True

            if stopped:
                result = SendResult.STOPPED
                message = f'发送已停止: {sent_bytes}/{total_size} bytes'
            else:
                result = SendResult.COMPLETED
                message = f'发送完成: {sent_bytes}/{total_size} bytes'
            self._logger.info(message)
            self._safe_call(on_log, message)
        except serial.SerialTimeoutException as e:
            result = SendResult.FAILED
            message = f'发送超时: {e}'
            self._logger.exception(f'发送超时，已发送 {sent_bytes}/{total_size} bytes')
            self._safe_call(on_log, message)
        except Exception as e:
            result = SendResult.FAILED
            message = f'发送失败: {e}'
            self._logger.exception(f'发送异常，已发送 {sent_bytes}/{total_size} bytes')
            self._safe_call(on_log, message)
        finally:
            self._safe_call(on_finished, result, message)

    def _cancel_pending_write(self) -> None:
        """Win32 上取消阻塞中的 write，让发送线程尽快退出。"""
        ser = self.ser
        cancel_write = getattr(ser, 'cancel_write', None)
        if cancel_write is None:
            return
        try:
            cancel_write()
        except Exception:
            self._logger.debug('取消未完成的写入失败', exc_info=True)

    def stop(self) -> None:
        """请求停止发送，立即返回；发送线程会通过 on_finished 上报结果。"""
        if self.is_sending():
            self._logger.info('已请求停止发送')
        self._stop_event.set()
        self._cancel_pending_write()

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
