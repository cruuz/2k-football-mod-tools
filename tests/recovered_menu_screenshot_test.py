#!/usr/bin/env python3
"""Semantic smoke check for the two recovered-menu host screenshots."""

from __future__ import annotations

import hashlib
import struct
import sys
import zlib
from pathlib import Path


def paeth(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def inspect(path: Path) -> tuple[int, int, str, int, bytes]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: missing PNG signature")

    position = 8
    header: bytes | None = None
    compressed = bytearray()
    saw_end = False
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        chunk_type = data[position + 4:position + 8]
        chunk_end = position + 12 + length
        if chunk_end > len(data):
            raise ValueError(f"{path}: truncated {chunk_type!r} chunk")
        payload = data[position + 8:position + 8 + length]
        expected_crc = struct.unpack(">I", data[position + 8 + length:chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError(f"{path}: bad {chunk_type!r} CRC")
        if chunk_type == b"IHDR":
            header = payload
        elif chunk_type == b"IDAT":
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            saw_end = True
            position = chunk_end
            break
        position = chunk_end

    if header is None or len(header) != 13:
        raise ValueError(f"{path}: missing IHDR")
    if not compressed or not saw_end or position != len(data):
        raise ValueError(f"{path}: incomplete PNG chunk stream")
    width, height, depth, color_type, compression, filtering, interlace = (
        struct.unpack(">IIBBBBB", header)
    )
    if width < 640 or height < 360:
        raise ValueError(f"{path}: unexpectedly small framebuffer {width}x{height}")
    if (depth, color_type, compression, filtering, interlace) != (8, 6, 0, 0, 0):
        raise ValueError(f"{path}: expected non-interlaced 8-bit RGBA PNG")
    if len(data) < 10_000:
        raise ValueError(f"{path}: screenshot payload is implausibly small")

    stride = width * 4
    filtered = zlib.decompress(compressed)
    if len(filtered) != height * (stride + 1):
        raise ValueError(f"{path}: invalid decompressed scanline size")
    pixels = bytearray()
    previous = bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        filter_type = filtered[start]
        row = bytearray(filtered[start + 1:start + stride + 1])
        if filter_type > 4:
            raise ValueError(f"{path}: unsupported PNG filter {filter_type}")
        for x in range(stride):
            left = row[x - 4] if x >= 4 else 0
            up = previous[x]
            upper_left = previous[x - 4] if x >= 4 else 0
            if filter_type == 1:
                row[x] = (row[x] + left) & 0xFF
            elif filter_type == 2:
                row[x] = (row[x] + up) & 0xFF
            elif filter_type == 3:
                row[x] = (row[x] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[x] = (row[x] + paeth(left, up, upper_left)) & 0xFF
        pixels.extend(row)
        previous = row
    return width, height, hashlib.sha256(data).hexdigest(), len(data), bytes(pixels)


def pixel(image: tuple[int, int, str, int, bytes], x: int, y: int) -> bytes:
    width, height, _, _, pixels = image
    if not (0 <= x < width and 0 <= y < height):
        raise ValueError(f"pixel coordinate outside framebuffer: {x},{y}")
    offset = (y * width + x) * 4
    return pixels[offset:offset + 4]


def verify_seven_row_geometry(
    name: str, image: tuple[int, int, str, int, bytes]
) -> tuple[bytes, bytes, bytes]:
    width, height, _, _, _ = image
    panel_x = width * 0.08
    panel_y = height * 0.12
    menu_x = panel_x + 38.0
    menu_y = panel_y + 126.0
    item_height = 36.0
    item_gap = 7.0
    sample_x = int(menu_x + 4.0)
    row_colors = [
        pixel(image, sample_x,
              int(menu_y + index * (item_height + item_gap) + item_height / 2.0))
        for index in range(7)
    ]
    if row_colors[0] == row_colors[1]:
        raise ValueError(f"{name}: selected row is not visibly distinct")
    if len(set(row_colors[1:])) != 1:
        raise ValueError(f"{name}: seven recovered row bands are inconsistent")
    gap_color = pixel(image, sample_x, int(menu_y + item_height + 3.0))
    if gap_color in (row_colors[0], row_colors[1]):
        raise ValueError(f"{name}: recovered rows are not separated by gaps")
    if any(color[3] != 255 for color in (*row_colors, gap_color)):
        raise ValueError(f"{name}: recovered menu framebuffer is not opaque")
    return row_colors[0], row_colors[1], gap_color


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: recovered_menu_screenshot_test.py NFL.png APF.png",
              file=sys.stderr)
        return 2
    nfl = inspect(Path(argv[0]))
    apf = inspect(Path(argv[1]))
    if nfl[:2] != apf[:2]:
        raise ValueError(f"framebuffer dimensions differ: {nfl[:2]} != {apf[:2]}")
    if nfl[2] == apf[2]:
        raise ValueError("NFL and APF recovered host representations are identical")
    nfl_geometry = verify_seven_row_geometry("NFL", nfl)
    apf_geometry = verify_seven_row_geometry("APF", apf)
    if nfl_geometry != apf_geometry:
        raise ValueError("NFL and APF recovered menu row geometry differs")
    print(
        "RECOVERED_MENU_SCREENSHOTS_PASS "
        f"dimensions={nfl[0]}x{nfl[1]} nfl_bytes={nfl[3]} apf_bytes={apf[3]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
