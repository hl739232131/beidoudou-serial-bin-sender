import threading
import time
import pytest
import serial
from unittest.mock import MagicMock
from serial_sender import SerialSender
from protocol import pack_frame
from config import FRAME_SIZE, FRAME_TOTAL_SIZE


class FakeSerial:
    def __init__(self):
        self.is_open = True
        self.written = b''
        self._lock = threading.Lock()

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def write(self, data):
        with self._lock:
            self.written += data

    def isOpen(self):
        return self.is_open


def expected_bytes(payload: bytes) -> bytes:
    frames = [
        pack_frame(payload[i:i + FRAME_SIZE])
        for i in range(0, len(payload), FRAME_SIZE)
    ]
    return b''.join(frames)


def make_sender(monkeypatch) -> tuple[SerialSender, FakeSerial]:
    fake = FakeSerial()
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)
    sender = SerialSender()
    sender.open('COM1', 115200)
    return sender, fake


def test_sender_open_close(monkeypatch):
    sender, _ = make_sender(monkeypatch)
    assert sender.is_open()
    sender.close()
    assert not sender.is_open()


def test_send_bin_progress(tmp_path, monkeypatch):
    sender, fake = make_sender(monkeypatch)

    bin_file = tmp_path / 'test.bin'
    payload = b'B' * (FRAME_SIZE * 2 + 10)
    bin_file.write_bytes(payload)

    progress = MagicMock()
    log = MagicMock()
    finished = MagicMock()

    sender.send_bin(str(bin_file), progress, log, finished)
    assert sender.wait(timeout=5)

    sender.close()

    expected = expected_bytes(payload)
    assert len(expected) == 3 * FRAME_TOTAL_SIZE
    assert fake.written == expected
    progress.assert_called()
    log.assert_called()
    finished.assert_called_once()
    success, message = finished.call_args[0]
    assert success is True
    assert '发送完成' in message


def test_send_bin_empty_file_finishes(tmp_path, monkeypatch):
    sender, fake = make_sender(monkeypatch)

    bin_file = tmp_path / 'empty.bin'
    bin_file.write_bytes(b'')

    finished = MagicMock()
    sender.send_bin(str(bin_file), None, None, finished)
    assert sender.wait(timeout=5)
    sender.close()

    assert fake.written == b''
    finished.assert_called_once_with(True, '发送完成: 0/0 bytes')


def test_send_bin_requires_open_port(tmp_path):
    sender = SerialSender()
    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(b'A' * FRAME_SIZE)

    with pytest.raises(RuntimeError, match='串口未打开'):
        sender.send_bin(str(bin_file))


def test_send_bin_missing_file(tmp_path, monkeypatch):
    sender, _ = make_sender(monkeypatch)
    missing = tmp_path / 'nope.bin'

    with pytest.raises(FileNotFoundError):
        sender.send_bin(str(missing))

    sender.close()


def test_send_bin_rejects_overlap(tmp_path, monkeypatch):
    sender, _ = make_sender(monkeypatch)

    bin_file = tmp_path / 'large.bin'
    bin_file.write_bytes(b'D' * FRAME_SIZE * 100)

    sender.send_bin(str(bin_file))
    try:
        with pytest.raises(RuntimeError, match='发送正在进行中'):
            sender.send_bin(str(bin_file))
    finally:
        sender.stop()
        sender.wait(timeout=5)
        sender.close()


def test_write_error_reported_to_finished(tmp_path, monkeypatch):
    sender, fake = make_sender(monkeypatch)

    def boom(data):
        raise serial.SerialTimeoutException('write timeout')

    monkeypatch.setattr(fake, 'write', boom)

    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(b'E' * FRAME_SIZE)

    finished = MagicMock()
    sender.send_bin(str(bin_file), None, None, finished)
    assert sender.wait(timeout=5)
    sender.close()

    finished.assert_called_once()
    success, message = finished.call_args[0]
    assert success is False
    assert '发送超时' in message


def test_stop_sending(tmp_path, monkeypatch):
    sender, fake = make_sender(monkeypatch)

    bin_file = tmp_path / 'large.bin'
    bin_file.write_bytes(b'C' * FRAME_SIZE * 100)

    finished = MagicMock()
    sender.send_bin(str(bin_file), None, None, finished)
    time.sleep(0.1)
    sender.stop()
    assert sender.wait(timeout=5)
    sender.close()

    assert len(fake.written) < FRAME_TOTAL_SIZE * 100
    finished.assert_called_once()
    success, message = finished.call_args[0]
    assert success is False
    assert '发送已停止' in message


def test_stop_does_not_block_caller(tmp_path, monkeypatch):
    sender, _ = make_sender(monkeypatch)

    bin_file = tmp_path / 'large.bin'
    bin_file.write_bytes(b'F' * FRAME_SIZE * 100)

    sender.send_bin(str(bin_file))
    started = time.monotonic()
    sender.stop()
    assert time.monotonic() - started < 0.2

    sender.wait(timeout=5)
    sender.close()
