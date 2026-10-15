#!/usr/bin/env python3
"""Losslessly convert the project's 32x32 paletted ICO to PNG (stdlib only)."""
from pathlib import Path
import struct
import zlib
root = Path(__file__).resolve().parents[1]
raw = (root / 'assets/zaper.ico').read_bytes()
size, offset = struct.unpack_from('<II', raw, 14)
data = raw[offset:offset + size]
header, width, height, planes, bits = struct.unpack_from('<IiiHH', data)
assert header == 40 and bits == 4 and width == 32 and height == 64
palette = [data[40 + i * 4:44 + i * 4] for i in range(16)]
scanlines = []
for row in range(32):
    source = 31 - row
    pixels = bytearray()
    for x in range(32):
        value = data[104 + source * 16 + x // 2]
        color = palette[(value >> 4) if x % 2 == 0 else (value & 15)]
        transparent = data[616 + source * 4 + x // 8] & (128 >> (x % 8))
        pixels.extend((color[2], color[1], color[0], 0 if transparent else 255))
    scanlines.append(b'\0' + pixels)

def chunk(kind, value):
    return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value))
image = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 32, 32, 8, 6, 0, 0, 0))
image += chunk(b'IDAT', zlib.compress(b''.join(scanlines))) + chunk(b'IEND', b'')
(root / 'linux/zaper.png').write_bytes(image)
