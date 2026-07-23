#!/usr/bin/env python3
"""Bounded framebuffer check for the static and animated APF shadow skins."""

from __future__ import annotations

import sys
from pathlib import Path

from recovered_menu_screenshot_test import inspect


def model_pixel(value: bytes) -> bool:
    red, green, blue, alpha = value
    return (alpha == 255 and red > 80 and red * 100 > green * 105 and
            red * 100 > blue * 102)


def crop_metrics(image: tuple[int, int, str, int, bytes]
                 ) -> tuple[list[bytes], int]:
    width, height, _, _, pixels = image
    panel_x = width * 0.08
    panel_y = height * 0.12
    panel_w = width * 0.84
    panel_h = height * 0.74
    preview_x = int(panel_x + panel_w * 0.62)
    preview_y = int(panel_y + panel_h * 0.49)
    preview_w = int(panel_w * 0.32)
    preview_h = int(panel_h * 0.28)
    # Exclude the overlapping logo and the preview caption. The retained crop
    # contains only the 3D viewport background and rendered shadow geometry.
    left, top = preview_x + 2, preview_y + 22
    right, bottom = preview_x + preview_w - 2, preview_y + preview_h - 28
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("computed preview crop lies outside the framebuffer")
    values = [
        pixels[(y * width + x) * 4:(y * width + x + 1) * 4]
        for y in range(top, bottom)
        for x in range(left, right)
    ]
    return values, sum(model_pixel(value) for value in values)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: apf_player_shadow_screenshot_test.py STATIC.png ANIMATED.png",
              file=sys.stderr)
        return 2
    static = inspect(Path(argv[0]))
    animated = inspect(Path(argv[1]))
    if static[:2] != animated[:2]:
        raise ValueError("static and animated framebuffer dimensions differ")
    if static[2] == animated[2]:
        raise ValueError("static and animated screenshots are byte-identical")
    if any(static[4][index] != 255 for index in range(3, len(static[4]), 4)):
        raise ValueError("static framebuffer is not opaque")
    if any(animated[4][index] != 255
           for index in range(3, len(animated[4]), 4)):
        raise ValueError("animated framebuffer is not opaque")

    static_crop, static_pixels = crop_metrics(static)
    animated_crop, animated_pixels = crop_metrics(animated)
    differing = sum(left != right for left, right in
                    zip(static_crop, animated_crop, strict=True))
    if static_pixels < 500 or animated_pixels < 500:
        raise ValueError(
            f"rendered model coverage is too small: {static_pixels}/{animated_pixels}"
        )
    if differing < 500:
        raise ValueError(f"static/animated preview difference is too small: {differing}")

    print(
        "APF_PLAYER_SHADOW_SCREENSHOTS_PASS "
        f"dimensions={static[0]}x{static[1]} "
        f"static_bytes={static[3]} animated_bytes={animated[3]} "
        f"static_model_pixels={static_pixels} "
        f"animated_model_pixels={animated_pixels} differing_pixels={differing} "
        f"static_sha256={static[2]} animated_sha256={animated[2]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
