"""Lazy PNG export and strict input checks for proved Phase 2 visuals.

Retail artwork is decoded only from the user's private source cache and is
stored only in that cache's ``originals`` directory. This module never writes
the source XISO, never places an original in a project, and accepts only exact
RGBA PNG dimensions understood by the fixed-span importers, including reviewed
package-local uniform-equipment P8 palettes.
"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

from .errors import ValidationError
from .nfl2k5_asset_io import Nfl2k5AssetIO
from .nfl2k5_extended_visual_catalog import (
    ExtendedVisualAsset,
    VisualReportPaths,
)
from .nfl2k5_source_cache import SOURCE_SHA256, SourceCache


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_create_team_field_art_png_import as field_import  # noqa: E402
import nfl_live_face_texture_png_import as face_import  # noqa: E402
import nfl_live_face_texture_targets as face_targets  # noqa: E402
from nfl_outer import parse_archive, read_entry_bytes, read_entry_range  # noqa: E402
import nfl_player_portrait_png_import as portrait_import  # noqa: E402
import nfl_player_portrait_targets as portrait_targets  # noqa: E402
import nfl_all_texture_xiso_workflow as p8_workflow  # noqa: E402
import nfl_scorebug_png_import as scorebug_import  # noqa: E402
import nfl_tset_png_import as png_codec  # noqa: E402
from nfl_txtr import (TextureInfo, decode_chunk, decode_dxt1, encode_rgba_png,  # noqa: E402
                      parse_chunks, parse_texture, texture_to_rgba)


ORIGINAL_SCHEMA = "2k5_mod_studio_extended_visual_original_png/v1"
MAX_PNG_BYTES = 32 * 1024 * 1024
OriginalDecoder = Callable[[ExtendedVisualAsset], tuple[bytes, bytes]]


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _asset_key(asset_id: str) -> str:
    return hashlib.sha256(asset_id.encode("utf-8")).hexdigest()


def _canonical_png(width: int, height: int, rgba: bytes) -> bytes:
    if len(rgba) != width * height * 4:
        raise ValidationError("Decoded artwork has the wrong pixel byte count")
    payload = encode_rgba_png(width, height, rgba)
    try:
        reparsed = png_codec.decode_rgba_png(payload, (width, height))
    except ValueError as exc:
        raise ValidationError("Exported PNG failed its strict image recheck") from exc
    if reparsed != (width, height, rgba):
        raise ValidationError("Exported PNG failed its pixel round-trip")
    return payload


def _atomic_write(path: Path, payload: bytes, *, replace: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.path.lexists(path) and not replace:
        raise ValidationError(f"A file already exists there: {path}")
    if path.is_symlink():
        raise ValidationError(f"Refusing to replace a symbolic link: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if not replace and os.path.lexists(path):
            raise ValidationError(f"A file appeared at the export destination: {path}")
        os.replace(temporary, path)
        return path
    finally:
        temporary.unlink(missing_ok=True)


class Nfl2k5ExtendedVisualIO:
    """Decode originals and validate replacements for extended visual assets."""

    def __init__(
        self,
        cache: SourceCache,
        *,
        report_paths: VisualReportPaths = VisualReportPaths(),
        original_decoder: OriginalDecoder | None = None,
    ) -> None:
        self.cache = cache
        self.report_paths = report_paths
        self._decoder = original_decoder
        self._archive: Any | None = None

    def original_path(self, asset: ExtendedVisualAsset) -> Path:
        return self.cache.originals / f"{_asset_key(asset.asset_id)}.png"

    def ensure_original(self, asset: ExtendedVisualAsset) -> Path:
        """Return a verified private original, decoding it once when absent."""

        path = self.original_path(asset)
        metadata = path.with_suffix(".json")
        stale = False
        tampered = ValidationError(
            "A private original-backup file changed outside Mod Studio. "
            "Remove the source cache and load the XISO again."
        )
        if path.is_file() and metadata.is_file() and not path.is_symlink() \
                and not metadata.is_symlink():
            try:
                record = json.loads(metadata.read_text(encoding="utf-8"))
                payload = path.read_bytes()
                recorded_dimensions = record.get("dimensions")
                if (
                    not isinstance(recorded_dimensions, list)
                    or len(recorded_dimensions) != 2
                    or any(
                        not isinstance(value, int) or isinstance(value, bool)
                        or not 0 < value <= 16_384
                        for value in recorded_dimensions
                    )
                ):
                    raise ValueError("invalid cached dimensions")
                width, height, rgba = png_codec.decode_rgba_png(
                    payload,
                    (recorded_dimensions[0], recorded_dimensions[1]),
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                raise tampered from None
            # Two different situations used to share one message. A file whose
            # own recorded hashes no longer match its bytes really was edited
            # behind our back. A file that is internally consistent but was
            # recorded against a different source XISO or an older schema is
            # just a stale cache entry -- and calling that tampering stopped
            # people exporting after they loaded a different disc.
            if (
                record.get("png_sha256") != _sha256(payload)
                or record.get("rgba_sha256") != _sha256(rgba)
                or [width, height] != recorded_dimensions
            ):
                raise tampered
            if (
                record.get("schema") == ORIGINAL_SCHEMA
                and record.get("asset_id") == asset.asset_id
                and record.get("source_sha256") == SOURCE_SHA256
                and recorded_dimensions == [asset.width, asset.height]
            ):
                return path
            stale = True
        elif os.path.lexists(path) or os.path.lexists(metadata):
            # Recover a regular half-written generated pair, but never replace
            # a link or directory hidden at either cache pathname.
            for leftover in (path, metadata):
                if os.path.lexists(leftover) and (
                    leftover.is_symlink() or not leftover.is_file()
                ):
                    raise tampered
            stale = True
        try:
            png, rgba = (
                self._decoder(asset) if self._decoder is not None
                else self._decode_original(asset)
            )
            width, height, reparsed = png_codec.decode_rgba_png(
                png, asset.dimensions
            )
        except ValidationError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValidationError(f"Could not export {asset.label}: {exc}") from exc
        if (width, height) != asset.dimensions or reparsed != rgba:
            raise ValidationError(f"Could not verify the decoded pixels for {asset.label}")
        record = {
            "asset_id": asset.asset_id,
            "dimensions": [asset.width, asset.height],
            "png_sha256": _sha256(png),
            "rgba_sha256": _sha256(rgba),
            "schema": ORIGINAL_SCHEMA,
            # All admitted XISO layouts reduce to the same independently pinned
            # source cache.  Bind its private originals to that canonical cache
            # identity, not to padding/layout bytes in the selected container.
            "source_sha256": SOURCE_SHA256,
        }
        # Do not delete an intact stale pair before the fresh decode succeeds.
        _atomic_write(path, png, replace=stale)
        _atomic_write(
            metadata,
            (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            replace=stale,
        )
        return path

    def export_original(
        self,
        asset: ExtendedVisualAsset,
        destination: Path,
        *,
        replace: bool = False,
    ) -> Path:
        original = self.ensure_original(asset)
        requested = destination.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        _atomic_write(requested, original.read_bytes(), replace=replace)
        return requested.resolve(strict=True)

    @staticmethod
    def validate_replacement(
        asset: ExtendedVisualAsset, path: Path
    ) -> tuple[bytes, bytes]:
        """Validate the exact user-facing PNG contract for one asset."""

        if not asset.editable:
            raise ValidationError(
                f"{asset.label} is preview/export-only because its texture "
                "format has no proved fixed-span importer."
            )
        requested = path.expanduser()
        try:
            supplied = requested.lstat()
        except FileNotFoundError as exc:
            raise ValidationError(f"Choose an existing PNG file for {asset.label}") from exc
        if not stat.S_ISREG(supplied.st_mode) or stat.S_ISLNK(supplied.st_mode):
            raise ValidationError("Choose a regular PNG file, not a folder or link")
        if requested.suffix.lower() != ".png":
            raise ValidationError("This asset needs a PNG file")
        if not 0 < supplied.st_size <= MAX_PNG_BYTES:
            raise ValidationError("That PNG is empty or larger than the 32 MiB input limit")
        resolved = requested.resolve(strict=True)
        payload = resolved.read_bytes()
        current = resolved.stat(follow_symlinks=False)
        if (current.st_dev, current.st_ino, current.st_size) != (
            supplied.st_dev,
            supplied.st_ino,
            supplied.st_size,
        ):
            raise ValidationError("That PNG changed while Mod Studio was reading it")
        try:
            width, height, rgba = png_codec.decode_rgba_png(
                payload, asset.dimensions
            )
        except ValueError as exc:
            raise ValidationError(
                f"{asset.label} needs a PNG that is exactly "
                f"{asset.width}×{asset.height}. Any standard PNG works -- RGB, "
                f"RGBA, greyscale, indexed, interlaced -- but the size is "
                f"fixed by the disc and cannot be scaled. {exc}"
            ) from exc
        if (width, height) != asset.dimensions:
            raise ValidationError(
                f"{asset.label} is {width}×{height}; it must stay "
                f"{asset.width}×{asset.height}."
            )
        if asset.kind == "live_face" and any(
            rgba[offset] != 255 for offset in range(3, len(rgba), 4)
        ):
            raise ValidationError(
                "Live face/head textures must be fully opaque. "
                "Set the PNG alpha channel to 255 everywhere and try again."
            )
        return payload, rgba

    @property
    def archive(self) -> Any:
        if self._archive is None:
            try:
                self._archive = parse_archive(self.cache.pack0)
            except (OSError, ValueError) as exc:
                raise ValidationError(f"Could not open the private game archive: {exc}") from exc
        return self._archive

    def _decode_original(
        self, asset: ExtendedVisualAsset
    ) -> tuple[bytes, bytes]:
        if asset.kind == "player_portrait":
            return self._decode_portrait(asset)
        if asset.kind == "live_face":
            return self._decode_face(asset)
        if asset.kind == "create_team_field_art":
            return self._decode_field_art(asset)
        if asset.kind == "scorebug_texture":
            return self._decode_scorebug(asset)
        if asset.kind == "p8_texture":
            return self._decode_p8_texture(asset)
        if asset.kind == "uniform_equipment_texture":
            return self._decode_uniform_equipment(asset)
        raise ValidationError(
            f"No safe export route exists for asset kind {asset.kind!r}; "
            "this asset is inspect-only"
        )

    def _decode_portrait(
        self, asset: ExtendedVisualAsset
    ) -> tuple[bytes, bytes]:
        if asset.portrait_id is None:
            raise ValidationError("The portrait selector is missing")
        _report, _payload, target = portrait_targets.select_target(
            asset.portrait_id, self.report_paths.portraits
        )
        entry = self.archive.entries[target.outer_index]
        span = read_entry_range(
            self.archive, entry, target.chunk_offset, target.span_size
        )
        chunk, decoded, texture = portrait_import.validate_span(span, target)
        rgba = texture_to_rgba(decoded, chunk, texture)
        if _sha256(rgba) != target.rgba_sha256:
            raise ValidationError("The selected portrait pixels differ from the catalog")
        return _canonical_png(asset.width, asset.height, rgba), rgba


    def _decode_face(self, asset: ExtendedVisualAsset) -> tuple[bytes, bytes]:
        if asset.face_id is None or asset.family is None:
            raise ValidationError("The live face selector is missing")
        _path, _report, _payload, target = face_targets.select_target(
            asset.face_id, asset.family, self.report_paths.live_faces
        )
        _index, _span, decoded, _decode_info = face_import.load_template(
            self.cache.pack0, target
        )
        rgba = decode_dxt1(decoded[128:128 + 32_768], 256, 256)
        if _sha256(rgba) != target.base_rgba_sha256:
            raise ValidationError("The selected live face pixels differ from the catalog")
        return _canonical_png(asset.width, asset.height, rgba), rgba

    def _decode_field_art(
        self, asset: ExtendedVisualAsset
    ) -> tuple[bytes, bytes]:
        if asset.logo_code is None or asset.weather is None or asset.texture is None:
            raise ValidationError("The create-team field-art selector is missing")
        _path, _payload, inventory = field_import.load_inventory(
            self.report_paths.field_art
        )
        target = field_import.select_target(
            inventory, asset.logo_code, asset.weather, asset.texture
        )
        _index, _span, decoded, _decode_info = field_import.load_template(
            self.cache.pack0, target
        )
        base = field_import.decode_levels(decoded, target)[0]
        return _canonical_png(base.width, base.height, base.rgba), base.rgba

    def _decode_p8_texture(
        self, asset: ExtendedVisualAsset
    ) -> tuple[bytes, bytes]:
        """Decode one standalone TXTR so the browser can preview and export it.

        Missing this branch is why All Textures listed 3,024 targets and then
        showed nothing when one was selected: the list comes from the catalog,
        but every preview and export goes through here, and an unknown kind
        raised straight out of the dispatch above.
        """
        if asset.texture is None:
            raise ValidationError("The standalone texture selector is missing")
        try:
            outer_index = int(asset.asset_id.split(":")[1])
        except (IndexError, ValueError) as exc:
            raise ValidationError(
                f"{asset.asset_id} is not a standalone texture selector"
            ) from exc
        try:
            target = p8_workflow.resolve_target(
                self.archive, outer_index, asset.texture
            )
        except p8_workflow.TextureWorkflowError as exc:
            raise ValidationError(str(exc)) from exc
        # parse_texture and texture_to_rgba read the decoded payload through
        # the chunk's system/video sizes and never its offset, so the resolved
        # chunk is used as-is.
        info = parse_texture(target.decoded, target.chunk)
        rgba = texture_to_rgba(target.decoded, target.chunk, info)
        return _canonical_png(target.width, target.height, rgba), rgba

    def _decode_uniform_equipment(
        self, asset: ExtendedVisualAsset
    ) -> tuple[bytes, bytes]:
        """Decode one reviewed embedded TSET reference for preview/export/edit."""

        descriptor = asset.equipment_descriptor
        if descriptor is None or asset.texture is None:
            raise ValidationError("The uniform-equipment export selector is incomplete")
        try:
            entry = self.archive.entries[descriptor.outer_index]
            package = read_entry_bytes(self.archive, entry)
            chunks = parse_chunks(package, allow_trailing=True)
            chunk = next(
                row for row in chunks
                if row.index == descriptor.chunk_index and row.kind == "TSET"
            )
            decoded, info = decode_chunk(package, chunk)
        except (IndexError, OSError, ValueError, StopIteration) as exc:
            raise ValidationError(
                f"Could not locate {asset.label} in the loaded game: {exc}"
            ) from exc
        if info is None:
            raise ValidationError(f"{asset.label} is not a compressed retail TSET")
        format_code = (descriptor.packed_format >> 8) & 0xFF
        dimensions = (descriptor.packed_format >> 4) & 0xF
        mip_levels = (descriptor.packed_format >> 16) & 0xF
        depth = 1 << ((descriptor.packed_format >> 28) & 0xF)
        texture = TextureInfo(
            name=asset.texture,
            name_offset=0,
            descriptor_offset=0,
            pixel_offset=descriptor.pixel_offset,
            palette_offset=descriptor.palette_offset,
            packed_format=descriptor.packed_format,
            packed_size=descriptor.packed_size,
            descriptor_flags=descriptor.descriptor_flags,
            dimensions=dimensions,
            format_code=format_code,
            format_name="P8" if format_code == 0x0B else f"UNKNOWN_0x{format_code:02X}",
            mip_levels=mip_levels,
            width=asset.width,
            height=asset.height,
            depth=depth,
        )
        video = decoded[chunk.system_bytes:chunk.system_bytes + chunk.video_bytes]
        base_size = asset.width * asset.height
        base = video[
            descriptor.pixel_offset:descriptor.pixel_offset + base_size
        ]
        palette = video[
            descriptor.palette_offset:descriptor.palette_offset + 1024
        ]
        if (
            len(base) != base_size
            or len(palette) != 1024
            or _sha256(base) != descriptor.base_pixel_sha256
            or _sha256(palette) != descriptor.palette_bgra_sha256
        ):
            raise ValidationError(
                f"{asset.label} no longer matches the reviewed source hashes"
            )
        try:
            rgba = texture_to_rgba(decoded, chunk, texture)
        except ValueError as exc:
            raise ValidationError(f"Could not decode {asset.label}: {exc}") from exc
        return _canonical_png(asset.width, asset.height, rgba), rgba

    def _decode_scorebug(
        self, asset: ExtendedVisualAsset
    ) -> tuple[bytes, bytes]:
        if asset.scorebug_target is None:
            raise ValidationError("The scorebug selector is missing")
        _path, _payload, audit = scorebug_import.load_audit(
            self.report_paths.scorebug
        )
        target = scorebug_import.select_target(audit, asset.scorebug_target)
        _index, _span, decoded, _decode_info, scratch = scorebug_import.read_template(
            self.cache.pack0, target
        )
        chunk = scorebug_import.chunk_for(target, scratch)
        texture = scorebug_import.validate_texture(decoded, target, scratch)
        rgba = texture_to_rgba(decoded, chunk, texture)
        expected = target.get("rgba_sha256")
        if isinstance(expected, str) and _sha256(rgba) != expected:
            raise ValidationError("The selected scorebug pixels differ from the catalog")
        return _canonical_png(asset.width, asset.height, rgba), rgba


class Nfl2k5ProductVisualIO:
    """Session-compatible router for uniform and extended visual assets."""

    # Every kind Nfl2k5ExtendedVisualIO can decode has to be listed here, or
    # the router hands it to the uniform IO instead and the author sees
    # the inspect-only no-safe-route error.  That is what happened to
    # p8_texture: the decoder existed, the routing entry did not, so the whole
    # All Textures panel could neither preview nor export an end-zone package.
    _extended_kinds = frozenset({
        "player_portrait",
        "live_face",
        "create_team_field_art",
        "scorebug_texture",
        "p8_texture",
        "uniform_equipment_texture",
    })

    def __init__(
        self,
        cache: SourceCache,
        *,
        report_paths: VisualReportPaths = VisualReportPaths(),
    ) -> None:
        self.uniforms = Nfl2k5AssetIO(cache)
        self.extended = Nfl2k5ExtendedVisualIO(cache, report_paths=report_paths)

    def _owner(self, asset: Any) -> Any:
        return self.extended if getattr(asset, "kind", None) in self._extended_kinds \
            else self.uniforms

    def original_path(self, asset: Any) -> Path:
        return self._owner(asset).original_path(asset)

    def ensure_original(self, asset: Any) -> Path:
        return self._owner(asset).ensure_original(asset)

    def export_original(
        self, asset: Any, destination: Path, *, replace: bool = False
    ) -> Path:
        return self._owner(asset).export_original(
            asset, destination, replace=replace
        )

    def validate_replacement(self, asset: Any, path: Path) -> tuple[bytes, bytes]:
        return self._owner(asset).validate_replacement(asset, path)


__all__ = [
    "MAX_PNG_BYTES",
    "Nfl2k5ExtendedVisualIO",
    "Nfl2k5ProductVisualIO",
    "ORIGINAL_SCHEMA",
]
