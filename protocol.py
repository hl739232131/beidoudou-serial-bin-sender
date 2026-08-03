import binascii
import struct
from config import FRAME_HEADER, FRAME_SIZE


def pack_frame(data: bytes) -> bytes:
    if len(data) > FRAME_SIZE:
        raise ValueError(f'Data length exceeds {FRAME_SIZE} bytes')
    padded = data + b'\xFF' * (FRAME_SIZE - len(data))
    crc = binascii.crc32(padded) & 0xFFFFFFFF
    return FRAME_HEADER + padded + struct.pack('<I', crc)
