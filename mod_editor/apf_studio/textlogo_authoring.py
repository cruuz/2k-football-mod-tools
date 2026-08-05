"""User-friendly preparation for APF's native 512x128 wordmark canvas."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from mod_editor.core.errors import ValidationError
from mod_editor.core.image_fit import fit_image

from .backend import ensure_tools_importable


ensure_tools_importable()
from nfl_txtr import encode_rgba_png  # type: ignore  # noqa: E402


WORDMARK_WIDTH = 512
WORDMARK_HEIGHT = 128
WORDMARK_FIT_MODES = ("contain", "cover")


@dataclass(frozen=True)
class PreparedWordmark:
    output_path: Path
    fit_mode: str
    source_width: int
    source_height: int
    fit_action: str
    fit_description: str
    transparent_source_pixels: int
    background_rgba: tuple[int, int, int, int] = (0, 0, 0, 255)


def _flatten_black(rgba: bytes) -> tuple[bytes, int]:
    """Composite straight-alpha RGBA onto the retail opaque-black background."""

    if len(rgba) != WORDMARK_WIDTH * WORDMARK_HEIGHT * 4:
        raise ValidationError("prepared wordmark canvas has the wrong byte length")
    output = bytearray(len(rgba))
    transparent = 0
    for offset in range(0, len(rgba), 4):
        alpha = rgba[offset + 3]
        if alpha != 255:
            transparent += 1
        output[offset] = (rgba[offset] * alpha + 127) // 255
        output[offset + 1] = (rgba[offset + 1] * alpha + 127) // 255
        output[offset + 2] = (rgba[offset + 2] * alpha + 127) // 255
        output[offset + 3] = 255
    return bytes(output), transparent


def prepare_wordmark_png(
    source: Path,
    destination: Path,
    *,
    fit_mode: str = "contain",
) -> PreparedWordmark:
    """Fit ordinary art, flatten transparency, and publish one exact PNG."""

    if fit_mode not in WORDMARK_FIT_MODES:
        raise ValidationError("wordmark fit mode must be contain or cover")
    result = fit_image(
        Path(source), WORDMARK_WIDTH, WORDMARK_HEIGHT, mode=fit_mode
    )
    rgba, transparent = _flatten_black(result.rgba)
    payload = encode_rgba_png(WORDMARK_WIDTH, WORDMARK_HEIGHT, rgba)
    output = Path(destination).expanduser()
    if output.is_symlink() or os.path.lexists(output):
        raise ValidationError(f"refusing to overwrite prepared wordmark: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        output,
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short prepared-wordmark write")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        output.unlink(missing_ok=True)
        raise
    else:
        os.close(descriptor)
    return PreparedWordmark(
        output_path=output,
        fit_mode=fit_mode,
        source_width=result.source_width,
        source_height=result.source_height,
        fit_action=result.action,
        fit_description=result.describe(),
        transparent_source_pixels=transparent,
    )


__all__ = [
    "PreparedWordmark",
    "WORDMARK_FIT_MODES",
    "WORDMARK_HEIGHT",
    "WORDMARK_WIDTH",
    "prepare_wordmark_png",
]
