import binascii
import struct
from typing import Tuple
from config import (
    FRAME_HEADER, HEADER_SIZE, LENGTH_SIZE, CMD_SIZE, CRC_SIZE,
    CMD_A5, CMD_5A, CMD_A7, CMD_7A,
)


def calc_crc(data: bytes) -> int:
    """计算 CRC32，返回 32 位无符号整数。"""
    return binascii.crc32(data) & 0xFFFFFFFF


def pack_frame(length: int, cmd: int, data: bytes) -> bytes:
    """
    打包成一帧。

    帧格式：帧头(0xAA55) + 字节数(2B LE) + 命令(1B) + 数据(NB) + CRC32(4B LE)
    其中 length = 1(命令) + len(数据) + 4(CRC32)
    CRC32 计算范围 = 字节数 + 命令 + 数据
    """
    if not (0 <= cmd <= 0xFF):
        raise ValueError(f'命令必须是 1 字节: {cmd}')
    if length != CMD_SIZE + len(data) + CRC_SIZE:
        raise ValueError(
            f'字节数应为 {CMD_SIZE + len(data) + CRC_SIZE}, 传入 {length}'
        )
    body = struct.pack('<H', length) + bytes([cmd]) + data
    crc = calc_crc(body)
    return FRAME_HEADER + body + struct.pack('<I', crc)


def parse_frame(frame: bytes) -> Tuple[int, int, bytes]:
    """
    解析一帧，返回 (length, cmd, data)。

    如果帧不完整返回 None；如果 CRC 校验失败抛出 ValueError。
    """
    min_size = HEADER_SIZE + LENGTH_SIZE + CMD_SIZE + CRC_SIZE
    if len(frame) < min_size:
        raise ValueError(f'帧长度不足最小长度 {min_size}: {len(frame)}')

    if frame[:HEADER_SIZE] != FRAME_HEADER:
        raise ValueError(f'帧头错误: {frame[:HEADER_SIZE].hex()}')

    length = struct.unpack('<H', frame[HEADER_SIZE:HEADER_SIZE + LENGTH_SIZE])[0]
    expected_total = HEADER_SIZE + LENGTH_SIZE + length
    if len(frame) < expected_total:
        raise ValueError(
            f'帧数据不完整: 期望 {expected_total} 字节, 实际 {len(frame)} 字节'
        )
    if len(frame) > expected_total:
        raise ValueError(
            f'帧长度超过预期: 期望 {expected_total} 字节, 实际 {len(frame)} 字节'
        )

    # body 用于 CRC 计算：字节数 + 命令 + 数据（不含 CRC32 本身）
    body_without_crc = frame[HEADER_SIZE:HEADER_SIZE + LENGTH_SIZE + length - CRC_SIZE]
    cmd_and_data = frame[HEADER_SIZE + LENGTH_SIZE:HEADER_SIZE + LENGTH_SIZE + length]
    cmd = cmd_and_data[0]
    data = cmd_and_data[1:-CRC_SIZE] if length > CMD_SIZE + CRC_SIZE else b''

    actual_crc = struct.unpack(
        '<I', frame[HEADER_SIZE + LENGTH_SIZE + length - CRC_SIZE:HEADER_SIZE + LENGTH_SIZE + length]
    )[0]
    expected_crc = calc_crc(body_without_crc)
    if actual_crc != expected_crc:
        raise ValueError(f'CRC32 校验失败: 实际 {actual_crc:08X}, 期望 {expected_crc:08X}')

    return length, cmd, data


def pack_a5_request(n: int) -> bytes:
    """主机发送：申请下发字节数 N（2 字节小端序）。"""
    return pack_frame(CMD_SIZE + 2 + CRC_SIZE, CMD_A5, struct.pack('<H', n))


def pack_5a_ack(status: int) -> bytes:
    """从机回复：收到状态（1 字节）。"""
    return pack_frame(CMD_SIZE + 1 + CRC_SIZE, CMD_5A, bytes([status]))


def pack_a7_request(x: int) -> bytes:
    """主机发送：申请第 x 个数据包（4 字节小端序）。"""
    return pack_frame(CMD_SIZE + 4 + CRC_SIZE, CMD_A7, struct.pack('<I', x))


def pack_7a_response(x: int, payload: bytes) -> bytes:
    """从机发送：第 x 个数据包 = 序号(4B) + 数据(NB)。"""
    return pack_frame(CMD_SIZE + 4 + len(payload) + CRC_SIZE, CMD_7A, struct.pack('<I', x) + payload)


def parse_a5_data(data: bytes) -> int:
    """解析 A5 命令数据，返回 N。"""
    if len(data) != 2:
        raise ValueError(f'A5 数据长度应为 2, 实际 {len(data)}')
    return struct.unpack('<H', data)[0]


def parse_a7_data(data: bytes) -> int:
    """解析 A7 命令数据，返回序号 x。"""
    if len(data) != 4:
        raise ValueError(f'A7 数据长度应为 4, 实际 {len(data)}')
    return struct.unpack('<I', data)[0]


def parse_7a_data(data: bytes) -> Tuple[int, bytes]:
    """解析 7A 命令数据，返回 (x, payload)。"""
    if len(data) < 4:
        raise ValueError(f'7A 数据长度至少 4, 实际 {len(data)}')
    x = struct.unpack('<I', data[:4])[0]
    return x, data[4:]
