import struct
import binascii
import pytest
from protocol import (
    calc_crc, pack_frame, parse_frame,
    pack_a5_request, pack_5a_ack, pack_a6_request, pack_6a_response,
    pack_a7_request, pack_7a_response,
    parse_a5_data, parse_a6_data, parse_6a_data, parse_a7_data, parse_7a_data,
)
from config import FRAME_HEADER, HEADER_SIZE, LENGTH_SIZE, CMD_SIZE, CRC_SIZE
from config import CMD_A5, CMD_5A, CMD_A6, CMD_6A, CMD_A7, CMD_7A, A5_ACK_OK, A6_INFO_SIZE


def test_calc_crc_matches_binascii():
    data = b'123456789'
    assert calc_crc(data) == binascii.crc32(data) & 0xFFFFFFFF


def test_pack_frame_basic():
    cmd = CMD_A5
    data = struct.pack('<H', 128)
    length = CMD_SIZE + len(data) + CRC_SIZE
    frame = pack_frame(length, cmd, data)

    assert frame[:HEADER_SIZE] == FRAME_HEADER
    assert struct.unpack('<H', frame[HEADER_SIZE:HEADER_SIZE + LENGTH_SIZE])[0] == length
    assert frame[HEADER_SIZE + LENGTH_SIZE] == cmd
    assert frame[HEADER_SIZE + LENGTH_SIZE + 1:HEADER_SIZE + LENGTH_SIZE + 1 + len(data)] == data

    body_for_crc = frame[HEADER_SIZE:HEADER_SIZE + LENGTH_SIZE + length - CRC_SIZE]
    expected_crc = binascii.crc32(body_for_crc) & 0xFFFFFFFF
    actual_crc = struct.unpack('<I', frame[-CRC_SIZE:])[0]
    assert actual_crc == expected_crc


def test_parse_frame_roundtrip():
    x = 0x12345678
    frame = pack_a7_request(x)
    length, cmd, parsed_data = parse_frame(frame)
    assert length == CMD_SIZE + 4 + CRC_SIZE
    assert cmd == CMD_A7
    assert parse_a7_data(parsed_data) == x


def test_parse_frame_crc_error():
    frame = bytearray(pack_a5_request(128))
    frame[-1] ^= 0xFF  # 破坏 CRC
    with pytest.raises(ValueError, match='CRC32'):
        parse_frame(bytes(frame))


def test_parse_frame_bad_header():
    frame = b'\x00\x00' + pack_a5_request(128)[2:]
    with pytest.raises(ValueError, match='帧头'):
        parse_frame(frame)


def test_a5_request_roundtrip():
    frame = pack_a5_request(256)
    _, cmd, data = parse_frame(frame)
    assert cmd == CMD_A5
    assert parse_a5_data(data) == 256


def test_5a_ack_roundtrip():
    frame = pack_5a_ack(A5_ACK_OK)
    _, cmd, data = parse_frame(frame)
    assert cmd == CMD_5A
    assert data == bytes([A5_ACK_OK])


def test_a6_request_roundtrip():
    frame = pack_a6_request()
    _, cmd, data = parse_frame(frame)
    assert cmd == CMD_A6
    parse_a6_data(data)


def test_6a_response_roundtrip():
    frame = pack_6a_response(120456, 236, 0xABCD1234)
    _, cmd, data = parse_frame(frame)
    assert cmd == CMD_6A
    assert len(data) == A6_INFO_SIZE
    file_size, packet_count, file_crc = parse_6a_data(data)
    assert file_size == 120456
    assert packet_count == 236
    assert file_crc == 0xABCD1234


def test_a7_request_roundtrip():
    frame = pack_a7_request(1234)
    _, cmd, data = parse_frame(frame)
    assert cmd == CMD_A7
    assert parse_a7_data(data) == 1234


def test_7a_response_roundtrip():
    payload = b'A' * 128
    frame = pack_7a_response(42, payload)
    _, cmd, data = parse_frame(frame)
    assert cmd == CMD_7A
    x, parsed_payload = parse_7a_data(data)
    assert x == 42
    assert parsed_payload == payload


def test_7a_response_short_data():
    frame = pack_7a_response(0, b'')
    _, cmd, data = parse_frame(frame)
    assert cmd == CMD_7A
    x, parsed_payload = parse_7a_data(data)
    assert x == 0
    assert parsed_payload == b''
