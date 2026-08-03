import threading
import time
import serial
from unittest.mock import MagicMock
from serial_sender import SerialSender
from config import FRAME_SIZE, FRAME_TOTAL_SIZE


class FakeSerial:
    def __init__(self):
        self.is_open = True
        self.written = b''

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def write(self, data):
        self.written += data

    def isOpen(self):
        return self.is_open


def test_sender_open_close(monkeypatch):
    fake = FakeSerial()
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)
    sender = SerialSender()
    sender.open('COM1', 115200)
    assert sender.is_open()
    sender.close()
    assert not sender.is_open()


def test_send_bin_progress(tmp_path, monkeypatch):
    fake = FakeSerial()
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)
    sender = SerialSender()
    sender.open('COM1', 115200)

    bin_file = tmp_path / 'test.bin'
    total = FRAME_SIZE * 2 + 10
    bin_file.write_bytes(b'B' * total)

    progress = MagicMock()
    log = MagicMock()

    sender.send_bin(str(bin_file), progress, log)
    sender._thread.join(timeout=5)

    sender.close()

    expected_frames = 3
    assert len(fake.written) == expected_frames * FRAME_TOTAL_SIZE
    progress.assert_called()
    log.assert_called()


def test_stop_sending(tmp_path, monkeypatch):
    fake = FakeSerial()
    monkeypatch.setattr(serial, 'Serial', lambda *args, **kwargs: fake)
    sender = SerialSender()
    sender.open('COM1', 115200)

    bin_file = tmp_path / 'large.bin'
    bin_file.write_bytes(b'C' * FRAME_SIZE * 100)

    thread = threading.Thread(target=sender.send_bin, args=(str(bin_file), None, None))
    thread.start()
    time.sleep(0.1)
    sender.stop()
    thread.join(timeout=5)
    sender.close()

    assert len(fake.written) < FRAME_TOTAL_SIZE * 100
