"""Portable, retail-free high-resolution texture authoring masters.

The Xbox and Xbox 360 games still require their proved native texture sizes.
This module preserves what the artist imported *before* that destructive
compile step, together with a deterministic canvas transform.  A bundle also
contains the exact native PNG used by the game writer and a 4x authoring
preview rendered directly from the preserved source.

The preview is deliberately not an emulator texture pack.  Rendering a game at
4x resolution does not add texels to a native game texture, and RPCS3 does not
have a locally proved replacement-file mapping for either editor.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
from typing import Any, Mapping
from uuid import uuid4
import zipfile

from .errors import ValidationError
from .json_stream import read_bounded_regular_file


TEXTURE_MASTER_SCHEMA = "2k_texture_authoring_master/v1"
TEXTURE_MASTER_EXTENSION = ".2ktexmaster"
SOURCE_MEMBER = "master.source"
NATIVE_MEMBER = "native.png"
NATIVE_BASELINE_MEMBER = "native-before-editor.png"
MANIFEST_MEMBER = "manifest.json"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_PNG_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024
MAX_EDITOR_TRANSFORM_BYTES = 64 * 1024
MAX_IMAGE_PIXELS = 64 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXPANDED_BYTES = MAX_SOURCE_BYTES + (3 * MAX_PNG_BYTES) + MAX_MANIFEST_BYTES
HIGH_RES_SCALES = (2, 4)
RESAMPLE_MODES = ("bicubic", "lanczos", "nearest")
RPCS3_TEXTURE_REPLACEMENT_EXPORT_SUPPORTED = False


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100600 << 16
    info.create_system = 3
    return info


def _reject_duplicate_json_pairs(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValidationError(
                f"Texture-master JSON contains a duplicate key: {key!r}."
            )
        document[key] = value
    return document


@dataclass(frozen=True, slots=True)
class AuthoringTransform:
    """One Photoshop-style source placement in native canvas coordinates."""

    center_x: float
    center_y: float
    width: float
    height: float
    rotation_degrees: float = 0.0
    resample: str = "bicubic"

    def validate(self, canvas_width: int, canvas_height: int) -> None:
        values = (
            self.center_x,
            self.center_y,
            self.width,
            self.height,
            self.rotation_degrees,
        )
        _require(all(math.isfinite(value) for value in values),
                 "Texture-master transform values must be finite.")
        _require(self.resample in RESAMPLE_MODES,
                 "Texture-master resampling must be bicubic, Lanczos, or nearest.")
        _require(
            self.resample != "lanczos"
            or math.isclose(
                self.rotation_degrees % 360.0, 0.0, abs_tol=1e-9
            ),
            "Lanczos texture-master placement does not support rotation.",
        )
        _require(self.width > 0.0 and self.height > 0.0,
                 "Texture-master width and height must be positive.")
        bound = float(max(canvas_width, canvas_height) * 64)
        _require(
            abs(self.center_x) <= bound
            and abs(self.center_y) <= bound
            and self.width <= bound
            and self.height <= bound,
            "Texture-master placement is outside the supported canvas range.",
        )
        _require(abs(self.rotation_degrees) <= 360_000.0,
                 "Texture-master rotation is outside the supported range.")

    def document(self) -> dict[str, object]:
        return {
            "center_x": self.center_x,
            "center_y": self.center_y,
            "height": self.height,
            "resample": self.resample,
            "rotation_degrees": self.rotation_degrees,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class TextureMasterBundle:
    """Validated in-memory contents of one authoring-master archive."""

    manifest: Mapping[str, Any]
    source_bytes: bytes
    native_png: bytes
    high_resolution_png: bytes
    native_baseline_png: bytes | None = None

    @property
    def asset_id(self) -> str:
        return str(self.manifest["asset_id"])

    @property
    def high_resolution_scale(self) -> int:
        return int(self.manifest["high_resolution_preview"]["scale"])


def texture_master_source_sha256(path: Path) -> str:
    """Fingerprint the exact bounded source bytes retained by an import flow."""

    _resolved, payload = read_bounded_regular_file(
        Path(path), "Texture-master source image", maximum=MAX_SOURCE_BYTES
    )
    # Decode now as well: a stable hash of an arbitrary non-image must never
    # enable a GUI action labelled as an image authoring master.
    _decode_image(payload, "Texture-master source image")
    return _sha256(payload)


def snapshot_texture_master_source(
    source: Path, destination: Path
) -> tuple[Path, str]:
    """Privately preserve exact imported bytes for a later explicit export."""

    _resolved, payload = read_bounded_regular_file(
        Path(source), "Texture-master source image", maximum=MAX_SOURCE_BYTES
    )
    _decode_image(payload, "Texture-master source image")
    output = Path(destination).expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    output = Path(os.path.abspath(os.fspath(output)))
    output.parent.mkdir(parents=True, exist_ok=True)
    _require(not output.parent.is_symlink(),
             "Texture-master snapshot folder must not be a symbolic link.")
    _require(not os.path.lexists(output),
             f"A texture-master snapshot already exists there: {output}")
    try:
        descriptor = os.open(
            output,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except OSError as exc:
        raise ValidationError(
            f"Could not preserve the texture-master source: {exc}"
        ) from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output.resolve(strict=True), _sha256(payload)


def _normalized_editor_transform(
    supplied: Mapping[str, object] | None,
    fallback: AuthoringTransform,
) -> dict[str, object]:
    value: object = (
        dict(supplied)
        if supplied is not None
        else {
            "coordinate_space": "native-texture-pixels",
            "operation": "affine-master-placement",
            **fallback.document(),
        }
    )
    try:
        payload = (
            json.dumps(value, sort_keys=True, allow_nan=False) + "\n"
        ).encode("utf-8")
        normalized = json.loads(
            payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_pairs
        )
    except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(
            "Texture-master editor transform must contain bounded JSON values."
        ) from exc
    _require(isinstance(normalized, dict) and bool(normalized),
             "Texture-master editor transform must be a nonempty object.")
    _require(len(payload) <= MAX_EDITOR_TRANSFORM_BYTES,
             "Texture-master editor transform exceeds 64 KiB.")
    return normalized


def fit_transform(
    source_width: int,
    source_height: int,
    canvas_width: int,
    canvas_height: int,
    *,
    mode: str = "contain",
    resample: str = "bicubic",
) -> AuthoringTransform:
    """Return a centred contain/cover/scale placement without touching pixels."""

    _require(
        source_width > 0 and source_height > 0
        and canvas_width > 0 and canvas_height > 0,
        "Texture-master source and canvas dimensions must be positive.",
    )
    _require(mode in {"auto", "contain", "cover", "scale"},
             "Texture-master fit mode must be auto, contain, cover, or scale.")
    if mode == "auto":
        mode = (
            "scale"
            if source_width * canvas_height == source_height * canvas_width
            else "cover"
        )
    if mode == "scale":
        width = float(canvas_width)
        height = float(canvas_height)
        center_x = canvas_width / 2.0
        center_y = canvas_height / 2.0
    else:
        factor = (
            min(canvas_width / source_width, canvas_height / source_height)
            if mode == "contain"
            else max(canvas_width / source_width, canvas_height / source_height)
        )
        if mode == "contain":
            width = float(max(1, min(canvas_width, round(source_width * factor))))
            height = float(max(1, min(canvas_height, round(source_height * factor))))
            left = (canvas_width - int(width)) // 2
            top = (canvas_height - int(height)) // 2
            center_x = left + width / 2.0
            center_y = top + height / 2.0
        else:
            width = float(max(canvas_width, round(source_width * factor)))
            height = float(max(canvas_height, round(source_height * factor)))
            left = (int(width) - canvas_width) // 2
            top = (int(height) - canvas_height) // 2
            center_x = width / 2.0 - left
            center_y = height / 2.0 - top
    result = AuthoringTransform(
        center_x=center_x,
        center_y=center_y,
        width=width,
        height=height,
        resample=resample,
    )
    result.validate(canvas_width, canvas_height)
    return result


def _decode_image(payload: bytes, label: str) -> tuple[Any, str, str]:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - Pillow ships with the app
        raise ValidationError("Pillow is required for texture-master images.") from exc
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(io.BytesIO(payload)) as opened:
            source_format = str(opened.format or "UNKNOWN").upper()
            source_mode = str(opened.mode)
            opened.load()
            image = opened.convert("RGBA")
    except Exception as exc:  # noqa: BLE001 - Pillow has format-specific errors
        raise ValidationError(f"{label} could not be decoded as an image: {exc}") from exc
    width, height = image.size
    _require(width > 0 and height > 0, f"{label} has no pixels.")
    _require(width * height <= MAX_IMAGE_PIXELS,
             f"{label} exceeds the {MAX_IMAGE_PIXELS:,}-pixel safety limit.")
    return image, source_format, source_mode


def _encode_png(image: Any) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    payload = output.getvalue()
    _require(0 < len(payload) <= MAX_PNG_BYTES,
             "Generated texture-master PNG exceeds the 128 MiB safety limit.")
    return payload


def render_master(
    image: Any,
    canvas_width: int,
    canvas_height: int,
    transform: AuthoringTransform,
    *,
    scale: int = 1,
) -> Any:
    """Render directly from the full-resolution source at the requested scale."""

    from PIL import Image

    _require(type(scale) is int and scale >= 1,
             "Texture-master render scale must be a positive integer.")
    _require(canvas_width > 0 and canvas_height > 0,
             "Texture-master canvas dimensions must be positive.")
    output_width = canvas_width * scale
    output_height = canvas_height * scale
    _require(output_width * output_height <= MAX_IMAGE_PIXELS,
             "Texture-master output exceeds the 64-megapixel safety limit.")
    transform.validate(canvas_width, canvas_height)
    source = image.convert("RGBA")
    source_width, source_height = source.size
    if transform.resample == "lanczos":
        placed_width = max(1, int(round(transform.width * scale)))
        placed_height = max(1, int(round(transform.height * scale)))
        resampling = getattr(Image, "Resampling", Image)
        placed = source.resize(
            (placed_width, placed_height), getattr(resampling, "LANCZOS")
        )
        left = int(round(transform.center_x * scale - placed_width / 2.0))
        top = int(round(transform.center_y * scale - placed_height / 2.0))
        output = Image.new("RGBA", (output_width, output_height), (0, 0, 0, 0))
        output.paste(placed, (left, top))
        return output
    scale_x = (transform.width * scale) / source_width
    scale_y = (transform.height * scale) / source_height
    center_x = transform.center_x * scale
    center_y = transform.center_y * scale
    angle = math.radians(transform.rotation_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    a_value = cosine / scale_x
    b_value = sine / scale_x
    d_value = -sine / scale_y
    e_value = cosine / scale_y
    source_center_x = source_width / 2.0
    source_center_y = source_height / 2.0
    c_value = source_center_x - a_value * center_x - b_value * center_y
    f_value = source_center_y - d_value * center_x - e_value * center_y
    affine = getattr(getattr(Image, "Transform", Image), "AFFINE")
    resampling = getattr(Image, "Resampling", Image)
    filter_value = (
        getattr(resampling, "NEAREST")
        if transform.resample == "nearest"
        else getattr(resampling, "BICUBIC")
    )
    return source.transform(
        (output_width, output_height),
        affine,
        (a_value, b_value, c_value, d_value, e_value, f_value),
        resample=filter_value,
        fillcolor=(0, 0, 0, 0),
    )


def _read_native_png(path: Path, width: int, height: int) -> bytes:
    _resolved, payload = read_bounded_regular_file(
        Path(path), "Compiled native texture PNG", maximum=MAX_PNG_BYTES
    )
    image, image_format, source_mode = _decode_image(
        payload, "Compiled native texture PNG"
    )
    _require(image_format == "PNG" and source_mode == "RGBA",
             "Compiled native texture must be an 8-bit RGBA PNG.")
    _require(image.size == (width, height),
             f"Compiled native texture must be exactly {width}x{height}.")
    return payload


def _native_raster_edit_preview(
    preview: Any,
    baseline: Any,
    final: Any,
    *,
    scale: int,
) -> tuple[Any, int]:
    """Apply exact native-canvas pixel edits over a direct master render.

    Unchanged native pixels keep the full-resolution source render. Changed
    pixels come from the editor's exact final native canvas and are expanded
    with nearest-neighbour sampling, matching the pixel editor's semantics.
    """

    from PIL import Image

    _require(baseline.size == final.size,
             "Texture-master native edit canvases have different dimensions.")
    before = baseline.convert("RGBA").tobytes()
    after = final.convert("RGBA").tobytes()
    _require(len(before) == len(after) and len(before) % 4 == 0,
             "Texture-master native edit pixels are malformed.")
    changed = bytearray(len(before) // 4)
    changed_count = 0
    for offset in range(0, len(before), 4):
        if before[offset:offset + 4] != after[offset:offset + 4]:
            changed[offset // 4] = 255
            changed_count += 1
    if changed_count == 0:
        return preview, 0
    mask = Image.frombytes("L", baseline.size, bytes(changed))
    resampling = getattr(Image, "Resampling", Image)
    output_size = (baseline.width * scale, baseline.height * scale)
    expanded_final = final.convert("RGBA").resize(
        output_size, getattr(resampling, "NEAREST")
    )
    expanded_mask = mask.resize(output_size, getattr(resampling, "NEAREST"))
    composed = preview.copy()
    composed.paste(expanded_final, (0, 0), expanded_mask)
    return composed, changed_count


def _destination(path: Path) -> Path:
    requested = Path(path).expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    requested = Path(os.path.abspath(os.fspath(requested)))
    _require(requested.suffix.casefold() == TEXTURE_MASTER_EXTENSION,
             f"Texture masters must use {TEXTURE_MASTER_EXTENSION}.")
    requested.parent.mkdir(parents=True, exist_ok=True)
    _require(not requested.parent.is_symlink(),
             "Choose a texture-master folder that is not a symbolic link.")
    _require(not os.path.lexists(requested),
             f"A file already exists there: {requested}")
    return requested


def save_texture_master_bundle(
    *,
    source_image: Path,
    destination: Path,
    asset_id: str,
    editor_target: str,
    native_width: int,
    native_height: int,
    transform: AuthoringTransform | None = None,
    fit_mode: str = "contain",
    high_resolution_scale: int = 4,
    compiled_native_png: Path | None = None,
    compiled_native_baseline_png: Path | None = None,
    expected_source_sha256: str | None = None,
    editor_transform: Mapping[str, object] | None = None,
) -> Path:
    """Create one non-overwriting authoring master plus exact native output.

    ``compiled_native_png`` is for game-specific compilers such as APF's
    semantic region-mask route.  When omitted, this function renders the native
    PNG from the source and transform itself.  In both cases the high-resolution
    preview is rendered directly from the preserved source.
    """

    _require(isinstance(asset_id, str) and 0 < len(asset_id) <= 512,
             "Texture-master asset ID must be 1 to 512 characters.")
    _require(isinstance(editor_target, str) and 0 < len(editor_target) <= 128,
             "Texture-master editor target must be 1 to 128 characters.")
    _require(type(native_width) is int and type(native_height) is int
             and native_width > 0 and native_height > 0,
             "Texture-master native dimensions must be positive integers.")
    _require(native_width * native_height <= MAX_IMAGE_PIXELS,
             "Texture-master native texture exceeds the pixel safety limit.")
    _require(high_resolution_scale in HIGH_RES_SCALES,
             "Texture-master high-resolution scale must be 2x or 4x.")
    _require(
        native_width * native_height * high_resolution_scale ** 2
        <= MAX_IMAGE_PIXELS,
        "Texture-master high-resolution preview exceeds the pixel safety limit.",
    )

    _source_path, source_payload = read_bounded_regular_file(
        Path(source_image), "Texture-master source image", maximum=MAX_SOURCE_BYTES
    )
    if expected_source_sha256 is not None:
        _require(
            isinstance(expected_source_sha256, str)
            and len(expected_source_sha256) == 64
            and all(
                character in "0123456789abcdef"
                for character in expected_source_sha256
            ),
            "Expected texture-master source SHA-256 is malformed.",
        )
        _require(
            _sha256(source_payload) == expected_source_sha256,
            "The imported full-resolution source changed outside Mod Studio. "
            "Import it again before saving an authoring master.",
        )
    source, source_format, source_mode = _decode_image(
        source_payload, "Texture-master source image"
    )
    source_width, source_height = source.size
    selected_transform = transform or fit_transform(
        source_width,
        source_height,
        native_width,
        native_height,
        mode=fit_mode,
    )
    selected_transform.validate(native_width, native_height)
    selected_editor_transform = _normalized_editor_transform(
        editor_transform, selected_transform
    )
    rendered_native = render_master(
        source, native_width, native_height, selected_transform
    )
    if compiled_native_png is None:
        native_payload = _encode_png(rendered_native)
        native_generation = "rendered-from-master"
    else:
        native_payload = _read_native_png(
            Path(compiled_native_png), native_width, native_height
        )
        native_generation = "supplied-game-compiled"
    preview = render_master(
        source,
        native_width,
        native_height,
        selected_transform,
        scale=high_resolution_scale,
    )
    baseline_payload: bytes | None = None
    native_raster_edit: dict[str, object] | None = None
    preview_composition = "direct-master"
    if compiled_native_baseline_png is not None:
        _require(compiled_native_png is not None,
                 "A native edit baseline requires an exact compiled native PNG.")
        baseline_payload = _read_native_png(
            Path(compiled_native_baseline_png), native_width, native_height
        )
        baseline_image, _format, _mode = _decode_image(
            baseline_payload, "Texture-master native edit baseline"
        )
        final_image, _format, _mode = _decode_image(
            native_payload, "Texture-master native texture PNG"
        )
        preview, changed_count = _native_raster_edit_preview(
            preview,
            baseline_image,
            final_image,
            scale=high_resolution_scale,
        )
        native_raster_edit = {
            "baseline_file": NATIVE_BASELINE_MEMBER,
            "baseline_sha256": _sha256(baseline_payload),
            "changed_pixel_count": changed_count,
            "preview_resample": "nearest",
        }
        preview_composition = "direct-master-plus-native-raster-edits"
    preview_payload = _encode_png(preview)
    preview_member = f"preview-{high_resolution_scale}x.png"
    source_more_detailed = (
        source_width > native_width or source_height > native_height
    )
    manifest = {
        "asset_id": asset_id,
        "capabilities": {
            "game_build_uses": NATIVE_MEMBER,
            "high_resolution_preview_is_game_replacement": False,
            "render_scale_increases_texture_resolution": False,
            "rpcs3_texture_pack_export": False,
        },
        "editor_target": editor_target,
        "editor_transform": selected_editor_transform,
        "high_resolution_preview": {
            "composition": preview_composition,
            "file": preview_member,
            "height": native_height * high_resolution_scale,
            "purpose": "authoring-preview-only",
            "rendered_directly_from_master": True,
            "scale": high_resolution_scale,
            "sha256": _sha256(preview_payload),
            "source_exceeds_native_dimensions": source_more_detailed,
            "width": native_width * high_resolution_scale,
        },
        "native": {
            "file": NATIVE_MEMBER,
            "generation": native_generation,
            "height": native_height,
            "sha256": _sha256(native_payload),
            "width": native_width,
        },
        "native_raster_edit": native_raster_edit,
        "payload_policy": "user-authored-source-and-derived-outputs-only",
        "schema": TEXTURE_MASTER_SCHEMA,
        "source": {
            "file": SOURCE_MEMBER,
            "format": source_format,
            "height": source_height,
            "mode": source_mode,
            "sha256": _sha256(source_payload),
            "size": len(source_payload),
            "width": source_width,
        },
        "transform": selected_transform.document(),
    }
    manifest_payload = _canonical_json(manifest)
    _require(len(manifest_payload) <= MAX_MANIFEST_BYTES,
             "Texture-master manifest exceeds its safety limit.")
    expanded = (
        len(source_payload) + len(native_payload) + len(preview_payload)
        + (len(baseline_payload) if baseline_payload is not None else 0)
        + len(manifest_payload)
    )
    _require(expanded <= MAX_EXPANDED_BYTES,
             "Texture-master bundle exceeds the expanded-size safety limit.")
    output = _destination(destination)
    _require(shutil.disk_usage(output.parent).free >= expanded,
             "There is not enough free space to save this texture master.")
    temporary = output.with_name(f".{output.name}.{os.getpid()}.{uuid4().hex}.tmp")
    descriptor = os.open(
        temporary,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w+b", closefd=True) as stream:
            with zipfile.ZipFile(
                stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                archive.writestr(_zip_info(MANIFEST_MEMBER), manifest_payload)
                archive.writestr(_zip_info(SOURCE_MEMBER), source_payload)
                archive.writestr(_zip_info(NATIVE_MEMBER), native_payload)
                if baseline_payload is not None:
                    archive.writestr(
                        _zip_info(NATIVE_BASELINE_MEMBER), baseline_payload
                    )
                archive.writestr(_zip_info(preview_member), preview_payload)
            stream.flush()
            os.fsync(stream.fileno())
        _require(0 < temporary.stat().st_size <= MAX_ARCHIVE_BYTES,
                 "Texture-master archive exceeds the 256 MiB safety limit.")
        try:
            os.link(temporary, output, follow_symlinks=False)
        except FileExistsError as exc:
            raise ValidationError(f"A file already exists there: {output}") from exc
        return output.resolve(strict=True)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValidationError(f"Could not save the texture master: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def _transform_from_document(value: object) -> AuthoringTransform:
    fields = {
        "center_x", "center_y", "height", "resample",
        "rotation_degrees", "width",
    }
    _require(isinstance(value, dict) and set(value) == fields,
             "Texture-master transform fields changed.")
    numeric = ("center_x", "center_y", "height", "rotation_degrees", "width")
    _require(all(type(value[field]) in {int, float} for field in numeric),
             "Texture-master transform has a nonnumeric value.")
    _require(isinstance(value["resample"], str),
             "Texture-master transform resampling is malformed.")
    return AuthoringTransform(
        center_x=float(value["center_x"]),
        center_y=float(value["center_y"]),
        width=float(value["width"]),
        height=float(value["height"]),
        rotation_degrees=float(value["rotation_degrees"]),
        resample=value["resample"],
    )


def load_texture_master_bundle(source: Path) -> TextureMasterBundle:
    """Validate every member and prove that preview/transform still agree."""

    requested, archive_payload = read_bounded_regular_file(
        Path(source), "Texture-master bundle", maximum=MAX_ARCHIVE_BYTES
    )
    _require(requested.suffix.casefold() == TEXTURE_MASTER_EXTENSION,
             f"Choose a {TEXTURE_MASTER_EXTENSION} texture master.")
    try:
        with zipfile.ZipFile(io.BytesIO(archive_payload), "r") as archive:
            infos = archive.infolist()
            _require(len(infos) in {4, 5},
                     "Texture-master archive must contain four or five files.")
            names = [info.filename for info in infos]
            _require(len(names) == len(set(names)),
                     "Texture-master archive contains duplicate files.")
            _require(all(
                not info.is_dir()
                and not (info.flag_bits & 1)
                and info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                for info in infos
            ), "Texture-master archive contains an unsupported or encrypted file.")
            _require(sum(info.file_size for info in infos) <= MAX_EXPANDED_BYTES,
                     "Texture-master archive expands beyond its safety limit.")
            by_name = {info.filename: info for info in infos}
            manifest_info = by_name.get(MANIFEST_MEMBER)
            _require(manifest_info is not None
                     and manifest_info.file_size <= MAX_MANIFEST_BYTES,
                     "Texture-master manifest is missing or too large.")
            try:
                manifest_payload = archive.read(manifest_info)
                document = json.loads(
                    manifest_payload.decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_pairs,
                )
            except (UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
                raise ValidationError(
                    f"Texture-master manifest is not valid JSON: {exc}"
                ) from exc
            top_fields = {
                "asset_id", "capabilities", "editor_target",
                "editor_transform", "high_resolution_preview", "native", "payload_policy",
                "native_raster_edit", "schema", "source", "transform",
            }
            _require(isinstance(document, dict) and set(document) == top_fields,
                     "Texture-master manifest fields changed.")
            _require(document.get("schema") == TEXTURE_MASTER_SCHEMA
                     and document.get("payload_policy")
                     == "user-authored-source-and-derived-outputs-only",
                     "Texture-master schema or payload policy is unsupported.")
            _require(isinstance(document.get("asset_id"), str)
                     and 0 < len(document["asset_id"]) <= 512,
                     "Texture-master asset ID is malformed.")
            _require(isinstance(document.get("editor_target"), str)
                     and 0 < len(document["editor_target"]) <= 128,
                     "Texture-master editor target is malformed.")
            editor_transform = document.get("editor_transform")
            _require(
                isinstance(editor_transform, dict) and bool(editor_transform)
                and len(
                    json.dumps(
                        editor_transform, sort_keys=True, allow_nan=False
                    ).encode("utf-8")
                ) <= MAX_EDITOR_TRANSFORM_BYTES,
                "Texture-master editor transform is malformed or too large.",
            )
            capabilities = document.get("capabilities")
            _require(capabilities == {
                "game_build_uses": NATIVE_MEMBER,
                "high_resolution_preview_is_game_replacement": False,
                "render_scale_increases_texture_resolution": False,
                "rpcs3_texture_pack_export": False,
            }, "Texture-master capability truth changed.")
            source_meta = document.get("source")
            source_fields = {
                "file", "format", "height", "mode", "sha256", "size", "width",
            }
            _require(isinstance(source_meta, dict) and set(source_meta) == source_fields
                     and source_meta.get("file") == SOURCE_MEMBER,
                     "Texture-master source metadata is malformed.")
            native_meta = document.get("native")
            native_fields = {"file", "generation", "height", "sha256", "width"}
            _require(isinstance(native_meta, dict) and set(native_meta) == native_fields
                     and native_meta.get("file") == NATIVE_MEMBER
                     and native_meta.get("generation") in {
                         "rendered-from-master", "supplied-game-compiled",
                     }, "Texture-master native metadata is malformed.")
            preview_meta = document.get("high_resolution_preview")
            preview_fields = {
                "composition", "file", "height", "purpose", "rendered_directly_from_master",
                "scale", "sha256", "source_exceeds_native_dimensions", "width",
            }
            _require(isinstance(preview_meta, dict)
                     and set(preview_meta) == preview_fields
                     and preview_meta.get("purpose") == "authoring-preview-only"
                     and preview_meta.get("rendered_directly_from_master") is True
                     and preview_meta.get("composition") in {
                         "direct-master",
                         "direct-master-plus-native-raster-edits",
                     }
                     and type(preview_meta.get("source_exceeds_native_dimensions")) is bool,
                     "Texture-master preview metadata is malformed.")
            scale = preview_meta.get("scale")
            width = native_meta.get("width")
            height = native_meta.get("height")
            _require(type(scale) is int and scale in HIGH_RES_SCALES
                     and type(width) is int and type(height) is int
                     and width > 0 and height > 0
                     and width * height * scale ** 2 <= MAX_IMAGE_PIXELS,
                     "Texture-master dimensions or preview scale are unsupported.")
            preview_member = f"preview-{scale}x.png"
            _require(preview_meta.get("file") == preview_member
                     and preview_meta.get("width") == width * scale
                     and preview_meta.get("height") == height * scale,
                     "Texture-master preview dimensions do not match its scale.")
            expected_names = {
                MANIFEST_MEMBER, SOURCE_MEMBER, NATIVE_MEMBER, preview_member,
            }
            native_raster_meta = document.get("native_raster_edit")
            if native_raster_meta is None:
                _require(preview_meta.get("composition") == "direct-master",
                         "Texture-master preview composition is inconsistent.")
            else:
                raster_fields = {
                    "baseline_file", "baseline_sha256",
                    "changed_pixel_count", "preview_resample",
                }
                _require(
                    isinstance(native_raster_meta, dict)
                    and set(native_raster_meta) == raster_fields
                    and native_raster_meta.get("baseline_file")
                    == NATIVE_BASELINE_MEMBER
                    and isinstance(native_raster_meta.get("baseline_sha256"), str)
                    and len(native_raster_meta["baseline_sha256"]) == 64
                    and type(native_raster_meta.get("changed_pixel_count")) is int
                    and native_raster_meta["changed_pixel_count"] >= 0
                    and native_raster_meta.get("preview_resample") == "nearest"
                    and preview_meta.get("composition")
                    == "direct-master-plus-native-raster-edits",
                    "Texture-master native raster-edit metadata is malformed.",
                )
                expected_names.add(NATIVE_BASELINE_MEMBER)
            _require(set(by_name) == expected_names,
                     "Texture-master archive contains undeclared files.")
            source_bytes = archive.read(SOURCE_MEMBER)
            native_png = archive.read(NATIVE_MEMBER)
            native_baseline_png = (
                archive.read(NATIVE_BASELINE_MEMBER)
                if NATIVE_BASELINE_MEMBER in by_name
                else None
            )
            preview_png = archive.read(preview_member)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ValidationError(f"Could not open the texture master: {exc}") from exc

    _require(len(source_bytes) == source_meta.get("size")
             and 0 < len(source_bytes) <= MAX_SOURCE_BYTES
             and _sha256(source_bytes) == source_meta.get("sha256"),
             "Texture-master source checksum or size failed.")
    _require(0 < len(native_png) <= MAX_PNG_BYTES
             and _sha256(native_png) == native_meta.get("sha256"),
             "Texture-master native PNG checksum failed.")
    _require(0 < len(preview_png) <= MAX_PNG_BYTES
             and _sha256(preview_png) == preview_meta.get("sha256"),
             "Texture-master preview PNG checksum failed.")
    source_image, source_format, source_mode = _decode_image(
        source_bytes, "Texture-master source image"
    )
    _require(source_meta.get("format") == source_format
             and source_meta.get("mode") == source_mode
             and source_meta.get("width") == source_image.width
             and source_meta.get("height") == source_image.height,
             "Texture-master source image does not match its metadata.")
    expected_source_detail = (
        source_image.width > width or source_image.height > height
    )
    _require(preview_meta.get("source_exceeds_native_dimensions")
             is expected_source_detail,
             "Texture-master source-detail declaration is incorrect.")
    native_image, native_format, native_mode = _decode_image(
        native_png, "Texture-master native PNG"
    )
    preview_image, preview_format, preview_mode = _decode_image(
        preview_png, "Texture-master preview PNG"
    )
    _require(native_format == "PNG" and native_mode == "RGBA"
             and native_image.size == (width, height),
             "Texture-master native output is not the declared RGBA PNG.")
    _require(preview_format == "PNG" and preview_mode == "RGBA"
             and preview_image.size == (width * scale, height * scale),
             "Texture-master preview is not the declared RGBA PNG.")
    transform = _transform_from_document(document.get("transform"))
    transform.validate(width, height)
    expected_preview = render_master(
        source_image, width, height, transform, scale=scale
    )
    if native_baseline_png is not None:
        _require(
            0 < len(native_baseline_png) <= MAX_PNG_BYTES
            and _sha256(native_baseline_png)
            == native_raster_meta.get("baseline_sha256"),
            "Texture-master native edit baseline checksum failed.",
        )
        baseline_image, baseline_format, baseline_mode = _decode_image(
            native_baseline_png, "Texture-master native edit baseline"
        )
        _require(
            baseline_format == "PNG"
            and baseline_mode == "RGBA"
            and baseline_image.size == (width, height),
            "Texture-master native edit baseline is not the declared RGBA PNG.",
        )
        expected_preview, changed_count = _native_raster_edit_preview(
            expected_preview,
            baseline_image,
            native_image,
            scale=scale,
        )
        _require(
            changed_count == native_raster_meta.get("changed_pixel_count"),
            "Texture-master native edit count does not match its pixels.",
        )
    _require(preview_image.tobytes() == expected_preview.tobytes(),
             "Texture-master preview does not match its source and transform.")
    if native_meta.get("generation") == "rendered-from-master":
        expected_native = render_master(source_image, width, height, transform)
        _require(native_image.tobytes() == expected_native.tobytes(),
                 "Texture-master native PNG does not match its source and transform.")
    return TextureMasterBundle(
        manifest=document,
        source_bytes=source_bytes,
        native_png=native_png,
        high_resolution_png=preview_png,
        native_baseline_png=native_baseline_png,
    )


def require_rpcs3_texture_replacement_export() -> None:
    """Fail honestly until RPCS3 support and APF PS3 texture IDs are proved."""

    raise ValidationError(
        "RPCS3 high-resolution texture-pack export is unavailable. RPCS3's "
        "official configuration exposes render-resolution scaling, not a "
        "supported custom-texture replacement contract, and this editor has "
        "no source-proved APF PS3 texture-ID/name mapping. Export the "
        ".2ktexmaster authoring bundle or the exact native game PNG instead."
    )


__all__ = [
    "AuthoringTransform",
    "HIGH_RES_SCALES",
    "RPCS3_TEXTURE_REPLACEMENT_EXPORT_SUPPORTED",
    "TEXTURE_MASTER_EXTENSION",
    "TEXTURE_MASTER_SCHEMA",
    "TextureMasterBundle",
    "fit_transform",
    "load_texture_master_bundle",
    "render_master",
    "require_rpcs3_texture_replacement_export",
    "save_texture_master_bundle",
    "snapshot_texture_master_source",
    "texture_master_source_sha256",
]
