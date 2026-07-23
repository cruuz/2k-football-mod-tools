#!/usr/bin/env python3
"""Prove the NFL row-label region changes when recovered font7 is active."""

from __future__ import annotations

import sys
from pathlib import Path

from recovered_menu_screenshot_test import inspect


def different_pixels(left: bytes, right: bytes, width: int,
                     first_x: int, first_y: int,
                     after_x: int, after_y: int) -> int:
    count = 0
    for y in range(first_y, after_y):
        for x in range(first_x, after_x):
            offset = (y * width + x) * 4
            if left[offset:offset + 4] != right[offset:offset + 4]:
                count += 1
    return count


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: nfl_bitmap_font_screenshot_test.py FONT7.png FALLBACK.png",
              file=sys.stderr)
        return 2
    recovered = inspect(Path(argv[0]))
    fallback = inspect(Path(argv[1]))
    if recovered[:2] != fallback[:2]:
        raise ValueError("font7 and fallback framebuffer dimensions differ")
    if recovered[2] == fallback[2]:
        raise ValueError("font7 and fallback screenshots are identical")

    width, height = recovered[:2]
    first_x = int(width * 0.08 + 38.0 + 44.0)
    after_x = int(width * 0.08 + width * 0.84 * 0.48)
    first_y = int(height * 0.12 + 126.0)
    after_y = int(first_y + 7.0 * 36.0 + 6.0 * 7.0)
    changed = different_pixels(recovered[4], fallback[4], width,
                               first_x, first_y, after_x, after_y)
    if changed < 500:
        raise ValueError(
            f"NFL row-label region changed only {changed} pixels; "
            "font7 rendering is not demonstrated"
        )

    total_changed = different_pixels(recovered[4], fallback[4], width,
                                     0, 0, width, height)
    outside_changed = total_changed - changed
    if outside_changed > 32:
        raise ValueError(
            f"font comparison changed {outside_changed} pixels outside the "
            "bounded NFL row-label region"
        )
    print(
        "NFL_BITMAP_FONT_SCREENSHOT_PASS "
        f"representation=recovered_host_representation "
        f"dimensions={width}x{height} row_label_changed_pixels={changed} "
        f"outside_changed_pixels={outside_changed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
