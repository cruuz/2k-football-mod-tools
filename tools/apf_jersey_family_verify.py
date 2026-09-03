#!/usr/bin/env python3
"""Independently verify a typed APF jersey recipe and copied 0A output.

This verifier does not import the jersey-family or uniform-mip writer. It
checks the selected catalog entry, copy span, manifest, decoded nine-level
texture, user PNG, and source identity through read-only handles. Verification
artifacts contain hashes and metrics only, never game or replacement bytes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import stat
import sys
from typing import Any, Iterable

from PIL import Image, UnidentifiedImageError

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from mod_editor.core import platform_compat  # noqa: E402

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_xenos_mip_layout as xenos_mips  # noqa: E402


RECIPE_SCHEMA = "apf2k8_jersey_color_recipe/v1"
VERIFY_SCHEMA = "apf2k8_jersey_family_verify/v1"
PATCH_SCHEMA = "apf_jersey_family_patch/v1"
CATALOG_SCHEMA = "apf_jersey_family_layout/v1"
CATALOG = WORKSPACE / "reports/assets/apf_jersey_family_layout.json"
EXPECTED_CATALOG_SHA256 = "b60783b9c47b57e9b9f545e95f5c17d3c850e263e0d7d453aa6c3be4a0f809e4"
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
MAX_RECIPE_BYTES = 64 * 1024
MAX_PNG_BYTES = 64 * 1024 * 1024


class VerifyError(ValueError):
    """Raised when any typed recipe or copied-output invariant fails."""


def require(value: bool, message: str) -> None:
    if not value:
        raise VerifyError(message)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise VerifyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class OpenIdentity:
    path: Path
    descriptor: int
    device: int
    inode: int
    size: int

    def close(self) -> None:
        os.close(self.descriptor)

    def recheck_path(self, label: str) -> None:
        current = self.path.lstat()
        require(
            stat.S_ISREG(current.st_mode)
            and not stat.S_ISLNK(current.st_mode)
            and (current.st_dev, current.st_ino, current.st_size)
            == (self.device, self.inode, self.size),
            f"{label} pathname or identity changed during verification",
        )


def open_regular(path: Path, label: str, maximum: int | None = None) -> OpenIdentity:
    requested = path.expanduser()
    try:
        supplied = requested.lstat()
    except FileNotFoundError as exc:
        raise VerifyError(f"{label} does not exist: {requested}") from exc
    require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"{label} must be a non-symlink regular file",
    )
    if maximum is not None:
        require(0 < supplied.st_size <= maximum, f"{label} size is outside its allowed range")
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
             | getattr(os, "O_BINARY", 0))
    try:
        descriptor = os.open(requested, flags)
    except OSError as exc:
        raise VerifyError(f"cannot open {label} read-only: {exc}") from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISREG(opened.st_mode)
        or (opened.st_dev, opened.st_ino, opened.st_size)
        != (supplied.st_dev, supplied.st_ino, supplied.st_size)
    ):
        os.close(descriptor)
        raise VerifyError(f"{label} changed before read-only open")
    return OpenIdentity(
        requested.resolve(strict=True), descriptor,
        opened.st_dev, opened.st_ino, opened.st_size,
    )


def read_all(identity: OpenIdentity, label: str) -> bytes:
    chunks: list[bytes] = []
    cursor = 0
    while cursor < identity.size:
        chunk = platform_compat.pread(
            identity.descriptor, min(1024 * 1024, identity.size - cursor), cursor
        )
        require(bool(chunk), f"{label} shortened during read")
        chunks.append(chunk)
        cursor += len(chunk)
    require(os.fstat(identity.descriptor).st_size == identity.size, f"{label} size changed")
    identity.recheck_path(label)
    return b"".join(chunks)


def load_recipe(path: Path, *, check_png: bool = True) -> dict[str, Any]:
    identity = open_regular(path, "APF jersey recipe", MAX_RECIPE_BYTES)
    try:
        payload = read_all(identity, "APF jersey recipe")
    finally:
        identity.close()
    try:
        value = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerifyError(f"APF jersey recipe is not valid UTF-8 JSON: {exc}") from exc
    canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    require(payload == canonical, "APF jersey recipe must use canonical sorted JSON")
    require(
        isinstance(value, dict)
        and set(value) == {"schema", "asset_index", "png"}
        and value.get("schema") == RECIPE_SCHEMA,
        "APF jersey recipe fields/schema differ from v1",
    )
    asset_index = value.get("asset_index")
    require(type(asset_index) is int and 0 <= asset_index <= 23,
            "APF jersey asset_index must be an integer in 0..23")
    png_value = value.get("png")
    require(isinstance(png_value, str) and png_value and "\0" not in png_value,
            "APF jersey recipe png must be a non-empty path string")
    png = Path(png_value).expanduser()
    if not png.is_absolute():
        png = identity.path.parent / png
    try:
        png_supplied = png.lstat()
    except FileNotFoundError as exc:
        raise VerifyError(f"APF jersey PNG does not exist: {png}") from exc
    require(stat.S_ISREG(png_supplied.st_mode) and not stat.S_ISLNK(png_supplied.st_mode),
            "APF jersey PNG path must be a non-symlink regular file")
    png = png.resolve(strict=True)
    require(png != identity.path, "recipe and PNG paths must be distinct")
    require(png.suffix.lower() == ".png", "APF jersey input must use a .png filename")
    png_report = validate_png(png) if check_png else None
    return {
        "schema": RECIPE_SCHEMA,
        "asset_index": asset_index,
        "png": png,
        "png_report": png_report,
        "recipe_path": identity.path,
        "recipe_sha256": sha256_bytes(payload),
    }


def validate_png(path: Path) -> dict[str, Any]:
    identity = open_regular(path, "APF jersey PNG", MAX_PNG_BYTES)
    try:
        payload = read_all(identity, "APF jersey PNG")
    finally:
        identity.close()
    try:
        with Image.open(io.BytesIO(payload)) as image:
            image.load()
            require(image.format == "PNG", "APF jersey input is not a decoded PNG")
            require(image.size == (1024, 1024), "APF jersey PNG must be exactly 1024x1024")
            require(image.mode == "RGBA", "APF jersey PNG must be stored as exact RGBA")
            rgba = image.tobytes()
    except (UnidentifiedImageError, OSError) as exc:
        raise VerifyError(f"cannot decode APF jersey PNG: {exc}") from exc
    return {
        "path": identity.path,
        "file_size": len(payload),
        "file_sha256": sha256_bytes(payload),
        "width": 1024,
        "height": 1024,
        "mode": "RGBA",
        "rgba": rgba,
        "rgba_sha256": sha256_bytes(rgba),
    }


def load_catalog() -> dict[str, Any]:
    payload = CATALOG.read_bytes()
    require(sha256_bytes(payload) == EXPECTED_CATALOG_SHA256,
            "APF jersey catalog hash changed")
    value = json.loads(payload)
    require(value.get("schema") == CATALOG_SCHEMA, "APF jersey catalog schema changed")
    require(value["source"]["sha256_before"] == EXPECTED_VOLUME_SHA256 and
            value["source"]["sha256_after"] == EXPECTED_VOLUME_SHA256,
            "APF jersey catalog retail 0A pin changed")
    jerseys = value.get("jerseys")
    require(isinstance(jerseys, list) and len(jerseys) == 24 and
            [row.get("asset_index") for row in jerseys] == list(range(24)),
            "APF jersey catalog target roster changed")
    return value


def hash_fd(descriptor: int, size: int) -> str:
    digest = hashlib.sha256()
    cursor = 0
    while cursor < size:
        chunk = platform_compat.pread(descriptor, min(8 * 1024 * 1024, size - cursor), cursor)
        require(bool(chunk), "file shortened during SHA-256 read")
        digest.update(chunk)
        cursor += len(chunk)
    return digest.hexdigest()


def _update_overlap(
    digest: "hashlib._Hash", chunk: bytes, chunk_start: int,
    range_start: int, range_end: int,
) -> None:
    start = max(chunk_start, range_start)
    end = min(chunk_start + len(chunk), range_end)
    if start < end:
        digest.update(chunk[start - chunk_start:end - chunk_start])


def compare_copy_outside_span(
    source_path: Path,
    output_path: Path,
    span_offset: int,
    span_size: int,
    expected_source_sha256: str,
) -> dict[str, Any]:
    """Compare a copied file through paired handles; useful on tiny test fixtures."""
    source = open_regular(source_path, "source APF 0A")
    output = open_regular(output_path, "output APF 0A")
    try:
        require(source.path != output.path, "source and output APF 0A paths must be distinct")
        require(source.size == output.size, "copied APF 0A size differs from source")
        require(0 <= span_offset <= source.size and 0 <= span_size <= source.size - span_offset,
                "selected jersey span is outside APF 0A")
        end = span_offset + span_size
        source_full = hashlib.sha256()
        output_full = hashlib.sha256()
        source_prefix = hashlib.sha256()
        output_prefix = hashlib.sha256()
        source_suffix = hashlib.sha256()
        output_suffix = hashlib.sha256()
        source_span = hashlib.sha256()
        output_span = hashlib.sha256()
        outside_equal = True
        cursor = 0
        while cursor < source.size:
            count = min(8 * 1024 * 1024, source.size - cursor)
            first = platform_compat.pread(source.descriptor, count, cursor)
            second = platform_compat.pread(output.descriptor, count, cursor)
            require(len(first) == count and len(second) == count,
                    "short paired read while verifying copied APF 0A")
            source_full.update(first)
            output_full.update(second)
            _update_overlap(source_prefix, first, cursor, 0, span_offset)
            _update_overlap(output_prefix, second, cursor, 0, span_offset)
            _update_overlap(source_span, first, cursor, span_offset, end)
            _update_overlap(output_span, second, cursor, span_offset, end)
            _update_overlap(source_suffix, first, cursor, end, source.size)
            _update_overlap(output_suffix, second, cursor, end, source.size)
            before_end = max(0, min(len(first), span_offset - cursor))
            after_start = max(0, end - cursor)
            if first[:before_end] != second[:before_end] or first[after_start:] != second[after_start:]:
                outside_equal = False
            cursor += count
        source_sha = source_full.hexdigest()
        require(source_sha == expected_source_sha256, "source APF 0A SHA-256 is not pinned retail")
        require(outside_equal, "bytes outside the selected jersey span differ")
        require(source_prefix.digest() == output_prefix.digest() and
                source_suffix.digest() == output_suffix.digest(),
                "outside-span digest comparison failed")
        source.recheck_path("source APF 0A")
        output.recheck_path("output APF 0A")
        return {
            "source_size": source.size,
            "source_sha256": source_sha,
            "output_sha256": output_full.hexdigest(),
            "span_offset": span_offset,
            "span_size": span_size,
            "source_span_sha256": source_span.hexdigest(),
            "output_span_sha256": output_span.hexdigest(),
            "prefix_length": span_offset,
            "prefix_sha256": source_prefix.hexdigest(),
            "suffix_offset": end,
            "suffix_length": source.size - end,
            "suffix_sha256": source_suffix.hexdigest(),
            "outside_span_identical": True,
            "source_identity": (source.device, source.inode, source.size),
            "output_identity": (output.device, output.inode, output.size),
        }
    finally:
        source.close()
        output.close()


def rgba_metrics(wanted: bytes, decoded: bytes) -> dict[str, Any]:
    require(len(wanted) == len(decoded), "PNG and decoded RGBA buffers differ in size")
    errors = [abs(first - second) for first, second in zip(wanted, decoded)]
    squared = sum(error * error for error in errors)
    rmse = math.sqrt(squared / len(errors)) if errors else 0.0
    return {
        "compared_components": len(errors),
        "different_components": sum(error != 0 for error in errors),
        "maximum_absolute_error": max(errors, default=0),
        "mean_absolute_error": sum(errors) / len(errors) if errors else 0.0,
        "rmse": rmse,
        "psnr_db": None if rmse == 0 else 20.0 * math.log10(255.0 / rmse),
    }


def decode_linear_bc3(linear: bytes, location: xenos_mips.MipLocation) -> bytes:
    expected = location.logical_block_count * xenos_mips.BYTES_PER_BLOCK
    require(len(linear) == expected, f"mip {location.level} BC3 length changed")
    rgba = bytearray(location.width * location.height * 4)
    for block_y in range(location.height_blocks):
        for block_x in range(location.width_blocks):
            index = block_y * location.width_blocks + block_x
            pixels = apf_inner._decode_bc3(  # type: ignore[attr-defined]
                linear[index * 16:(index + 1) * 16]
            )
            for local_y in range(4):
                for local_x in range(4):
                    x = block_x * 4 + local_x
                    y = block_y * 4 + local_y
                    if x >= location.width or y >= location.height:
                        continue
                    destination = (y * location.width + x) * 4
                    rgba[destination:destination + 4] = bytes(pixels[local_y * 4 + local_x])
    return bytes(rgba)


def wanted_levels(base_rgba: bytes, locations: Iterable[xenos_mips.MipLocation]) -> list[bytes]:
    rows = list(locations)
    require(len(rows) == 9 and rows[0].width == 1024 and rows[0].height == 1024,
            "APF jersey layout is not the proved nine-level 1024x1024 family")
    base = Image.frombytes("RGBA", (1024, 1024), base_rgba)
    return [
        base_rgba if row.level == 0 else base.resize((row.width, row.height), Image.Resampling.BOX).tobytes()
        for row in rows
    ]


def verify_decoded_levels(
    base_rgba: bytes,
    texture: bytes,
    locations: tuple[xenos_mips.MipLocation, ...],
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    levels = manifest.get("levels")
    require(isinstance(levels, list) and len(levels) == 9,
            "writer manifest does not describe nine mip levels")
    wanted = wanted_levels(base_rgba, locations)
    results: list[dict[str, Any]] = []
    mode = manifest.get("mode")
    for location, desired, row in zip(locations, wanted, levels):
        require(row.get("level") == location.level, "writer manifest mip order changed")
        linear = xenos_mips.extract_linear_bc3(texture, location)
        decoded = decode_linear_bc3(linear, location)
        linear_hash = sha256_bytes(linear)
        decoded_hash = sha256_bytes(decoded)
        desired_hash = sha256_bytes(desired)
        metrics = rgba_metrics(desired, decoded)
        if mode == "patched":
            require(row.get("linear_bc3_sha256_after") == linear_hash,
                    f"mip {location.level} BC3 hash differs from manifest")
            require(row.get("decoded_rgba_sha256_after") == decoded_hash,
                    f"mip {location.level} decoded hash differs from manifest")
            require(row.get("wanted_rgba_sha256") == desired_hash,
                    f"mip {location.level} PNG-derived hash differs from manifest")
            require(row.get("decode_back_metrics") == metrics,
                    f"mip {location.level} PNG decode-back metrics differ")
        elif mode == "no_op":
            require(row.get("linear_bc3_sha256") == linear_hash and
                    row.get("decoded_rgba_sha256") == decoded_hash,
                    f"no-op mip {location.level} differs from manifest")
            if location.level == 0:
                require(decoded == desired, "no-op output does not decode exactly to the input PNG")
        else:
            raise VerifyError("writer manifest mode is not patched/no_op")
        results.append({
            "level": location.level,
            "linear_bc3_sha256": linear_hash,
            "decoded_rgba_sha256": decoded_hash,
            "wanted_rgba_sha256": desired_hash,
            "decode_back_metrics": metrics,
        })
    return results


class BytesReader:
    """Bounds-checked entry-local reader for independent in-memory tests."""

    def __init__(self, data: bytes):
        self.data = data

    def read(self, entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        require(0 <= offset <= len(self.data) and 0 <= size <= len(self.data) - offset,
                "memory jersey entry read is out of bounds")
        return self.data[offset:offset + size]


def decode_entry_bytes(entry_bytes: bytes, row: dict[str, Any]) -> dict[str, Any]:
    """Parse/decode one fixed jersey allocation without any retail-sized copy."""
    require(len(entry_bytes) == int(row["outer_allocation"]["size"]),
            "jersey entry byte length differs from its fixed allocation")
    entry = apf_outer.Entry(
        table_index=int(row["outer_table_index"]),
        name_id=int(str(row["outer_name_id"]), 16),
        offset_blocks=0,
        size_blocks=0,
        virtual_offset=0,
        size=len(entry_bytes),
        head_hex=entry_bytes[:4].hex(),
        segments=(),
    )
    reader = BytesReader(entry_bytes)
    record = apf_inner.parse_iff(reader, entry)
    blocks = [
        apf_inner.decode_block(reader, record, block_index, 1 << 30)
        for block_index in range(record.block_count)
    ]
    require(record.file_count == 1 and record.block_count == 2,
            "output jersey IFF structure changed")
    target = record.files[0]
    require(target.name == "jersey_color" and target.type_name == "TXTR" and
            len(target.parts) == 2 and target.parts[0].block_index == 0 and
            target.parts[1].block_index == 1,
            "output jersey_color TXTR pairing changed")
    dram = blocks[0][target.parts[0].offset:target.parts[0].offset + target.parts[0].length]
    texture = blocks[1][target.parts[1].offset:target.parts[1].offset + target.parts[1].length]
    metadata = apf_inner.parse_txtr_metadata(dram)
    locations = xenos_mips.derive_layout(metadata)
    require(xenos_mips.transport_roundtrip(texture, locations) == texture,
            "output jersey Xenos transport round-trip failed")
    return {
        "entry": entry,
        "entry_bytes": entry_bytes,
        "record": record,
        "metadata": metadata,
        "texture": texture,
        "locations": locations,
    }


def decode_output_entry(output: Path, row: dict[str, Any]) -> dict[str, Any]:
    # The copied file may be named anything by the user and need not sit beside
    # retail 0B/1A/1B. The unchanged directory table was already proved by the
    # outside-span comparison, so read the catalog-selected 0A allocation
    # directly instead of asking the multi-pack parser to resolve siblings.
    identity = open_regular(output, "output APF 0A")
    try:
        offset = int(row["physical"]["pack_offset"])
        size = int(row["outer_allocation"]["size"])
        require(0 <= offset <= identity.size and size <= identity.size - offset,
                "output selected jersey span is outside copied 0A")
        entry_bytes = platform_compat.pread(identity.descriptor, size, offset)
        require(len(entry_bytes) == size, "short read of output selected jersey entry")
        identity.recheck_path("output APF 0A")
    finally:
        identity.close()
    return decode_entry_bytes(entry_bytes, row)


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    identity = open_regular(path, "APF jersey writer manifest", 16 * 1024 * 1024)
    try:
        payload = read_all(identity, "APF jersey writer manifest")
    finally:
        identity.close()
    try:
        document = json.loads(payload, object_pairs_hook=_reject_duplicate_pairs)
    except json.JSONDecodeError as exc:
        raise VerifyError(f"APF jersey writer manifest is invalid JSON: {exc}") from exc
    require(isinstance(document, dict) and document.get("schema") == PATCH_SCHEMA,
            "APF jersey writer manifest schema changed")
    return document, sha256_bytes(payload)


def validate_copy_manifest(
    document: dict[str, Any],
    recipe: dict[str, Any],
    source: Path,
    output: Path,
    row: dict[str, Any],
    copy: dict[str, Any],
) -> None:
    family = document.get("family_target", {})
    source_row = document.get("source", {})
    copied = document.get("copied_volume", {})
    require(document.get("transport_schema") == "apf_uniform_mip_patch/v1" and
            "output_entry" not in document,
            "writer manifest transport/output mode differs from the typed provider")
    require(family == {
        "asset_index": recipe["asset_index"],
        "outer_name": row["outer_name"],
        "outer_table_index": row["outer_table_index"],
        "fixed_allocation": row["outer_allocation"]["size"],
        "retail_entry_sha256": row["outer_allocation"]["sha256"],
        "retail_texture_sha256": row["inner_file"]["texture_sha256"],
        "catalog_sha256": EXPECTED_CATALOG_SHA256,
        "runtime_visibility_proved": False,
    }, "writer manifest family target differs from the selected catalog asset")
    require(Path(source_row.get("archive_index", "")).resolve(strict=True) == source.resolve(strict=True) and
            source_row.get("physical_volume") == "0A" and
            source_row.get("outer_entry_index") == row["outer_table_index"] and
            source_row.get("outer_name") == row["outer_name"] and
            source_row.get("inner_file_index") == 0 and
            source_row.get("inner_name") == "jersey_color" and
            source_row.get("entry_sha256") == row["outer_allocation"]["sha256"] and
            source_row.get("texture_sha256") == row["inner_file"]["texture_sha256"] and
            source_row.get("png_rgba_sha256") == recipe["png_report"]["rgba_sha256"],
            "writer manifest source/PNG pins differ from the selected recipe")
    require(isinstance(copied, dict), "writer manifest has no copied_volume proof")
    require(Path(copied.get("source_volume", "")).resolve(strict=True) == source.resolve(strict=True) and
            Path(copied.get("output_volume", "")).resolve(strict=True) == output.resolve(strict=True),
            "writer manifest source/output paths differ from the typed request")
    outside = copied.get("outside_replacement", {})
    expected_mode = "replaced_entry" if document.get("mode") == "patched" else "bit_exact_no_op"
    require(copied.get("mode") == expected_mode and
            copied.get("volume_size") == copy["source_size"] and
            copied.get("source_volume_sha256_before") == EXPECTED_VOLUME_SHA256 and
            copied.get("source_volume_sha256_after") == EXPECTED_VOLUME_SHA256 and
            copied.get("output_volume_sha256") == copy["output_sha256"] and
            copied.get("replacement_read_back_sha256") == copy["output_span_sha256"],
            "writer copied-volume hashes differ from independent verification")
    require(outside == {
        "prefix_length": copy["prefix_length"],
        "prefix_sha256": copy["prefix_sha256"],
        "suffix_offset": copy["suffix_offset"],
        "suffix_length": copy["suffix_length"],
        "suffix_sha256": copy["suffix_sha256"],
        "source_and_output_match": True,
    }, "writer outside-replacement proof differs from independent comparison")


def _same_identity(path: Path, identity: tuple[int, int, int], label: str) -> None:
    current = path.lstat()
    require((current.st_dev, current.st_ino, current.st_size) == identity and
            stat.S_ISREG(current.st_mode) and not stat.S_ISLNK(current.st_mode),
            f"{label} identity changed after archive decode")


def verify_build(
    recipe_path: Path,
    source: Path,
    output: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    recipe = load_recipe(recipe_path)
    catalog = load_catalog()
    row = catalog["jerseys"][recipe["asset_index"]]
    span_offset = int(row["physical"]["pack_offset"])
    span_size = int(row["outer_allocation"]["size"])
    copy = compare_copy_outside_span(
        source, output, span_offset, span_size, EXPECTED_VOLUME_SHA256
    )
    require(copy["source_span_sha256"] == row["outer_allocation"]["sha256"],
            "source selected jersey entry differs from catalog retail hash")
    manifest, manifest_sha = load_manifest(manifest_path)
    validate_copy_manifest(manifest, recipe, source, output, row, copy)
    decoded = decode_output_entry(output, row)
    require(sha256_bytes(decoded["entry_bytes"]) == copy["output_span_sha256"],
            "parsed output jersey entry differs from copied span")
    texture_hash = sha256_bytes(decoded["texture"])
    if manifest["mode"] == "patched":
        require(manifest.get("texture", {}).get("sha256_after") == texture_hash,
                "output jersey texture differs from writer manifest")
    else:
        require(texture_hash == row["inner_file"]["texture_sha256"],
                "no-op output jersey texture differs from retail")
    require(manifest.get("target", {}).get("layout") == [
        location.manifest() for location in decoded["locations"]
    ], "output Xenos layout differs from writer manifest")
    level_results = verify_decoded_levels(
        recipe["png_report"]["rgba"], decoded["texture"],
        decoded["locations"], manifest,
    )
    _same_identity(source.resolve(strict=True), copy["source_identity"], "source APF 0A")
    _same_identity(output.resolve(strict=True), copy["output_identity"], "output APF 0A")
    source_after = open_regular(source, "source APF 0A")
    try:
        source_after_sha = hash_fd(source_after.descriptor, source_after.size)
        source_after.recheck_path("source APF 0A")
    finally:
        source_after.close()
    require(source_after_sha == EXPECTED_VOLUME_SHA256,
            "source APF 0A changed during independent verification")
    return {
        "schema": VERIFY_SCHEMA,
        "scope": {
            "read_only_verifier": True,
            "emulator_launched": False,
            "retail_source_modified": False,
            "replacement_or_game_bytes_embedded": False,
        },
        "recipe": {
            "schema": RECIPE_SCHEMA,
            "sha256": recipe["recipe_sha256"],
            "asset_index": recipe["asset_index"],
            "png_file_sha256": recipe["png_report"]["file_sha256"],
            "png_rgba_sha256": recipe["png_report"]["rgba_sha256"],
            "png_dimensions": [1024, 1024],
            "png_mode": "RGBA",
        },
        "manifest": {"schema": PATCH_SCHEMA, "sha256": manifest_sha, "mode": manifest["mode"]},
        "target": {
            "outer_table_index": row["outer_table_index"],
            "outer_name": row["outer_name"],
            "span_offset": span_offset,
            "span_size": span_size,
            "source_entry_sha256": copy["source_span_sha256"],
            "output_entry_sha256": copy["output_span_sha256"],
            "output_texture_sha256": texture_hash,
        },
        "copy": {
            "source_sha256_before": copy["source_sha256"],
            "source_sha256_after": source_after_sha,
            "output_sha256": copy["output_sha256"],
            "outside_span_identical": True,
            "prefix_length": copy["prefix_length"],
            "suffix_offset": copy["suffix_offset"],
        },
        "decode_back": {
            "level_count": len(level_results),
            "levels": level_results,
            "manifest_metrics_recomputed": True,
        },
        "result": {
            "manifest_exact": True,
            "selected_outer_entry_exact": True,
            "png_decode_back_exact_to_manifest": True,
            "source_output_outside_span_identical": True,
            "source_unchanged": True,
            "runtime_visibility_proved": False,
        },
    }


def write_artifact_dir(path: Path, report: dict[str, Any]) -> Path:
    requested = path.expanduser()
    if not requested.is_absolute():
        requested = Path.cwd() / requested
    parent = requested.parent
    parent_stat = parent.lstat()
    require(stat.S_ISDIR(parent_stat.st_mode) and not stat.S_ISLNK(parent_stat.st_mode),
            "verification artifact parent must be a non-symlink directory")
    try:
        os.mkdir(requested, 0o755)
    except FileExistsError as exc:
        raise VerifyError(f"verification artifact directory already exists: {requested}") from exc
    report_path = requested / "verification.json"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            report_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_BINARY", 0),
            0o644,
        )
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        cursor = 0
        while cursor < len(payload):
            written = os.write(descriptor, payload[cursor:])
            require(written > 0, "short write while creating verification report")
            cursor += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        return report_path
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        try:
            report_path.unlink()
        except FileNotFoundError:
            pass
        try:
            requested.rmdir()
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-recipe")
    validate.add_argument("--recipe", required=True, type=Path)
    verify = commands.add_parser("verify")
    verify.add_argument("--recipe", required=True, type=Path)
    verify.add_argument("--source-0a", required=True, type=Path)
    verify.add_argument("--output-0a", required=True, type=Path)
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--artifact-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-recipe":
            recipe = load_recipe(args.recipe)
            print(json.dumps({
                "schema": RECIPE_SCHEMA,
                "recipe_valid": True,
                "asset_index": recipe["asset_index"],
                "png_dimensions": [1024, 1024],
                "png_mode": "RGBA",
                "png_file_sha256": recipe["png_report"]["file_sha256"],
                "png_rgba_sha256": recipe["png_report"]["rgba_sha256"],
            }, sort_keys=True))
            return 0
        report = verify_build(
            args.recipe, args.source_0a, args.output_0a, args.manifest
        )
        report_path = write_artifact_dir(args.artifact_dir, report)
        print(
            "APF_JERSEY_FAMILY_VERIFY_PASS "
            f"asset={report['recipe']['asset_index']} levels=9 outside_span=true "
            f"source_unchanged=true report={report_path}"
        )
        return 0
    except (
        VerifyError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        xenos_mips.MipLayoutError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
