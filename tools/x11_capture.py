#!/usr/bin/env python3
"""Capture a mapped X11 window without taking an X server grab."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image
from Xlib import X, display


def title(window) -> str:
    try:
        value = window.get_wm_name()
        return str(value) if value is not None else ""
    except Exception:
        return ""


def walk(window):
    for child in window.query_tree().children:
        yield child
        yield from walk(child)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pattern", help="case-insensitive substring of the window title")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    dpy = display.Display()
    needle = args.pattern.casefold()
    matches = [window for window in walk(dpy.screen().root)
               if needle in title(window).casefold()]
    if not matches:
        raise SystemExit(f"no X11 window matches: {args.pattern}")
    window = matches[-1]
    geometry = window.get_geometry()
    pixels = window.get_image(
        0, 0, geometry.width, geometry.height, X.ZPixmap, 0xFFFFFFFF
    )
    if pixels is None:
        raise SystemExit(f"could not capture window 0x{window.id:x}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    Image.frombytes(
        "RGB", (geometry.width, geometry.height), pixels.data, "raw", "BGRX"
    ).save(args.output)
    print(
        f"CAPTURED 0x{window.id:x} {geometry.width}x{geometry.height} "
        f"title={title(window)!r} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
