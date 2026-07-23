#!/usr/bin/env python3
"""Detect an Xbox game's PRESS START prompt and assert START immediately."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageEnhance
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


def capture(window) -> Image.Image:
    geometry = window.get_geometry()
    pixels = window.get_image(
        0, 0, geometry.width, geometry.height, X.ZPixmap, 0xFFFFFFFF
    )
    if pixels is None:
        raise RuntimeError(f"could not capture window 0x{window.id:x}")
    return Image.frombytes(
        "RGB", (geometry.width, geometry.height), pixels.data, "raw", "BGRX"
    )


def ocr_title(image: Image.Image) -> str:
    width, height = image.size
    crop = image.crop((160, 0, max(161, width - 160), min(240, height)))
    crop = crop.resize((crop.width * 2, crop.height * 2))
    crop = ImageEnhance.Contrast(crop.convert("L")).enhance(2.0)
    payload = io.BytesIO()
    crop.save(payload, format="PNG")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "--psm", "11"],
        input=payload.getvalue(),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return result.stdout.decode("utf-8", "replace")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fifo", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--window", default="xemu |")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=0.20)
    parser.add_argument("--hold", type=float, default=3.0)
    parser.add_argument("--result-delay", type=float, default=4.0)
    parser.add_argument("--prefix", default="title-start")
    args = parser.parse_args()

    dpy = display.Display()
    needle = args.window.casefold()
    matches = [window for window in walk(dpy.screen().root)
               if needle in title(window).casefold()]
    if not matches:
        raise SystemExit(f"no X11 window matches: {args.window}")
    window = matches[-1]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + args.timeout
    attempt = 0
    last_text = ""
    started = time.monotonic()
    while time.monotonic() < deadline:
        attempt += 1
        frame = capture(window)
        last_text = ocr_title(frame)
        normalized = " ".join(last_text.upper().split())
        if attempt == 1 or attempt % 10 == 0 or "PRESS" in normalized or "START" in normalized:
            print(
                f"OCR attempt={attempt} elapsed={time.monotonic() - started:.1f} "
                f"text={normalized!r}",
                flush=True,
            )
        if "PRESS" in normalized and "START" in normalized:
            detected = args.output_dir / f"{args.prefix}-detected.png"
            frame.save(detected)
            print(f"DETECTED output={detected}", flush=True)
            with args.fifo.open("w", buffering=1) as controller:
                controller.write("HOLD START\n")
                print(f"HOLD START seconds={args.hold:.3f}", flush=True)
                time.sleep(args.hold)
                controller.write("RELEASE START\n")
            print("RELEASE START", flush=True)
            time.sleep(args.result_delay)
            result_path = args.output_dir / f"{args.prefix}-result.png"
            capture(window).save(result_path)
            print(f"RESULT output={result_path}", flush=True)
            return 0
        time.sleep(args.interval)
    raise SystemExit(f"PRESS START not detected; last OCR={last_text!r}")


if __name__ == "__main__":
    raise SystemExit(main())
