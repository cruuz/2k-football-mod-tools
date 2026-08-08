"""Fit any supplied image to the exact size a game texture slot demands.

Every texture on these discs occupies a fixed byte span, so its replacement has
to be exactly the retail pixel size -- 512x256 for a jersey, 1024x32 for the
nameplate strip, and so on. That rule is the disc's and cannot be relaxed.

What *was* ours is refusing the file outright. A modder with a 2048x1024 jersey,
or a PS2 texture pulled from another mod, or a photo, had to go and resize it in
another program before the editor would look at it. This module removes that
step: it reads whatever they hand over and produces the exact pixel size the
slot needs, reporting precisely what it did so nothing is silently altered.

Three fits, chosen deliberately:

* **exact** -- already the right size. Passed through untouched, so an image
  that needed no work is byte-identical to what the user supplied.
* **scaled** -- same aspect ratio, so a straight high-quality resample lands on
  the target with nothing cropped and nothing padded.
* **cropped** -- a different aspect ratio, filling the slot. The image is
  scaled until it covers the target and the overflow is trimmed evenly from
  both sides. This is right for a jersey or a field panel, where transparent
  bars would show up in game as holes.
* **padded** -- a different aspect ratio, keeping the whole image. It is scaled
  to fit inside the target and centred on transparency. This is right for a
  crest or a logo, where cropping the sides off the shape is exactly the wrong
  answer, and the texture already has an alpha channel to pad into.

Downscaling uses Lanczos, which is what keeps small lettering on a 32-pixel-tall
nameplate legible instead of turning it to mush.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
from typing import Any

from .errors import ValidationError


MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_PIXELS = 64 * 1024 * 1024  # a decompression-bomb ceiling
FIT_MODES = ("auto", "scale", "cover", "contain", "stretch")


@dataclass(frozen=True)
class FitResult:
    """What was produced, and honestly what was done to get there."""

    width: int
    height: int
    rgba: bytes
    source_width: int
    source_height: int
    action: str          # "exact" | "scaled" | "cropped" | "padded" | "stretched"
    cropped_x: int = 0
    cropped_y: int = 0
    padded_x: int = 0
    padded_y: int = 0
    source_format: str = "UNKNOWN"
    source_mode: str = "UNKNOWN"

    @property
    def changed(self) -> bool:
        return self.action != "exact"

    def describe(self) -> str:
        if self.action == "exact":
            return f"already {self.width}x{self.height}"
        if self.action == "scaled":
            return (
                f"scaled {self.source_width}x{self.source_height} "
                f"to {self.width}x{self.height}"
            )
        if self.action == "padded":
            return (
                f"fit {self.source_width}x{self.source_height} inside "
                f"{self.width}x{self.height}, padding "
                f"{self.padded_x}px horizontally and {self.padded_y}px "
                "vertically with transparency"
            )
        if self.action == "stretched":
            return (
                f"stretched {self.source_width}x{self.source_height} "
                f"to {self.width}x{self.height} without preserving aspect ratio"
            )
        return (
            f"scaled {self.source_width}x{self.source_height} to cover "
            f"{self.width}x{self.height} and trimmed "
            f"{self.cropped_x}px horizontally, {self.cropped_y}px vertically"
        )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _load(path: Path) -> tuple[Any, str, str]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with the app
        raise ValidationError(
            "Pillow is required to resize an image to the size this slot needs."
        ) from exc

    resolved = Path(path).expanduser()
    try:
        info = resolved.lstat()
    except OSError as exc:
        raise ValidationError(f"Cannot read {resolved.name}: {exc.strerror}") from exc
    _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
             f"{resolved.name} must be a regular, non-symlink file")
    _require(info.st_size <= MAX_SOURCE_BYTES,
             f"{resolved.name} is larger than {MAX_SOURCE_BYTES // (1024 * 1024)} MiB")
    Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS
    try:
        image = Image.open(resolved)
        image.load()
    except Exception as exc:  # noqa: BLE001 - Pillow raises many types
        raise ValidationError(
            f"{resolved.name} could not be read as an image: {exc}"
        ) from exc
    return image.convert("RGBA"), str(image.format or "UNKNOWN").upper(), str(image.mode)


def fit_image(
    path: Path, width: int, height: int, *, mode: str = "auto"
) -> FitResult:
    """Return exactly ``width`` x ``height`` RGBA from whatever is at ``path``."""
    _require(mode in FIT_MODES, f"fit mode must be one of {', '.join(FIT_MODES)}")
    _require(width > 0 and height > 0, "target size must be positive")
    from PIL import Image

    image, source_format, source_mode = _load(path)
    source_width, source_height = image.size
    _require(source_width > 0 and source_height > 0, "image has no pixels")

    if (source_width, source_height) == (width, height):
        return FitResult(
            width, height, image.tobytes(), source_width, source_height, "exact",
            source_format=source_format, source_mode=source_mode,
        )

    same_aspect = source_width * height == source_height * width
    if mode == "stretch" or mode == "scale" or (mode == "auto" and same_aspect):
        resized = image.resize((width, height), Image.LANCZOS)
        action = "stretched" if mode == "stretch" else "scaled"
        return FitResult(
            width, height, resized.tobytes(), source_width, source_height, action,
            source_format=source_format, source_mode=source_mode,
        )

    if mode == "contain":
        # Fit the whole image inside the slot and centre it on transparency.
        scale = min(width / source_width, height / source_height)
        inner_width = max(1, min(width, int(round(source_width * scale))))
        inner_height = max(1, min(height, int(round(source_height * scale))))
        resized = image.resize((inner_width, inner_height), Image.LANCZOS)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        left = (width - inner_width) // 2
        top = (height - inner_height) // 2
        canvas.paste(resized, (left, top))
        return FitResult(
            width, height, canvas.tobytes(), source_width, source_height, "padded",
            padded_x=width - inner_width,
            padded_y=height - inner_height,
            source_format=source_format,
            source_mode=source_mode,
        )

    # Cover: scale until both axes reach the target, then trim the overflow.
    scale = max(width / source_width, height / source_height)
    cover_width = max(width, int(round(source_width * scale)))
    cover_height = max(height, int(round(source_height * scale)))
    resized = image.resize((cover_width, cover_height), Image.LANCZOS)
    left = (cover_width - width) // 2
    top = (cover_height - height) // 2
    cropped = resized.crop((left, top, left + width, top + height))
    _require(cropped.size == (width, height), "cover crop produced the wrong size")
    return FitResult(
        width, height, cropped.tobytes(), source_width, source_height,
        "cropped", cover_width - width, cover_height - height,
        source_format=source_format, source_mode=source_mode,
    )


def fit_to_png(
    path: Path, width: int, height: int, destination: Path, *, mode: str = "auto"
) -> FitResult:
    """Fit an image and write it as a plain 8-bit RGBA PNG."""
    import sys

    tools = str(Path(__file__).resolve().parents[2] / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    from nfl_txtr import encode_rgba_png

    result = fit_image(path, width, height, mode=mode)
    payload = encode_rgba_png(result.width, result.height, result.rgba)
    out = Path(destination).expanduser()
    _require(not out.is_symlink(), f"refusing to write through a symlink: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload)
    return result


__all__ = [
    "FIT_MODES",
    "FitResult",
    "MAX_SOURCE_BYTES",
    "fit_image",
    "fit_to_png",
]
