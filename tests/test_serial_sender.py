import os
import struct
import threading
import time
import serial
from unittest.mock import MagicMock
import pytest
import binascii
from serial_sender import SerialSender
from protocol import pack_a5_request, pack_a6_request, pack_a7_request, parse_frame, parse_6a_data
from config import CMD_5A, CMD_6A, CMD_7A, A5_ACK_OK, A5_ACK_ERR, MAX_PACKET_SIZE


class FakeSerial:
    def __init__(self, to_read=b''):
        self._to_read = to_read
        self._read_idx = 0
        self.written = b''
        self._open = True

    def read(self, size=1):
        available = len(self._to_read) - self._read_idx
        to_read = min(size, available)
        data = self._to_read[self._read_idx:self._read_idx + to_read]
        self._read_idx += to_read
        return data

    @property
    def in_waiting(self):
        return len(self._to_read) - self._read_idx

    def write(self, data):
        self.written += data

    @property
    def is_open(self):
        return self._open

    def close(self):
        self._open = False


def _wait_for_written(fake, min_bytes, timeout=2.0):
    """等待 fake 收到至少 min_bytes 字节的回复。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(fake.written) >= min_bytes:
            return True
        time.sleep(0.05)
    return False


def test_open_close(monkeypatch):
    fake = FakeSerial()
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)
    sender = SerialSender()
    sender.open('COM1')
    assert sender.is_open()
    assert sender.is_listening()
    sender.close()
    assert not sender.is_open()
    assert not sender.is_listening()


def test_a5_valid_sets_packet_size(monkeypatch, tmp_path):
    fake = FakeSerial(to_read=pack_a5_request(64))
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)

    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(b'X' * 200)

    sender = SerialSender()
    sender.load_bin(str(bin_file))
    sender.open('COM1')

    assert _wait_for_written(fake, 1)
    sender.close()

    # 第一个回复应该是 5A
    assert fake.written[0:2] == b'\xAA\x55'
    assert fake.written[4] == CMD_5A
    assert fake.written[5] == A5_ACK_OK


def test_a5_invalid_replies_zero(monkeypatch, tmp_path):
    fake = FakeSerial(to_read=pack_a5_request(600))
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)

    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(b'X' * 100)

    sender = SerialSender()
    sender.load_bin(str(bin_file))
    sender.open('COM1')

    assert _wait_for_written(fake, 1)
    sender.close()

    assert fake.written[4] == CMD_5A
    assert fake.written[5] == A5_ACK_ERR


def test_a6_returns_file_info(monkeypatch, tmp_path):
    packet_size = 64
    bin_data = b'ABCDEFGH' * 30  # 240 bytes -> 4 packets
    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(bin_data)

    a5_frame = pack_a5_request(packet_size)
    a6_frame = pack_a6_request()
    fake = FakeSerial(to_read=a5_frame + a6_frame)
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)

    sender = SerialSender()
    sender.load_bin(str(bin_file))
    sender.open('COM1')

    assert _wait_for_written(fake, 20)
    time.sleep(0.2)
    sender.close()

    # 依次解析回复帧，找到 6A（避免 CRC 字节中的 0x6A 被误匹配）
    buf = fake.written
    found = None
    while buf:
        idx = buf.find(b'\xAA\x55')
        if idx < 0:
            break
        buf = buf[idx:]
        if len(buf) < 5:
            break
        length = struct.unpack('<H', buf[2:4])[0]
        total = 2 + 2 + length
        if len(buf) < total:
            break
        frame = buf[:total]
        buf = buf[total:]
        _, cmd, data = parse_frame(frame)
        if cmd == CMD_6A:
            found = data
            break

    assert found is not None, f'未找到 6A 回复: {fake.written.hex()}'
    file_size, packet_count, file_crc = parse_6a_data(found)
    assert file_size == len(bin_data)
    assert packet_count == 4
    assert file_crc == (binascii.crc32(bin_data) & 0xFFFFFFFF)


def test_a6_without_a5_reports_error(monkeypatch, tmp_path):
    fake = FakeSerial(to_read=pack_a6_request())
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)

    on_error = MagicMock()
    sender = SerialSender()
    sender.set_callbacks(on_error=on_error)
    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(b'X' * 100)
    sender.load_bin(str(bin_file))
    sender.open('COM1')

    time.sleep(0.3)
    sender.close()

    assert on_error.called
    assert CMD_6A not in fake.written


def test_a5_and_a7_emit_progress(monkeypatch, tmp_path):
    packet_size = 32
    bin_data = bytes(range(96))  # 3 packets
    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(bin_data)

    a5_frame = pack_a5_request(packet_size)
    a7_frame = pack_a7_request(1)
    fake = FakeSerial(to_read=a5_frame + a7_frame)
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)

    progress_calls = []
    sender = SerialSender()
    sender.set_callbacks(on_progress=lambda cur, total, n: progress_calls.append((cur, total, n)))
    sender.load_bin(str(bin_file))
    sender.open('COM1')

    assert _wait_for_written(fake, 20)
    time.sleep(0.2)
    sender.close()

    assert (None, 3, packet_size) in progress_calls
    assert (1, 3, packet_size) in progress_calls


def test_a7_returns_requested_packet(monkeypatch, tmp_path):
    packet_size = 32
    bin_data = bytes(range(256))  # 0x00..0xFF
    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(bin_data)

    # 主机先发 A5 设置 N，再发 A7 要第 2 包
    a5_frame = pack_a5_request(packet_size)
    a7_frame = pack_a7_request(2)
    fake = FakeSerial(to_read=a5_frame + a7_frame)
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)

    on_response = MagicMock()
    sender = SerialSender()
    sender.set_callbacks(on_response=on_response)
    sender.load_bin(str(bin_file))
    sender.open('COM1')

    # 等 A5 回复 + A7 回复都完成
    assert _wait_for_written(fake, 20)
    time.sleep(0.2)
    sender.close()

    # 找到 7A 回复的位置
    assert CMD_7A in fake.written
    idx_7a = fake.written.index(CMD_7A)
    # 7A 帧：AA 55 + length(2) + cmd(1) + data(4 + 32) + crc(4)
    response = fake.written[idx_7a - 3:idx_7a - 3 + 3 + 1 + 4 + 32 + 4]
    # 数据段从 cmd 后开始
    x = struct.unpack('<I', response[3 + 1:3 + 1 + 4])[0]
    payload = response[3 + 1 + 4:3 + 1 + 4 + 32]
    assert x == 2
    assert payload == bin_data[64:96]


def test_a7_without_a5_reports_error(monkeypatch, tmp_path):
    fake = FakeSerial(to_read=pack_a7_request(0))
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)

    on_error = MagicMock()
    sender = SerialSender()
    sender.set_callbacks(on_error=on_error)
    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(b'X' * 100)
    sender.load_bin(str(bin_file))
    sender.open('COM1')

    time.sleep(0.3)
    sender.close()

    assert on_error.called
    assert not fake.written  # 不应回复 7A


def test_a7_out_of_range_reports_error(monkeypatch, tmp_path):
    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(b'X' * 100)

    a5_frame = pack_a5_request(64)
    a7_frame = pack_a7_request(9999)
    fake = FakeSerial(to_read=a5_frame + a7_frame)
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)

    on_error = MagicMock()
    sender = SerialSender()
    sender.set_callbacks(on_error=on_error)
    sender.load_bin(str(bin_file))
    sender.open('COM1')

    time.sleep(0.3)
    sender.close()

    assert on_error.called
