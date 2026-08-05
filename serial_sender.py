import os
import struct
import threading
import time
from typing import Callable, Dict, Optional

import serial

from config import (
    BAUDRATE, READ_TIMEOUT_S, WRITE_TIMEOUT_S,
    FRAME_HEADER, HEADER_SIZE, LENGTH_SIZE, CMD_SIZE, CRC_SIZE,
    CMD_A5, CMD_A6, CMD_A7, A5_ACK_OK, A5_ACK_ERR,
    MIN_PACKET_SIZE, MAX_PACKET_SIZE,
)
from logger import get_logger
from protocol import (
    parse_frame, pack_5a_ack, pack_6a_response, pack_7a_response,
    parse_a5_data, parse_a6_data, parse_a7_data, calc_crc,
)


class SerialSender:
    """
    从机模式：监听串口，响应主机 A5 / A6 / A7 命令。

    交互流程：
      1. 主机发 A5 命令申请数据包字节数 N
      2. 从机回复 5A（0xA5 正常 / 0x00 异常），并预先把 bin 文件分成 N 字节一包
      3. 主机发 A6 命令申请文件信息
      4. 从机回复 6A：文件长度 + 总包数 + CRC32（针对原始 bin）
      5. 主机发 A7 命令申请第 x 包
      6. 从机回复 7A，包含 x + 该包数据
    """

    def __init__(self) -> None:
        self.ser: Optional[serial.Serial] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._port_lock = threading.Lock()
        self._logger = get_logger(__name__)

        self._buffer = b''
        self._packet_size = 0
        self._bin_data = b''
        self._packets: list[bytes] = []
        self._callbacks: Dict[str, Optional[Callable]] = {}

    def set_callbacks(
        self,
        on_command: Optional[Callable[[str], None]] = None,
        on_response: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._callbacks['on_command'] = on_command
        self._callbacks['on_response'] = on_response
        self._callbacks['on_error'] = on_error

    def open(self, port: str, baudrate: int = BAUDRATE,
             write_timeout: float = WRITE_TIMEOUT_S) -> None:
        with self._port_lock:
            self.ser = serial.Serial(
                port, baudrate, bytesize=8, parity='N', stopbits=1,
                timeout=READ_TIMEOUT_S, write_timeout=write_timeout,
            )
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
        )
        self._thread.start()
        self._logger.info(f'串口已打开: {port} @ {baudrate}')

    def close(self) -> None:
        self._stop_event.set()
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

        with self._port_lock:
            ser = self.ser
            self.ser = None
        if ser is not None and ser.is_open:
            try:
                ser.close()
            except Exception:
                self._logger.debug('关闭串口时异常', exc_info=True)
            self._logger.info('串口已关闭')

    def is_open(self) -> bool:
        ser = self.ser
        return ser is not None and ser.is_open

    def is_listening(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def load_bin(self, file_path: str) -> None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f'文件不存在: {file_path}')
        with open(file_path, 'rb') as f:
            self._bin_data = f.read()
        self._split_packets()
        self._logger.info(f'加载 bin 文件: {file_path} ({len(self._bin_data)} bytes)')

    def _split_packets(self) -> None:
        """根据当前 packet_size 把 bin 文件分包。"""
        if not self._bin_data or self._packet_size <= 0:
            self._packets = []
            return

        self._packets = []
        for i in range(0, len(self._bin_data), self._packet_size):
            chunk = self._bin_data[i:i + self._packet_size]
            if len(chunk) < self._packet_size:
                chunk += b'\xFF' * (self._packet_size - len(chunk))
            self._packets.append(chunk)

    def _listen_loop(self) -> None:
        """后台线程：持续读取串口并处理帧。"""
        while not self._stop_event.is_set():
            try:
                ser = self.ser
                if ser is None or not ser.is_open:
                    break

                available = ser.in_waiting
                if available > 0:
                    data = ser.read(available)
                    if data:
                        self._buffer += data
                        self._process_buffer()
                else:
                    time.sleep(0.01)
            except serial.SerialException as e:
                self._logger.exception('串口异常')
                self._safe_callback('on_error', f'串口异常: {e}')
                break
            except Exception as e:
                self._logger.exception('监听循环异常')
                self._safe_callback('on_error', f'监听异常: {e}')

    def _process_buffer(self) -> None:
        """从缓冲区中解析完整帧并处理。"""
        while True:
            if self._stop_event.is_set():
                break

            idx = self._buffer.find(FRAME_HEADER)
            if idx == -1:
                self._buffer = b''
                break

            # 丢弃帧头之前的垃圾数据
            self._buffer = self._buffer[idx:]

            min_body = LENGTH_SIZE + CMD_SIZE + CRC_SIZE
            if len(self._buffer) < HEADER_SIZE + min_body:
                break

            length = struct.unpack(
                '<H', self._buffer[HEADER_SIZE:HEADER_SIZE + LENGTH_SIZE]
            )[0]
            expected_total = HEADER_SIZE + LENGTH_SIZE + length

            if len(self._buffer) < expected_total:
                break

            frame = self._buffer[:expected_total]
            self._buffer = self._buffer[expected_total:]

            try:
                _, cmd, data = parse_frame(frame)
                self._handle_command(cmd, data)
            except Exception as e:
                self._logger.warning(f'帧解析失败: {e}')
                self._safe_callback('on_error', f'帧解析失败: {e}')

    def _handle_command(self, cmd: int, data: bytes) -> None:
        if cmd == CMD_A5:
            self._handle_a5(data)
        elif cmd == CMD_A6:
            self._handle_a6(data)
        elif cmd == CMD_A7:
            self._handle_a7(data)
        else:
            self._logger.warning(f'收到未知命令: 0x{cmd:02X}')
            self._safe_callback('on_error', f'未知命令: 0x{cmd:02X}')

    def _handle_a5(self, data: bytes) -> None:
        """处理主机申请 N 个数据的请求。"""
        try:
            n = parse_a5_data(data)
        except Exception as e:
            self._write_frame(pack_5a_ack(A5_ACK_ERR))
            self._safe_callback('on_error', f'A5 数据解析失败: {e}')
            return

        if MIN_PACKET_SIZE <= n <= MAX_PACKET_SIZE:
            self._packet_size = n
            self._split_packets()
            self._write_frame(pack_5a_ack(A5_ACK_OK))
            self._safe_callback(
                'on_command',
                f'A5 申请 N={n}, 已分 {len(self._packets)} 包, 回复 5A=0x{A5_ACK_OK:02X}'
            )
        else:
            self._write_frame(pack_5a_ack(A5_ACK_ERR))
            self._safe_callback(
                'on_command',
                f'A5 申请 N={n}, 越界, 回复 5A=0x{A5_ACK_ERR:02X}'
            )

    def _handle_a6(self, data: bytes) -> None:
        """处理主机申请 bin 文件信息的请求。"""
        try:
            parse_a6_data(data)
        except Exception as e:
            self._safe_callback('on_error', f'A6 数据解析失败: {e}')
            return

        if not self._bin_data:
            self._safe_callback('on_error', 'A6 请求前 bin 未加载')
            return

        if self._packet_size <= 0 or not self._packets:
            self._safe_callback('on_error', 'A6 请求前未收到有效 A5，无法确定总包数')
            return

        file_size = len(self._bin_data)
        packet_count = len(self._packets)
        file_crc = calc_crc(self._bin_data)
        self._write_frame(pack_6a_response(file_size, packet_count, file_crc))
        self._safe_callback(
            'on_response',
            f'6A 回复: 文件长度={file_size}, 总包数={packet_count}, CRC32=0x{file_crc:08X}'
        )

    def _handle_a7(self, data: bytes) -> None:
        """处理主机申请第 x 个数据包的请求。"""
        try:
            x = parse_a7_data(data)
        except Exception as e:
            self._safe_callback('on_error', f'A7 数据解析失败: {e}')
            return

        if not self._packets:
            self._safe_callback('on_error', 'A7 请求前未收到 A5 或 bin 未加载')
            return

        if not (0 <= x < len(self._packets)):
            self._safe_callback('on_error', f'A7 请求序号 {x} 越界 (共 {len(self._packets)} 包)')
            return

        self._write_frame(pack_7a_response(x, self._packets[x]))
        self._safe_callback('on_response', f'7A 发送第 {x} 包 ({len(self._packets[x])} bytes)')

    def _write_frame(self, frame: bytes) -> None:
        """线程安全地写入一帧。"""
        ser = None
        with self._port_lock:
            if self.ser is not None and self.ser.is_open:
                ser = self.ser
        if ser is not None:
            ser.write(frame)

    def _safe_callback(self, name: str, message: str) -> None:
        callback = self._callbacks.get(name)
        if callback is None:
            return
        try:
            callback(message)
        except Exception:
            self._logger.exception(f'{name} 回调执行失败')
