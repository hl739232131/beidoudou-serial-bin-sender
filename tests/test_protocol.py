import struct
import binascii
import pytest
from protocol import pack_frame
from config import FRAME_HEADER, FRAME_SIZE, FRAME_TOTAL_SIZE


def test_pack_frame_full_length():
    data = b'A' * FRAME_SIZE
    frame = pack_frame(data)
    assert len(frame) == FRAME_TOTAL_SIZE
    assert frame[:2] == FRAME_HEADER
    assert frame[2:2 + FRAME_SIZE] == data


def test_pack_frame_short_data_padded():
    data = b'hello'
    frame = pack_frame(data)
    assert len(frame) == FRAME_TOTAL_SIZE
    payload = frame[2:2 + FRAME_SIZE]
    assert payload[:5] == data
    assert payload[5:] == b'\xFF' * (FRAME_SIZE - 5)


def test_pack_frame_crc_is_correct():
    data = b'\x01\x02\x03\x04'
    frame = pack_frame(data)
    payload = frame[2:2 + FRAME_SIZE]
    expected_crc = binascii.crc32(payload) & 0xFFFFFFFF
    actual_crc = struct.unpack('<I', frame[2 + FRAME_SIZE:])[0]
    assert actual_crc == expected_crc


def test_pack_frame_crc_known_answer():
    """固定测试向量，确保 CRC 变体不被无意改成 CRC-32/BZIP2 等其它多项式。"""
    # CRC-32/ISO-HDLC（zlib）对 b'123456789' 的标准校验值
    assert binascii.crc32(b'123456789') & 0xFFFFFFFF == 0xCBF43926

    frame = pack_frame(b'123456789')
    assert frame == (
        FRAME_HEADER
        + b'123456789'
        + b'\xFF' * (FRAME_SIZE - 9)
        + bytes.fromhex('e9e7a1d4')  # 0xD4A1E7E9 小端
    )


def test_pack_frame_exceeds_size_raises():
    with pytest.raises(ValueError):
        pack_frame(b'X' * (FRAME_SIZE + 1))
