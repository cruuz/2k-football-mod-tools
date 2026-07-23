"""Canonical recipe contract for APF 2K8's shared ``digital_font``.

The recipe names one fixed global UI texture and a user-authored PNG.  Xenos
DXT5A stores only the PNG alpha plane, so creation and loading both require an
exact 128x128 RGBA PNG whose RGB channels are solid white.  The complete PNG
and stored alpha plane are content-pinned without exposing archive offsets.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from PIL import Image, UnidentifiedImageError

from .errors import ModEditorError, OutputRefusedError, ValidationError


APF_DIGITAL_FONT_RECIPE_SCHEMA = "apf2k8_digital_font_recipe/v1"
APF_DIGITAL_FONT_TARGET = "digital_font"
APF_DIGITAL_FONT_SCOPE = "shared-global-ui"
APF_DIGITAL_FONT_STORED_CHANNEL = "alpha"
APF_DIGITAL_FONT_DIMENSIONS = (128, 128)
MAX_APF_DIGITAL_FONT_PNG_BYTES = 16 * 1024 * 1024
MAX_APF_DIGITAL_FONT_RECIPE_BYTES = 64 * 1024

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ApfDigitalFontRecipeError(ValidationError):
    """The digital-font recipe or PNG violates its fixed alpha-only contract."""


@dataclass(frozen=True)
class ApfDigitalFontRecipe:
    recipe_path: Path
    png_path: Path
    png_size: int
    png_sha256: str
    alpha_sha256: str


@dataclass(frozen=True)
class _RegularBytes:
    path: Path
    payload: bytes


def canonical_apf_digital_font_recipe_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ApfDigitalFontRecipeError(message)


def _read_regular(path: Path, *, maximum: int, label: str) -> _RegularBytes:
    requested = path.expanduser()
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise ApfDigitalFontRecipeError(f"{label} does not exist: {requested}") from exc
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"{label} must be a non-symlink regular file",
    )
    _require(0 < supplied.st_size <= maximum, f"{label} size is outside its limit")
    resolved = requested.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        _require(
            stat.S_ISREG(opened.st_mode)
            and identity == (supplied.st_dev, supplied.st_ino)
            and opened.st_size == supplied.st_size,
            f"{label} changed before its read-only open",
        )
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            _require(bool(chunk), f"{label} shortened while reading")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(not os.read(descriptor, 1), f"{label} grew while reading")
        current = resolved.stat(follow_symlinks=False)
        _require(
            (current.st_dev, current.st_ino, current.st_size)
            == (identity[0], identity[1], opened.st_size),
            f"{label} pathname changed while reading",
        )
        return _RegularBytes(resolved, b"".join(chunks))
    finally:
        os.close(descriptor)


def _decode_png(file: _RegularBytes) -> tuple[bytes, bytes]:
    try:
        with Image.open(io.BytesIO(file.payload)) as image:
            image.load()
            _require(
                image.format == "PNG"
                and image.size == APF_DIGITAL_FONT_DIMENSIONS
                and image.mode == "RGBA",
                "APF digital_font PNG must be exact 128x128 RGBA PNG",
            )
            rgba = image.tobytes()
    except (UnidentifiedImageError, OSError) as exc:
        raise ApfDigitalFontRecipeError(
            f"Could not decode APF digital_font PNG: {exc}"
        ) from exc
    _require(
        all(
            rgba[offset : offset + 3] == b"\xff\xff\xff"
            for offset in range(0, len(rgba), 4)
        ),
        "APF digital_font PNG RGB must be solid white; DXT5A stores alpha only",
    )
    alpha = rgba[3::4]
    _require(
        len(alpha) == APF_DIGITAL_FONT_DIMENSIONS[0] * APF_DIGITAL_FONT_DIMENSIONS[1],
        "APF digital_font alpha plane length changed",
    )
    return rgba, alpha


def _png(path: Path) -> tuple[_RegularBytes, bytes]:
    file = _read_regular(
        path,
        maximum=MAX_APF_DIGITAL_FONT_PNG_BYTES,
        label="APF digital_font PNG",
    )
    _require(file.path.suffix.lower() == ".png", "APF digital_font input must use .png")
    _rgba, alpha = _decode_png(file)
    return file, alpha


def _output_path(path: Path) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.suffix.lower() != ".json":
        raise OutputRefusedError("APF digital_font recipe output must use .json")
    if os.path.lexists(requested):
        raise OutputRefusedError(
            f"APF digital_font recipe output already exists: {requested}"
        )
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise OutputRefusedError(
            f"APF digital_font recipe parent does not exist: {requested.parent}"
        ) from exc
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise OutputRefusedError(
            "APF digital_font recipe parent must be a non-symlink directory"
        )
    return requested.resolve(strict=False)


def _path_reference(source: Path, parent: Path) -> str:
    try:
        return source.relative_to(parent).as_posix()
    except ValueError:
        return os.fspath(source)


def _remove_owned(path: Path, identity: tuple[int, int] | None) -> None:
    if identity is None:
        return
    try:
        current = path.lstat()
    except FileNotFoundError:
        return
    if (
        stat.S_ISREG(current.st_mode)
        and not stat.S_ISLNK(current.st_mode)
        and (current.st_dev, current.st_ino) == identity
    ):
        path.unlink(missing_ok=True)


def _write_new(path: Path, document: object) -> Path:
    payload = canonical_apf_digital_font_recipe_json(document)
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
        opened = os.fstat(descriptor)
        _require(stat.S_ISREG(opened.st_mode), "APF digital_font recipe is not regular")
        identity = (opened.st_dev, opened.st_ino)
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            if written <= 0:
                raise OSError("short APF digital_font recipe write")
            cursor += written
        os.fsync(descriptor)
        current = path.lstat()
        _require(
            stat.S_ISREG(current.st_mode)
            and not stat.S_ISLNK(current.st_mode)
            and (current.st_dev, current.st_ino, current.st_size)
            == (identity[0], identity[1], len(payload)),
            "APF digital_font recipe pathname or size changed while writing",
        )
    except FileExistsError as exc:
        raise OutputRefusedError(
            f"APF digital_font recipe output already exists: {path}"
        ) from exc
    except Exception as exc:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        _remove_owned(path, identity)
        if isinstance(exc, ModEditorError):
            raise
        raise ApfDigitalFontRecipeError(
            f"Could not create APF digital_font recipe: {exc}"
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return path


def create_apf_digital_font_recipe(*, output: Path, png: Path) -> Path:
    """Create one exclusive, content-pinned alpha-only font recipe."""

    destination = _output_path(output)
    png_file, alpha = _png(png)
    _require(
        png_file.path != destination,
        "APF digital_font recipe output cannot replace the PNG input",
    )
    document = {
        "alpha_sha256": hashlib.sha256(alpha).hexdigest(),
        "png": _path_reference(png_file.path, destination.parent),
        "png_sha256": hashlib.sha256(png_file.payload).hexdigest(),
        "png_size": len(png_file.payload),
        "schema": APF_DIGITAL_FONT_RECIPE_SCHEMA,
        "scope": APF_DIGITAL_FONT_SCOPE,
        "stored_channel": APF_DIGITAL_FONT_STORED_CHANNEL,
        "target": APF_DIGITAL_FONT_TARGET,
    }
    return _write_new(destination, document)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        _require(key not in value, f"APF digital_font recipe has duplicate key: {key}")
        value[key] = item
    return value


def load_apf_digital_font_recipe(path: Path) -> ApfDigitalFontRecipe:
    """Load canonical JSON and recheck the PNG plus its alpha content pin."""

    recipe = _read_regular(
        path,
        maximum=MAX_APF_DIGITAL_FONT_RECIPE_BYTES,
        label="APF digital_font recipe",
    )
    try:
        value = json.loads(recipe.payload, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ApfDigitalFontRecipeError(
            "APF digital_font recipe is invalid UTF-8 JSON"
        ) from exc
    _require(
        recipe.payload == canonical_apf_digital_font_recipe_json(value),
        "APF digital_font recipe must use canonical sorted pretty JSON",
    )
    fields = {
        "alpha_sha256",
        "png",
        "png_sha256",
        "png_size",
        "schema",
        "scope",
        "stored_channel",
        "target",
    }
    _require(isinstance(value, dict) and set(value) == fields, "APF digital_font recipe fields differ")
    _require(value.get("schema") == APF_DIGITAL_FONT_RECIPE_SCHEMA, "APF digital_font recipe schema differs")
    _require(value.get("target") == APF_DIGITAL_FONT_TARGET, "APF digital_font target must be fixed")
    _require(value.get("scope") == APF_DIGITAL_FONT_SCOPE, "APF digital_font scope must remain global")
    _require(
        value.get("stored_channel") == APF_DIGITAL_FONT_STORED_CHANNEL,
        "APF digital_font recipe must identify alpha as the only stored channel",
    )
    png_value = value.get("png")
    _require(
        isinstance(png_value, str) and png_value and "\0" not in png_value,
        "APF digital_font recipe png must be a non-empty path string",
    )
    png_path = Path(png_value).expanduser()
    if not png_path.is_absolute():
        png_path = recipe.path.parent / png_path
    png_file, alpha = _png(png_path)
    _require(png_file.path != recipe.path, "APF digital_font PNG and recipe must differ")
    png_size = value.get("png_size")
    _require(
        type(png_size) is int and png_size == len(png_file.payload),
        "APF digital_font PNG size pin differs",
    )
    png_sha = value.get("png_sha256")
    alpha_sha = value.get("alpha_sha256")
    _require(
        isinstance(png_sha, str)
        and _SHA256_RE.fullmatch(png_sha) is not None
        and png_sha == hashlib.sha256(png_file.payload).hexdigest(),
        "APF digital_font PNG SHA-256 pin differs",
    )
    _require(
        isinstance(alpha_sha, str)
        and _SHA256_RE.fullmatch(alpha_sha) is not None
        and alpha_sha == hashlib.sha256(alpha).hexdigest(),
        "APF digital_font alpha SHA-256 pin differs",
    )
    return ApfDigitalFontRecipe(
        recipe_path=recipe.path,
        png_path=png_file.path,
        png_size=png_size,
        png_sha256=png_sha,
        alpha_sha256=alpha_sha,
    )


__all__ = [
    "APF_DIGITAL_FONT_DIMENSIONS",
    "APF_DIGITAL_FONT_RECIPE_SCHEMA",
    "APF_DIGITAL_FONT_SCOPE",
    "APF_DIGITAL_FONT_STORED_CHANNEL",
    "APF_DIGITAL_FONT_TARGET",
    "ApfDigitalFontRecipe",
    "ApfDigitalFontRecipeError",
    "canonical_apf_digital_font_recipe_json",
    "create_apf_digital_font_recipe",
    "load_apf_digital_font_recipe",
]
