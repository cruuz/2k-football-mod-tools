#!/usr/bin/env python3
"""Prove that the recovered loose TM PNG replaces only row-2 source markup."""

from __future__ import annotations

import sys
from pathlib import Path

from recovered_menu_screenshot_test import inspect


def changed_in_box(left: bytes, right: bytes, width: int,
                   x0: int, y0: int, x1: int, y1: int) -> int:
    changed = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            offset = (y * width + x) * 4
            if left[offset:offset + 4] != right[offset:offset + 4]:
                changed += 1
    return changed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: nfl_formatted_token_screenshot_test.py TM.png LITERAL.png",
              file=sys.stderr)
        return 2
    rendered = inspect(Path(argv[0]))
    literal = inspect(Path(argv[1]))
    if rendered[:2] != literal[:2]:
        raise ValueError("TM and literal screenshots have different dimensions")
    if rendered[2] == literal[2]:
        raise ValueError("TM and literal screenshots are identical")

    width, height = rendered[:2]
    menu_x = width * 0.08 + 38.0
    first_y = height * 0.12 + 126.0
    row_step = 36.0 + 7.0
    x0 = int(menu_x + 46.0)
    x1 = int(width * 0.08 + width * 0.84 * 0.48)
    y0 = int(first_y + 2.0 * row_step)
    y1 = int(y0 + 36.0)
    row_changed = changed_in_box(rendered[4], literal[4], width,
                                 x0, y0, x1, y1)
    total_changed = changed_in_box(rendered[4], literal[4], width,
                                   0, 0, width, height)
    outside_changed = total_changed - row_changed
    if row_changed < 20:
        raise ValueError(f"TM changed only {row_changed} pixels in row 2")
    if outside_changed != 0:
        raise ValueError(
            f"TM rendering changed {outside_changed} pixels outside row 2")
    print(
        "NFL_FORMATTED_TOKEN_SCREENSHOT_PASS "
        "representation=recovered_host_representation token=TM index=40 "
        f"row2_changed_pixels={row_changed} outside_changed_pixels=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
