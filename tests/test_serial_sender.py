import threading
import time
import pytest
import serial
from unittest.mock import MagicMock
from serial_sender import SerialSender, SendResult
from protocol import pack_frame
from config import BAUDRATE, FRAME_SIZE, FRAME_TOTAL_SIZE, INTERVAL_MS, WRITE_TIMEOUT_S


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.init_args = args
        self.init_kwargs = kwargs
        self.is_open = True
        self.written = b''
        self.cancel_write_calls = 0
        self._lock = threading.Lock()

    def open(self):
        self.is_open = True

    def cancel_write(self):
        self.cancel_write_calls += 1

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


def make_sender(monkeypatch, open_kwargs=None) -> tuple[SerialSender, FakeSerial]:
    created = []

    def fake_serial(*args, **kwargs):
        fake = FakeSerial(*args, **kwargs)
        created.append(fake)
        return fake

    monkeypatch.setattr(serial, 'Serial', fake_serial)
    sender = SerialSender()
    sender.open('COM1', **(open_kwargs or {}))
    return sender, created[0]


def test_sender_open_close(monkeypatch):
    sender, fake = make_sender(monkeypatch)
    assert sender.is_open()

    # 串口线路参数属于协议约定，必须固定为 8N1
    assert fake.init_args[0] == 'COM1'
    assert fake.init_args[1] == BAUDRATE
    assert fake.init_kwargs['bytesize'] == 8
    assert fake.init_kwargs['parity'] == 'N'
    assert fake.init_kwargs['stopbits'] == 1
    assert fake.init_kwargs['write_timeout'] == WRITE_TIMEOUT_S

    sender.close()
    assert not sender.is_open()
    assert not fake.is_open


def test_sender_open_honours_explicit_parameters(monkeypatch):
    sender, fake = make_sender(
        monkeypatch, {'baudrate': 9600, 'write_timeout': 0.5}
    )
    assert fake.init_args[1] == 9600
    assert fake.init_kwargs['write_timeout'] == 0.5
    sender.close()


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
    result, message = finished.call_args[0]
    assert result is SendResult.COMPLETED
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
    finished.assert_called_once_with(SendResult.COMPLETED, '发送完成: 0/0 bytes')


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
    result, message = finished.call_args[0]
    assert result is SendResult.FAILED
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
    result, message = finished.call_args[0]
    assert result is SendResult.STOPPED
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


def test_stop_cancels_pending_write(tmp_path, monkeypatch):
    sender, fake = make_sender(monkeypatch)

    bin_file = tmp_path / 'large.bin'
    bin_file.write_bytes(b'G' * FRAME_SIZE * 100)

    sender.send_bin(str(bin_file))
    sender.stop()
    assert sender.wait(timeout=5)
    sender.close()

    assert fake.cancel_write_calls >= 1


def test_close_during_send_reports_stopped(tmp_path, monkeypatch):
    """关闭串口属于用户主动中断，UI 不应该因此弹出错误框。"""
    sender, _ = make_sender(monkeypatch)

    bin_file = tmp_path / 'large.bin'
    bin_file.write_bytes(b'H' * FRAME_SIZE * 100)

    finished = MagicMock()
    sender.send_bin(str(bin_file), None, None, finished)
    time.sleep(0.06)
    sender.close()
    assert sender.wait(timeout=5)

    finished.assert_called_once()
    result, message = finished.call_args[0]
    assert result is SendResult.STOPPED
    assert '发送已停止' in message


def test_close_does_not_wait_for_blocking_write(tmp_path, monkeypatch):
    """write 阻塞在对端不接收时，close() 不能被 _port_lock 拖住（GUI 线程会卡死）。"""
    sender, fake = make_sender(monkeypatch)

    write_started = threading.Event()
    release_write = threading.Event()

    def blocking_write(data):
        write_started.set()
        release_write.wait(5)

    monkeypatch.setattr(fake, 'write', blocking_write)

    bin_file = tmp_path / 'large.bin'
    bin_file.write_bytes(b'I' * FRAME_SIZE * 10)

    sender.send_bin(str(bin_file))
    assert write_started.wait(5)

    started = time.monotonic()
    sender.close()
    assert time.monotonic() - started < 0.5

    release_write.set()
    assert sender.wait(timeout=5)


def test_frame_interval_waited_between_full_frames(tmp_path, monkeypatch):
    """每帧之间必须留出 50 ms 间隔，且最后一个不满帧后不再等待。"""
    sender, _ = make_sender(monkeypatch)

    bin_file = tmp_path / 'test.bin'
    bin_file.write_bytes(b'J' * (FRAME_SIZE * 3 + 1))

    waits = []

    def fake_wait():
        waits.append(INTERVAL_MS / 1000.0)
        return False

    monkeypatch.setattr(sender, '_wait_interval', fake_wait)

    finished = MagicMock()
    sender.send_bin(str(bin_file), None, None, finished)
    assert sender.wait(timeout=5)
    sender.close()

    assert finished.call_args[0][0] is SendResult.COMPLETED
    # 3 个满帧各等待一次，末尾 1 字节的不满帧不等待
    assert waits == [0.05, 0.05, 0.05]


def test_frame_interval_uses_configured_delay(tmp_path, monkeypatch):
    """不打桩的计时校验，边界放宽以容忍调度抖动。"""
    sender, _ = make_sender(monkeypatch)

    bin_file = tmp_path / 'test.bin'
    frames = 4
    bin_file.write_bytes(b'K' * FRAME_SIZE * frames)

    started = time.monotonic()
    sender.send_bin(str(bin_file))
    assert sender.wait(timeout=10)
    elapsed = time.monotonic() - started
    sender.close()

    # 4 个满帧 => 4 次间隔等待
    assert elapsed >= frames * (INTERVAL_MS / 1000.0) * 0.8
    assert elapsed < frames * (INTERVAL_MS / 1000.0) + 2.0


def test_stop_event_wait_uses_interval(monkeypatch):
    sender = SerialSender()
    recorded = []
    monkeypatch.setattr(sender._stop_event, 'wait', lambda t: recorded.append(t) or False)

    assert sender._wait_interval() is False
    assert recorded == [INTERVAL_MS / 1000.0]
