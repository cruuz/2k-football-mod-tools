"""Safe canonical recipe generation for the editor's simple typed workflows.

This module only inspects user-authored PNGs and creates new JSON recipe files.
It has no archive parser, raw-offset input, game-data output, or backend command
dispatch.  Existing destinations (including broken symlinks) are always
refused, and a failed write removes only the partially written inode that this
module exclusively created.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Mapping, Sequence

from PIL import Image, UnidentifiedImageError

from .errors import ModEditorError, OutputRefusedError, ValidationError


APF_JERSEY_RECIPE_SCHEMA = "apf2k8_jersey_color_recipe/v1"
APF_PANTS_RECIPE_SCHEMA = "apf2k8_pants_color_recipe/v1"
APF_HELMET_RECIPE_SCHEMA = "apf2k8_helmet_color_recipe/v1"
APF_SHOULDER_RECIPE_SCHEMA = "apf2k8_shoulder_color_recipe/v1"
NFL_SCOREBUG_RECIPE_SCHEMA = "nfl2k5_scorebug_mod_project/v1"

APF_JERSEY_DIMENSIONS = (1024, 1024)
APF_PANTS_DIMENSIONS = (512, 512)
APF_HELMET_DIMENSIONS = (256, 1024)
APF_SHOULDER_DIMENSIONS = (1024, 1024)
NFL_SCOREBUG_TARGET_DIMENSIONS: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        "score_buga": (64, 64),
        "shield_espn": (128, 64),
        "digital_font": (128, 128),
    }
)
NFL_SCOREBUG_TARGETS = tuple(NFL_SCOREBUG_TARGET_DIMENSIONS)

# These values are the complete source object required by the existing typed
# scorebug backend.  Recipe callers cannot supply, weaken, or replace them.
NFL_SCOREBUG_SOURCE_PIN: Mapping[str, str | int] = MappingProxyType(
    {
        "canonical_index_sha256": (
            "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"
        ),
        "canonical_index_size": 193_710_080,
        "default_xbe_sha256": (
            "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
        ),
        "default_xbe_size": 11_948_032,
        "scorebug_audit_sha256": (
            "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1"
        ),
        "scorebug_audit_size": 46_512,
        "xiso_sha256": (
            "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
        ),
        "xiso_size": 6_300_499_968,
    }
)

MAX_APF_PNG_BYTES = 64 * 1024 * 1024
MAX_NFL_PNG_BYTES = 32 * 1024 * 1024


class RecipeError(ValidationError):
    """A user-authored input cannot produce the requested typed recipe."""


@dataclass(frozen=True)
class ScorebugRecipeEdit:
    """One named scorebug target and its user-authored PNG."""

    target: str
    png: Path


@dataclass(frozen=True)
class _PngPin:
    path: Path
    size: int
    sha256: str
    width: int
    height: int
    mode: str


def canonical_recipe_json(value: object) -> bytes:
    """Return the canonical encoding required by both typed backends."""

    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RecipeError(message)


def _absolute_output(path: Path) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    if requested.suffix.lower() != ".json":
        raise OutputRefusedError("Recipe output must use a .json filename")
    if os.path.lexists(requested):
        raise OutputRefusedError(f"Recipe output already exists: {requested}")
    try:
        parent = requested.parent.lstat()
    except FileNotFoundError as exc:
        raise OutputRefusedError(
            f"Recipe output parent does not exist: {requested.parent}"
        ) from exc
    if not stat.S_ISDIR(parent.st_mode) or stat.S_ISLNK(parent.st_mode):
        raise OutputRefusedError(
            "Recipe output parent must be a non-symlink directory"
        )
    return requested.resolve(strict=False)


def _read_png(
    path: Path,
    dimensions: tuple[int, int],
    *,
    exact_rgba: bool,
    fully_opaque: bool = False,
    blue_zero: bool = False,
    maximum: int,
    label: str,
) -> _PngPin:
    requested = path.expanduser()
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise RecipeError(f"{label} does not exist: {requested}") from exc
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"{label} must be a non-symlink regular file",
    )
    _require(
        0 < supplied.st_size <= maximum,
        f"{label} size is outside the allowed range",
    )
    resolved = requested.resolve(strict=True)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(resolved, flags)
    except OSError as exc:
        raise RecipeError(f"Cannot open {label} read-only: {exc}") from exc
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
        payload = b"".join(chunks)
    finally:
        os.close(descriptor)

    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            _require(image.format == "PNG", f"{label} is not a decoded PNG")
            _require(
                image.size == dimensions,
                f"{label} must be exactly {dimensions[0]}x{dimensions[1]}",
            )
            if exact_rgba:
                _require(
                    image.mode == "RGBA",
                    f"{label} must be stored as exact RGBA",
                )
            if fully_opaque:
                _require(
                    image.mode == "RGBA"
                    and image.getchannel("A").getextrema() == (255, 255),
                    f"{label} must be fully opaque",
                )
            if blue_zero:
                _require(
                    image.mode == "RGBA"
                    and image.getchannel("B").getextrema() == (0, 0),
                    f"{label} B channel must be exactly zero",
                )
            # Force a complete decode in addition to the format/mode checks.
            image.convert("RGBA").tobytes()
            mode = image.mode
    except (UnidentifiedImageError, OSError) as exc:
        raise RecipeError(f"Cannot decode {label}: {exc}") from exc

    try:
        current = resolved.stat(follow_symlinks=False)
    except FileNotFoundError as exc:
        raise RecipeError(f"{label} disappeared after decoding") from exc
    _require(
        stat.S_ISREG(current.st_mode)
        and (current.st_dev, current.st_ino, current.st_size)
        == (identity[0], identity[1], len(payload)),
        f"{label} changed while decoding",
    )
    return _PngPin(
        resolved,
        len(payload),
        hashlib.sha256(payload).hexdigest(),
        dimensions[0],
        dimensions[1],
        mode,
    )


def _recipe_path_reference(png: Path, recipe_parent: Path) -> str:
    """Prefer a portable child path; otherwise retain an exact absolute path."""

    try:
        relative = png.relative_to(recipe_parent)
    except ValueError:
        return os.fspath(png)
    return relative.as_posix()


def _write_payload(descriptor: int, payload: bytes) -> None:
    cursor = 0
    while cursor < len(payload):
        written = os.write(descriptor, payload[cursor:])
        if written <= 0:
            raise OSError("short write while creating recipe")
        cursor += written


def _cleanup_owned_output(path: Path, identity: tuple[int, int] | None) -> None:
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
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _create_recipe(path: Path, document: object) -> Path:
    payload = canonical_recipe_json(document)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor: int | None = None
    identity: tuple[int, int] | None = None
    try:
        try:
            descriptor = os.open(path, flags, 0o644)
        except FileExistsError as exc:
            raise OutputRefusedError(f"Recipe output already exists: {path}") from exc
        opened = os.fstat(descriptor)
        _require(stat.S_ISREG(opened.st_mode), "Recipe output is not a regular file")
        identity = (opened.st_dev, opened.st_ino)
        _write_payload(descriptor, payload)
        os.fsync(descriptor)
        current = path.lstat()
        _require(
            stat.S_ISREG(current.st_mode)
            and not stat.S_ISLNK(current.st_mode)
            and (current.st_dev, current.st_ino, current.st_size)
            == (identity[0], identity[1], len(payload)),
            "Recipe output pathname or size changed while writing",
        )
    except Exception as exc:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        _cleanup_owned_output(path, identity)
        if isinstance(exc, ModEditorError):
            raise
        raise RecipeError(f"Could not create recipe: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return path


def create_apf_jersey_recipe(
    *, output: Path, asset_index: int, png: Path
) -> Path:
    """Validate one APF jersey PNG and exclusively create its typed recipe."""

    destination = _absolute_output(output)
    _require(
        type(asset_index) is int and 0 <= asset_index <= 23,
        "APF jersey asset_index must be an integer in 0..23",
    )
    pin = _read_png(
        png,
        APF_JERSEY_DIMENSIONS,
        exact_rgba=True,
        maximum=MAX_APF_PNG_BYTES,
        label="APF jersey PNG",
    )
    document = {
        "schema": APF_JERSEY_RECIPE_SCHEMA,
        "asset_index": asset_index,
        "png": _recipe_path_reference(pin.path, destination.parent),
    }
    return _create_recipe(destination, document)


def create_apf_pants_recipe(
    *, output: Path, asset_index: int, png: Path
) -> Path:
    """Validate one opaque APF pants PNG and exclusively create its recipe."""

    destination = _absolute_output(output)
    _require(
        type(asset_index) is int and 0 <= asset_index <= 23,
        "APF pants asset_index must be an integer in 0..23",
    )
    pin = _read_png(
        png,
        APF_PANTS_DIMENSIONS,
        exact_rgba=True,
        fully_opaque=True,
        maximum=MAX_APF_PNG_BYTES,
        label="APF pants PNG",
    )
    document = {
        "schema": APF_PANTS_RECIPE_SCHEMA,
        "asset_index": asset_index,
        "png": _recipe_path_reference(pin.path, destination.parent),
    }
    return _create_recipe(destination, document)


def create_apf_helmet_recipe(
    *, output: Path, asset_index: int, png: Path
) -> Path:
    """Create a recipe for raw helmet DXN data without naming its semantics."""

    destination = _absolute_output(output)
    _require(
        type(asset_index) is int and 0 <= asset_index <= 23,
        "APF helmet asset_index must be an integer in 0..23",
    )
    pin = _read_png(
        png,
        APF_HELMET_DIMENSIONS,
        exact_rgba=True,
        fully_opaque=True,
        blue_zero=True,
        maximum=MAX_APF_PNG_BYTES,
        label="APF helmet two-channel PNG",
    )
    document = {
        "schema": APF_HELMET_RECIPE_SCHEMA,
        "asset_index": asset_index,
        "png": _recipe_path_reference(pin.path, destination.parent),
    }
    return _create_recipe(destination, document)


def create_apf_shoulder_recipe(
    *, output: Path, asset_index: int, png: Path
) -> Path:
    """Validate one APF shoulder-color PNG and create its typed recipe."""

    destination = _absolute_output(output)
    _require(
        type(asset_index) is int and 0 <= asset_index <= 23,
        "APF shoulder asset_index must be an integer in 0..23",
    )
    pin = _read_png(
        png,
        APF_SHOULDER_DIMENSIONS,
        exact_rgba=True,
        maximum=MAX_APF_PNG_BYTES,
        label="APF shoulder-color PNG",
    )
    document = {
        "schema": APF_SHOULDER_RECIPE_SCHEMA,
        "asset_index": asset_index,
        "png": _recipe_path_reference(pin.path, destination.parent),
    }
    return _create_recipe(destination, document)


def create_nfl_scorebug_recipe(
    *,
    output: Path,
    purpose: str,
    edits: Sequence[ScorebugRecipeEdit],
) -> Path:
    """Validate one to three unique NFL scorebug PNGs and create a recipe."""

    destination = _absolute_output(output)
    _require(
        type(purpose) is str
        and 0 < len(purpose) <= 4096
        and "\0" not in purpose,
        "NFL scorebug purpose must contain 1..4096 characters and no NUL",
    )
    _require(
        isinstance(edits, Sequence) and not isinstance(edits, (str, bytes))
        and 1 <= len(edits) <= 3,
        "NFL scorebug recipe requires one to three edits",
    )
    targets: list[str] = []
    prepared: list[dict[str, object]] = []
    for index, edit in enumerate(edits):
        _require(
            isinstance(edit, ScorebugRecipeEdit),
            f"NFL scorebug edit {index} is not a ScorebugRecipeEdit",
        )
        _require(
            type(edit.target) is str
            and edit.target in NFL_SCOREBUG_TARGET_DIMENSIONS,
            f"NFL scorebug edit {index} target is not proved",
        )
        _require(
            edit.target not in targets,
            "Each NFL scorebug target may appear at most once",
        )
        targets.append(edit.target)
        pin = _read_png(
            Path(edit.png),
            NFL_SCOREBUG_TARGET_DIMENSIONS[edit.target],
            exact_rgba=True,
            maximum=MAX_NFL_PNG_BYTES,
            label=f"{edit.target} PNG",
        )
        prepared.append(
            {
                "target": edit.target,
                "png": _recipe_path_reference(pin.path, destination.parent),
                "png_size": pin.size,
                "png_sha256": pin.sha256,
            }
        )
    target_order = {target: index for index, target in enumerate(NFL_SCOREBUG_TARGETS)}
    prepared.sort(key=lambda record: target_order[str(record["target"])])
    document = {
        "schema": NFL_SCOREBUG_RECIPE_SCHEMA,
        "purpose": purpose,
        "source": dict(NFL_SCOREBUG_SOURCE_PIN),
        "edits": prepared,
    }
    return _create_recipe(destination, document)


__all__ = [
    "APF_HELMET_DIMENSIONS",
    "APF_HELMET_RECIPE_SCHEMA",
    "APF_JERSEY_DIMENSIONS",
    "APF_JERSEY_RECIPE_SCHEMA",
    "APF_PANTS_DIMENSIONS",
    "APF_PANTS_RECIPE_SCHEMA",
    "APF_SHOULDER_DIMENSIONS",
    "APF_SHOULDER_RECIPE_SCHEMA",
    "NFL_SCOREBUG_RECIPE_SCHEMA",
    "NFL_SCOREBUG_SOURCE_PIN",
    "NFL_SCOREBUG_TARGET_DIMENSIONS",
    "NFL_SCOREBUG_TARGETS",
    "RecipeError",
    "ScorebugRecipeEdit",
    "canonical_recipe_json",
    "create_apf_jersey_recipe",
    "create_apf_helmet_recipe",
    "create_apf_pants_recipe",
    "create_apf_shoulder_recipe",
    "create_nfl_scorebug_recipe",
]
