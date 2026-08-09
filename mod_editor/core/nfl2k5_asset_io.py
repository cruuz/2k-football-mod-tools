"""Lazy NFL 2K5 uniform PNG export and strict replacement input handling."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

from .errors import ValidationError
from .nfl2k5_source_cache import SOURCE_SHA256, SourceCache


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_jersey_tset_png_import as jersey_import  # noqa: E402
import nfl_jersey_tset_targets as jersey_targets  # noqa: E402
import nfl_live_helmet_txtr_png_import as helmet_import  # noqa: E402
import nfl_live_helmet_txtr_targets as helmet_targets  # noqa: E402
import nfl_live_numbers_nameplate_png_import as live_art_import  # noqa: E402
import nfl_live_numbers_nameplate_targets as live_art_targets  # noqa: E402
import nfl_pants_tset_png_import as pants_import  # noqa: E402
import nfl_pants_tset_targets as pants_targets  # noqa: E402
import nfl_sleeve_tset_png_import as sleeve_import  # noqa: E402
import nfl_sleeve_tset_targets as sleeve_targets  # noqa: E402
import nfl_team_select_card_png_import as card_import  # noqa: E402
import nfl_team_select_card_targets as card_targets  # noqa: E402
import nfl_tset_png_import as png_codec  # noqa: E402
from nfl_outer import parse_archive, read_entry_range  # noqa: E402
from nfl_txtr import decode_chunk, encode_rgba_png, texture_to_rgba  # noqa: E402
from nfl_uniform_inventory import read_and_validate_span  # noqa: E402


ORIGINAL_SCHEMA = "2k5_mod_studio_original_png/v1"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_key(asset_id: str) -> str:
    return hashlib.sha256(asset_id.encode("utf-8")).hexdigest()


def _canonical_png(width: int, height: int, rgba: bytes) -> bytes:
    payload = encode_rgba_png(width, height, rgba)
    parsed = png_codec.decode_rgba_png(payload, (width, height))
    if parsed != (width, height, rgba):
        raise ValidationError("The exported PNG failed its image round-trip")
    return payload


def _atomic_write(path: Path, payload: bytes, *, replace: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not replace:
        raise ValidationError(f"A file already exists there: {path}")
    if path.is_symlink():
        raise ValidationError(f"Refusing to replace a symbolic link: {path}")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if not replace and path.exists():
            raise ValidationError(f"A file appeared at the export destination: {path}")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Nfl2k5AssetIO:
    """Decode originals from the private user-derived archive cache on demand."""

    def __init__(self, cache: SourceCache) -> None:
        self.cache = cache
        try:
            self.inventory = json.loads(cache.inventory.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationError(f"Could not open the private game index: {exc}") from exc
        if self.inventory.get("schema") != "nfl2k5_resource_chunk_inventory/v1":
            raise ValidationError("The private game index has an unsupported format")
        try:
            self.archive = parse_archive(cache.pack0)
        except (OSError, ValueError) as exc:
            raise ValidationError(f"Could not open the private game archive: {exc}") from exc

    def original_path(self, asset: Any) -> Path:
        return self.cache.originals / f"{_safe_key(asset.asset_id)}.png"

    def ensure_original(self, asset: Any) -> Path:
        path = self.original_path(asset)
        metadata = path.with_suffix(".json")
        tampered = ValidationError(
            "A private original-backup file changed outside Mod Studio. "
            "Remove the source cache and load the XISO again."
        )
        stale = False
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
            # Check the entry against its own record before deciding that it is
            # stale. This keeps genuine behind-the-app edits loud, but lets an
            # intact entry from an older schema or dimension catalog be decoded
            # again. Team Kit export reaches this uniform IO, not the extended
            # visual IO, which is why repairing only that router was incomplete.
            if (
                record.get("png_sha256") != sha256_bytes(payload)
                or record.get("rgba_sha256") != sha256_bytes(rgba)
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
            # A stopped process can leave one regular half of this generated
            # pair. Recover it, but never replace a link or directory.
            for leftover in (path, metadata):
                if os.path.lexists(leftover) and (
                    leftover.is_symlink() or not leftover.is_file()
                ):
                    raise tampered
            stale = True
        png, rgba = self._decode_original(asset)
        try:
            width, height, reparsed = png_codec.decode_rgba_png(
                png, (int(asset.width), int(asset.height))
            )
        except ValueError as exc:
            raise ValidationError(
                f"Could not verify the decoded pixels for {asset.label}"
            ) from exc
        if (
            (width, height) != (asset.width, asset.height)
            or reparsed != rgba
        ):
            raise ValidationError(
                f"Could not verify the decoded pixels for {asset.label}"
            )
        record = {
            "asset_id": asset.asset_id,
            "dimensions": [asset.width, asset.height],
            "png_sha256": sha256_bytes(png),
            "rgba_sha256": sha256_bytes(rgba),
            "schema": ORIGINAL_SCHEMA,
            # All admitted XISO layouts reduce to the same independently pinned
            # source cache.  Bind its private originals to that canonical cache
            # identity, not to padding/layout bytes in the selected container.
            "source_sha256": SOURCE_SHA256,
        }
        # Keep the valid stale pair until fresh decoding succeeds. Each final
        # pathname is then replaced atomically; no pre-emptive unlink is needed.
        _atomic_write(path, png, replace=stale)
        _atomic_write(
            metadata,
            (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            replace=stale,
        )
        return path

    def export_original(self, asset: Any, destination: Path,
                        *, replace: bool = False) -> Path:
        original = self.ensure_original(asset)
        payload = original.read_bytes()
        requested = destination.expanduser()
        if not requested.is_absolute():
            requested = Path.cwd() / requested
        _atomic_write(requested, payload, replace=replace)
        return requested.resolve(strict=True)

    @staticmethod
    def validate_replacement(asset: Any, path: Path) -> tuple[bytes, bytes]:
        supplied = path.expanduser().resolve(strict=True)
        if not supplied.is_file() or supplied.is_symlink():
            raise ValidationError("Choose a regular PNG file, not a folder or link")
        if supplied.suffix.lower() != ".png":
            raise ValidationError("This asset needs a PNG file")
        if supplied.stat().st_size > 32 * 1024 * 1024:
            raise ValidationError("That PNG is larger than the 32 MiB input limit")
        payload = supplied.read_bytes()
        try:
            width, height, rgba = png_codec.decode_rgba_png(
                payload, (int(asset.width), int(asset.height)))
        except ValueError as exc:
            raise ValidationError(
                f"{asset.label} needs a PNG that is exactly "
                f"{asset.width}×{asset.height}. Any standard PNG works -- "
                "RGB, RGBA, greyscale, indexed, interlaced -- but the size "
                "is fixed by the disc and cannot be scaled. " + str(exc)
            ) from exc
        if (width, height) != (asset.width, asset.height):
            raise ValidationError(
                f"{asset.label} is {width}×{height}; it must stay "
                f"{asset.width}×{asset.height}."
            )
        return payload, rgba

    def _decode_original(self, asset: Any) -> tuple[bytes, bytes]:
        try:
            if asset.kind in {"torso", "sleeve", "pants"}:
                return self._decode_tset(asset)
            if asset.kind == "live_helmet":
                return self._decode_helmet(asset)
            if asset.kind == "live_number_nameplate":
                return self._decode_live_art(asset)
            if asset.kind == "team_select":
                return self._decode_card(asset)
        except ValidationError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValidationError(f"Could not export {asset.label}: {exc}") from exc
        raise ValidationError(
            f"No safe export route exists for asset kind {asset.kind!r}; "
            "this asset is inspect-only"
        )

    def _decode_tset(self, asset: Any) -> tuple[bytes, bytes]:
        modules = {
            "torso": (
                jersey_targets, jersey_import,
                jersey_import.legacy.decode_tset_levels,
            ),
            "sleeve": (sleeve_targets, sleeve_import, sleeve_import.decode_tset_levels),
            "pants": (pants_targets, pants_import, pants_import.decode_tset_levels),
        }
        target_module, import_module, decoder = modules[asset.kind]
        _, _, _, target = target_module.select_target(
            asset.asset_code, asset.side_code, asset.variant)
        item, _ = import_module.target_record(self.inventory, target)
        _, span, decoded, _ = read_and_validate_span(self.archive, item)
        if sha256_bytes(span) != target.span_sha256 or \
                sha256_bytes(decoded) != target.decoded_sha256:
            raise ValidationError("The selected uniform texture no longer matches the index")
        clean, _mud = decoder(decoded)
        base = clean[0]
        rgba = base.rgba
        return _canonical_png(base.width, base.height, rgba), rgba

    def _decode_helmet(self, asset: Any) -> tuple[bytes, bytes]:
        _, _, _, target = helmet_targets.select_target(
            asset.asset_code, asset.side_code, asset.variant, asset.family)
        entry = self.archive.entries[target.outer_index]
        span = read_entry_range(
            self.archive, entry, target.chunk_offset, target.span_size)
        if sha256_bytes(span) != target.span_sha256:
            raise ValidationError("The selected helmet texture no longer matches the index")
        chunk = helmet_import.as_chunk(target)
        decoded, info = decode_chunk(span, chunk)
        if info is None or sha256_bytes(decoded) != target.decoded_sha256:
            raise ValidationError("The selected helmet texture could not be decoded")
        helmet_import.validate_texture(decoded, target)
        base = helmet_import.decode_levels(decoded)[0]
        if sha256_bytes(base.rgba) != target.rgba_sha256:
            raise ValidationError("The selected helmet pixels differ from the catalog")
        return _canonical_png(base.width, base.height, base.rgba), base.rgba

    def _decode_live_art(self, asset: Any) -> tuple[bytes, bytes]:
        _, _, target = live_art_targets.select_target(
            asset.family, asset.asset_code, asset.side_code,
            asset.variant, asset.digit)
        entry = self.archive.entries[target.outer_index]
        span = read_entry_range(
            self.archive, entry, target.chunk_offset, target.span_size)
        chunk, decoded, texture = live_art_import.validate_template(span, target)
        base = live_art_import.decode_levels(decoded, chunk, texture)[0]
        return _canonical_png(base.width, base.height, base.rgba), base.rgba

    def _decode_card(self, asset: Any) -> tuple[bytes, bytes]:
        side = "home" if asset.side_code == "H" else "away"
        _, _, target = card_targets.select_target(
            asset.family, asset.asset_code, side,
            asset.variant, asset.resolution,
            ROOT / "reports/assets/nfl2k5_team_select_card_inventory.json",
        )
        entry = self.archive.entries[target.outer_index]
        span = read_entry_range(
            self.archive, entry, target.chunk_offset, target.span_size)
        chunk, decoded, texture = card_import.validate_template(span, target)
        rgba = texture_to_rgba(decoded, chunk, texture)
        if sha256_bytes(rgba) != target.rgba_sha256:
            raise ValidationError("The selected Team Select card differs from the catalog")
        return _canonical_png(target.resolution, target.resolution, rgba), rgba


def copy_user_asset_atomic(source: Path, destination: Path) -> None:
    """Copy a user-authored replacement into private session storage."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        with source.open("rb") as reader:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(temporary, flags | getattr(os, "O_BINARY", 0), 0o600)
            with os.fdopen(descriptor, "wb", closefd=True) as writer:
                shutil.copyfileobj(reader, writer, 1024 * 1024)
                writer.flush()
                os.fsync(writer.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
