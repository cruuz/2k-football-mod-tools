"""Bounded package-local uniform-equipment P8 palette imports.

The uniform ``TSET`` resources in chunks 4 through 10 do not contain one
independent index image per named texture.  Every named sock, glove, shoe, and
similar variant in a chunk shares one swizzled mip/index chain and owns only an
independent 256-entry BGRA palette.  Replacing that shared chain for one name
would silently reshape every sibling.

This writer therefore projects an authored PNG onto the retail shared indices
and changes only the selected palette allocation.  Unselected palettes, the
shared indices, descriptors, names, and all other decoded bytes remain exact.
The complete TSET is recompressed into its original fixed span; deterministic
palette tiers are tried when the richest projection does not fit.  Unsupported
formats and layouts fail closed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import nfl_all_texture_xiso_workflow as p8_writer  # noqa: E402
from nfl_outer import parse_archive, read_entry_bytes  # noqa: E402
import nfl_tset_png_import as palette_tools  # noqa: E402
from nfl_txtr import (  # noqa: E402
    HEADER,
    TextureInfo,
    TxtrError,
    decode_chunk,
    encode_rgba_png,
    parse_chunks,
    rebuild_compressed_chunk_fixed_span,
    texture_to_rgba,
    unswizzle_2d,
)


CATALOG_SCHEMA = "nfl2k5_uniform_equipment_export_catalog/v1"
DEFAULT_CATALOG = (
    ROOT / "mod_editor/data/nfl2k5_uniform_equipment_export_catalog.v1.json"
)
CATALOG_SIZE = 5_851_450
CATALOG_SHA256 = "fa2c9ca9bcc267b6981735347bf6daf6243d6ab8b83fba268804c280cfd94173"
EXPECTED_TARGETS = 28_530
MAX_PNG_BYTES = 32 * 1024 * 1024
PALETTE_BYTES = 1_024
PALETTE_LIMITS = (256, 128, 64, 32, 16, 8, 4, 2)
SUPPORTED_CHUNKS = frozenset(range(4, 11))
SUPPORTED_FORMAT = 0x0B
CATALOG_COLUMNS = (
    "outer_index",
    "set_selector",
    "tset_chunk_index",
    "reference_index",
    "name",
    "width",
    "height",
    "pixel_offset",
    "palette_offset",
    "packed_format",
    "packed_size",
    "descriptor_flags",
    "base_pixel_sha256",
    "palette_bgra_sha256",
)


class UniformEquipmentWriterError(ValueError):
    """A logical selector, private source, PNG, or fixed span is unsafe."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UniformEquipmentWriterError(message)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _file_digest(path: Path) -> str:
    supplied = path.lstat()
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        f"Private extracted pack must be a regular, non-link file: {path}",
    )
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        _require(
            (opened.st_dev, opened.st_ino, opened.st_size)
            == (supplied.st_dev, supplied.st_ino, supplied.st_size),
            f"Private extracted pack changed while opening: {path}",
        )
        result = hashlib.sha256()
        while True:
            block = os.read(descriptor, 16 * 1024 * 1024)
            if not block:
                break
            result.update(block)
        current = path.stat(follow_symlinks=False)
        _require(
            (current.st_dev, current.st_ino, current.st_size)
            == (opened.st_dev, opened.st_ino, opened.st_size),
            f"Private extracted pack changed while hashing: {path}",
        )
        return result.hexdigest()
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class EquipmentTarget:
    outer_index: int
    set_selector: str
    chunk_index: int
    reference_index: int
    name: str
    width: int
    height: int
    pixel_offset: int
    palette_offset: int
    packed_format: int
    packed_size: int
    descriptor_flags: int
    base_pixel_sha256: str
    palette_bgra_sha256: str

    @property
    def asset_id(self) -> str:
        return (
            f"tset:{self.outer_index}:{self.chunk_index}:"
            f"{self.reference_index}:{self.name}"
        )

    @property
    def mip_levels(self) -> int:
        return (self.packed_format >> 16) & 0xF

    @property
    def format_code(self) -> int:
        return (self.packed_format >> 8) & 0xFF


def load_targets(
    path: Path = DEFAULT_CATALOG,
) -> tuple[dict[str, EquipmentTarget], dict[tuple[int, int], tuple[EquipmentTarget, ...]]]:
    """Read the exact retail-free catalog and expose logical/physical maps."""

    resolved = path.expanduser()
    _require(resolved.is_file() and not resolved.is_symlink(),
             f"Uniform-equipment catalog is missing: {resolved}")
    payload = resolved.read_bytes()
    _require(
        len(payload) == CATALOG_SIZE and _digest(payload) == CATALOG_SHA256,
        "Uniform-equipment catalog identity changed",
    )
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UniformEquipmentWriterError(
            f"Uniform-equipment catalog is invalid JSON: {exc}"
        ) from exc
    _require(
        document.get("schema") == CATALOG_SCHEMA
        and document.get("columns") == list(CATALOG_COLUMNS)
        and document.get("contract") == {
            "access": "preview-export-and-palette-import",
            "import_mode": "fixed-shared-index-palette",
            "import_supported": True,
            "retail_payload_bytes": False,
            "source_rows": 32_334,
            "source_tsv_sha256":
                "f8c60d618cab8326d7a215936a2e66a75d9f399c13c0087608fbc2010bcd3abd",
        },
        "Uniform-equipment catalog contract changed",
    )
    rows = document.get("rows")
    _require(isinstance(rows, list) and len(rows) == EXPECTED_TARGETS,
             "Uniform-equipment catalog row count changed")
    by_id: dict[str, EquipmentTarget] = {}
    grouped: dict[tuple[int, int], list[EquipmentTarget]] = {}
    for number, raw in enumerate(rows, 1):
        _require(isinstance(raw, list) and len(raw) == len(CATALOG_COLUMNS),
                 f"Uniform-equipment catalog row {number} has the wrong shape")
        row = dict(zip(CATALOG_COLUMNS, raw))
        target = EquipmentTarget(
            outer_index=int(row["outer_index"]),
            set_selector=str(row["set_selector"]),
            chunk_index=int(row["tset_chunk_index"]),
            reference_index=int(row["reference_index"]),
            name=str(row["name"]),
            width=int(row["width"]),
            height=int(row["height"]),
            pixel_offset=int(row["pixel_offset"]),
            palette_offset=int(row["palette_offset"]),
            packed_format=int(row["packed_format"]),
            packed_size=int(row["packed_size"]),
            descriptor_flags=int(row["descriptor_flags"]),
            base_pixel_sha256=str(row["base_pixel_sha256"]),
            palette_bgra_sha256=str(row["palette_bgra_sha256"]),
        )
        _require(
            target.chunk_index in SUPPORTED_CHUNKS
            and target.format_code == SUPPORTED_FORMAT
            and target.packed_size == 0
            and target.pixel_offset == 0
            and target.asset_id not in by_id,
            f"Uniform-equipment row {number} is not a unique supported P8 target",
        )
        by_id[target.asset_id] = target
        grouped.setdefault((target.outer_index, target.chunk_index), []).append(target)
    return by_id, {
        key: tuple(sorted(value, key=lambda item: item.reference_index))
        for key, value in grouped.items()
    }


def _pointer(payload: bytes, field: int, limit: int, label: str) -> int:
    _require(field + 4 <= limit, f"{label} pointer field is out of bounds")
    relative = struct.unpack_from("<i", payload, field)[0]
    target = field + relative - 1
    _require(0 <= target < limit, f"{label} pointer is out of bounds")
    return target


def _utf16z(payload: bytes, start: int, limit: int, label: str) -> str:
    cursor = start
    while cursor + 2 <= limit and payload[cursor:cursor + 2] != b"\0\0":
        cursor += 2
    _require(cursor + 2 <= limit, f"{label} is not NUL terminated")
    try:
        return payload[start:cursor].decode("utf-16le")
    except UnicodeDecodeError as exc:
        raise UniformEquipmentWriterError(f"{label} is invalid UTF-16") from exc


def _texture(target: EquipmentTarget, descriptor_offset: int) -> TextureInfo:
    return TextureInfo(
        name=target.name,
        name_offset=0,
        descriptor_offset=descriptor_offset,
        pixel_offset=target.pixel_offset,
        palette_offset=target.palette_offset,
        packed_format=target.packed_format,
        packed_size=target.packed_size,
        descriptor_flags=target.descriptor_flags,
        dimensions=(target.packed_format >> 4) & 0xF,
        format_code=target.format_code,
        format_name="P8",
        mip_levels=target.mip_levels,
        width=target.width,
        height=target.height,
        depth=1 << ((target.packed_format >> 28) & 0xF),
    )


def _validate_layout(
    decoded: bytes,
    chunk: Any,
    rows: tuple[EquipmentTarget, ...],
) -> tuple[dict[int, TextureInfo], list[bytes]]:
    _require(
        len(decoded) == chunk.system_bytes + chunk.video_bytes
        and len(decoded) >= 8,
        "Uniform-equipment TSET decoded size changed",
    )
    version, count = struct.unpack_from("<II", decoded, 0)
    _require(version == 0x0D and count == len(rows),
             "Uniform-equipment TSET version/reference count changed")
    _require(
        tuple(item.reference_index for item in rows) == tuple(range(count)),
        "Uniform-equipment reference order changed",
    )
    video = decoded[chunk.system_bytes:]
    textures: dict[int, TextureInfo] = {}
    common_layout: tuple[int, int, int, int] | None = None
    for target in rows:
        base = 0x18 + target.reference_index * 0x24
        _require(decoded[base:base + 4] == b"TXTR",
                 f"{target.asset_id} embedded TXTR marker changed")
        name_offset = _pointer(
            decoded, base + 4, chunk.system_bytes, f"{target.asset_id} name"
        )
        descriptor_offset = _pointer(
            decoded, base + 8, chunk.system_bytes, f"{target.asset_id} descriptor"
        )
        name = _utf16z(
            decoded, name_offset, chunk.system_bytes, f"{target.asset_id} name"
        )
        _require(name == target.name and descriptor_offset + 24 <= chunk.system_bytes,
                 f"{target.asset_id} name/descriptor moved")
        _unknown, pixel, palette, packed_format, packed_size, flags = \
            struct.unpack_from("<6I", decoded, descriptor_offset)
        _require(
            pixel == target.pixel_offset
            and palette == target.palette_offset
            and packed_format == target.packed_format
            and packed_size == target.packed_size
            and flags == target.descriptor_flags
            and target.format_code == SUPPORTED_FORMAT,
            f"{target.asset_id} is not the reviewed swizzled P8 descriptor",
        )
        layout = (
            target.pixel_offset, target.width, target.height, target.mip_levels
        )
        _require(common_layout in {None, layout},
                 "Uniform-equipment references no longer share one index layout")
        common_layout = layout
        base_bytes = target.width * target.height
        _require(
            _digest(video[pixel:pixel + base_bytes]) == target.base_pixel_sha256
            and _digest(video[palette:palette + PALETTE_BYTES])
                == target.palette_bgra_sha256,
            f"{target.asset_id} no longer matches the reviewed source hashes",
        )
        textures[target.reference_index] = _texture(target, descriptor_offset)
    assert common_layout is not None
    pixel_offset, width, height, mip_levels = common_layout
    expected_chain = sum(
        max(1, width >> level) * max(1, height >> level)
        for level in range(mip_levels)
    )
    _require(
        pixel_offset == 0
        and expected_chain == min(item.palette_offset for item in rows)
        and all(
            item.palette_offset + PALETTE_BYTES <= len(video)
            for item in rows
        )
        and len({item.palette_offset for item in rows}) == len(rows),
        "Uniform-equipment shared index/palette allocation changed",
    )
    indices: list[bytes] = []
    cursor = pixel_offset
    for level in range(mip_levels):
        level_width = max(1, width >> level)
        level_height = max(1, height >> level)
        size = level_width * level_height
        indices.append(unswizzle_2d(
            video[cursor:cursor + size], level_width, level_height, 1
        ))
        cursor += size
    _require(cursor == expected_chain, "Uniform-equipment mip chain size changed")
    return textures, indices


def _read_png(path: Path, target: EquipmentTarget) -> tuple[bytes, bytes, list[Any]]:
    requested = path.expanduser()
    supplied = requested.lstat()
    _require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode)
        and 0 < supplied.st_size <= MAX_PNG_BYTES,
        f"{target.asset_id} PNG must be a regular file no larger than 32 MiB",
    )
    resolved = requested.resolve(strict=True)
    payload = resolved.read_bytes()
    current = resolved.stat(follow_symlinks=False)
    _require(
        (current.st_dev, current.st_ino, current.st_size)
        == (supplied.st_dev, supplied.st_ino, supplied.st_size),
        f"{target.asset_id} PNG changed while it was read",
    )
    try:
        width, height, rgba = palette_tools.decode_rgba_png(
            payload, (target.width, target.height)
        )
        levels = p8_writer.generate_mips(
            rgba, width, height, target.mip_levels
        )
    except (ValueError, p8_writer.TextureWorkflowError) as exc:
        raise UniformEquipmentWriterError(str(exc)) from exc
    return payload, rgba, levels


def _project_palette(
    indices: list[bytes], levels: list[Any], maximum: int
) -> tuple[bytes, int]:
    totals = [[0, 0, 0, 0, 0] for _ in range(256)]
    for index_bytes, level in zip(indices, levels):
        _require(len(index_bytes) * 4 == len(level.rgba),
                 "Uniform-equipment authored mip/index size differs")
        for palette_index, offset in zip(index_bytes, range(0, len(level.rgba), 4)):
            row = totals[palette_index]
            for channel in range(4):
                row[channel] += level.rgba[offset + channel]
            row[4] += 1
    desired = {
        index: tuple(
            (row[channel] + row[4] // 2) // row[4]
            for channel in range(4)
        )
        for index, row in enumerate(totals)
        if row[4]
    }
    histogram: Counter[tuple[int, int, int, int]] = Counter()
    for index, color in desired.items():
        histogram[color] += totals[index][4]
    representatives = palette_tools.median_cut_palette(histogram, maximum)
    mapped: list[tuple[int, int, int, int]] = []
    for index in range(256):
        color = desired.get(index)
        if color is None:
            mapped.append((0, 0, 0, 0))
            continue
        mapped.append(min(
            representatives,
            key=lambda candidate: (
                sum(
                    (color[channel] - candidate[channel]) ** 2
                    for channel in range(4)
                ),
                candidate,
            ),
        ))
    return palette_tools.palette_bytes(mapped), len(representatives)


def _quality(requested: bytes, actual: bytes) -> dict[str, int]:
    _require(len(requested) == len(actual), "Equipment preview size changed")
    squared = 0
    maximum = 0
    differing = 0
    for offset in range(0, len(requested), 4):
        changed = False
        for channel in range(4):
            error = abs(requested[offset + channel] - actual[offset + channel])
            squared += error * error
            maximum = max(maximum, error)
            changed = changed or bool(error)
        differing += int(changed)
    return {
        "differing_pixel_count": differing,
        "maximum_channel_error": maximum,
        "total_pixel_count": len(requested) // 4,
        "total_squared_rgba_error": squared,
    }


def build_unified_uniform_equipment_imports(
    index: Path,
    edits: Iterable[tuple[str, Path]],
    *,
    pack_hashes: dict[str, str] | None = None,
    catalog_path: Path = DEFAULT_CATALOG,
) -> tuple[bytes, list[tuple[str, bytes]], dict[str, Any], str, dict[str, Any]]:
    """Compile logical edits sharing one TSET into one fixed physical span."""

    requested = tuple((str(asset_id), Path(path)) for asset_id, path in edits)
    _require(bool(requested), "Choose at least one uniform-equipment texture")
    by_id, groups = load_targets(catalog_path)
    selected: list[tuple[EquipmentTarget, Path]] = []
    seen: set[str] = set()
    for asset_id, path in requested:
        target = by_id.get(asset_id)
        _require(target is not None,
                 f"{asset_id} is not a reviewed uniform-equipment P8 target")
        _require(asset_id not in seen, f"Uniform-equipment edit repeats {asset_id}")
        seen.add(asset_id)
        assert target is not None
        selected.append((target, path))
    physical = {(item.outer_index, item.chunk_index) for item, _path in selected}
    _require(len(physical) == 1,
             "One uniform-equipment compile may target only one physical TSET")
    outer_index, chunk_index = next(iter(physical))
    rows = groups[(outer_index, chunk_index)]

    archive = parse_archive(Path(index))
    _require(0 <= outer_index < len(archive.entries),
             "Uniform-equipment outer selector is outside the private archive")
    entry = archive.entries[outer_index]
    _require(len(entry.segments) == 1,
             "Uniform-equipment package crosses pack extents and is read-only")
    segment = entry.segments[0]
    package = read_entry_bytes(archive, entry)
    matches = [
        chunk for chunk in parse_chunks(package, allow_trailing=True)
        if chunk.index == chunk_index and chunk.kind == "TSET"
    ]
    _require(len(matches) == 1,
             "Uniform-equipment TSET selector is absent or ambiguous")
    chunk = matches[0]
    template_span = package[chunk.offset:chunk.end_offset]
    decoded, decode_info = decode_chunk(package, chunk)
    _require(decode_info is not None, "Uniform-equipment TSET is not compressed")
    textures, indices = _validate_layout(decoded, chunk, rows)

    authored: dict[int, tuple[EquipmentTarget, bytes, bytes, list[Any]]] = {}
    input_rows: list[dict[str, Any]] = []
    for target, path in selected:
        payload, rgba, levels = _read_png(path, target)
        authored[target.reference_index] = (target, payload, rgba, levels)
        input_rows.append({
            "target": target.asset_id,
            "path": str(path.resolve(strict=True)),
            "file_name": path.name,
            "sha256": _digest(payload),
            "rgba_sha256": _digest(rgba),
            "width": target.width,
            "height": target.height,
        })

    attempts: list[dict[str, Any]] = []
    rebuilt_decoded: bytes | None = None
    rebuilt_span: bytes | None = None
    rebuild_info: Any | None = None
    selected_entries: dict[int, int] = {}
    tried: set[tuple[int, ...]] = set()
    for maximum in PALETTE_LIMITS:
        candidate = bytearray(decoded)
        entries: dict[int, int] = {}
        for reference, (target, _payload, _rgba, levels) in authored.items():
            palette, actual_entries = _project_palette(indices, levels, maximum)
            entries[reference] = actual_entries
            start = chunk.system_bytes + target.palette_offset
            candidate[start:start + PALETTE_BYTES] = palette
        signature = tuple(entries[reference] for reference in sorted(entries))
        if signature in tried:
            continue
        tried.add(signature)
        try:
            span, info = rebuild_compressed_chunk_fixed_span(
                template_span, bytes(candidate)
            )
        except TxtrError as exc:
            message = str(exc)
            if not (
                message.startswith("VC-LZ stream needs more than the ")
                or (message.startswith("VC-LZ stream is ") and " exceeds " in message)
            ):
                raise UniformEquipmentWriterError(message) from exc
            attempts.append({
                "maximum_palette_entries": maximum,
                "palette_entries": entries,
                "result": "vc_lz_overflow",
            })
            continue
        rebuilt_decoded = bytes(candidate)
        rebuilt_span = span
        rebuild_info = info
        selected_entries = entries
        attempts.append({
            "encoded_bytes": info.recompressed_bytes,
            "maximum_palette_entries": maximum,
            "palette_entries": entries,
            "result": "fit",
        })
        break
    _require(
        rebuilt_decoded is not None and rebuilt_span is not None,
        f"This equipment art cannot fit a usable two-color version inside the "
        f"retail {chunk.stored_size:,}-byte TSET. Simplify the image and try again.",
    )
    assert rebuild_info is not None

    decoded_roundtrip, roundtrip_info = decode_chunk(
        rebuilt_span,
        type(chunk)(
            index=chunk.index,
            offset=0,
            kind=chunk.kind,
            stored_size=chunk.stored_size,
            system_bytes=chunk.system_bytes,
            video_bytes=chunk.video_bytes,
            compression_magic=chunk.compression_magic,
            overlap_scratch_bytes=chunk.overlap_scratch_bytes,
            reserved0=chunk.reserved0,
            reserved1=chunk.reserved1,
        ),
    )
    _require(
        roundtrip_info is not None and decoded_roundtrip == rebuilt_decoded,
        "Rebuilt uniform-equipment TSET failed independent decode",
    )

    selected_ranges = {
        (
            chunk.system_bytes + target.palette_offset,
            chunk.system_bytes + target.palette_offset + PALETTE_BYTES,
        )
        for target, _path in selected
    }
    cursor = 0
    for start, end in sorted(selected_ranges):
        _require(decoded[cursor:start] == rebuilt_decoded[cursor:start],
                 "Uniform-equipment rebuild changed bytes outside selected palettes")
        cursor = end
    _require(decoded[cursor:] == rebuilt_decoded[cursor:],
             "Uniform-equipment rebuild changed bytes outside selected palettes")

    previews: list[tuple[str, bytes]] = []
    edit_reports: list[dict[str, Any]] = []
    for target, _path in selected:
        before = texture_to_rgba(
            decoded, chunk, textures[target.reference_index]
        )
        after = texture_to_rgba(
            rebuilt_decoded, chunk, textures[target.reference_index]
        )
        authored_rgba = authored[target.reference_index][2]
        _require(before != after, f"Replacement equals retail for {target.asset_id}")
        preview_name = (
            f"equipment_{outer_index}_{chunk_index}_"
            f"{target.reference_index}_{target.name}.png"
        )
        preview = encode_rgba_png(target.width, target.height, after)
        previews.append((preview_name, preview))
        edit_reports.append({
            "asset_id": target.asset_id,
            "name": target.name,
            "palette_entries": selected_entries[target.reference_index],
            "palette_offset": target.palette_offset,
            "preview_file": preview_name,
            "preview_sha256": _digest(preview),
            "projection_quality": _quality(authored_rgba, after),
            "reference_index": target.reference_index,
            "set_selector": target.set_selector,
        })

    selected_references = set(authored)
    for target in rows:
        if target.reference_index in selected_references:
            continue
        before = texture_to_rgba(decoded, chunk, textures[target.reference_index])
        after = texture_to_rgba(
            rebuilt_decoded, chunk, textures[target.reference_index]
        )
        _require(before == after,
                 f"Editing equipment changed sibling {target.asset_id}")

    pack = archive.packs[segment.pack_ordinal]
    hashes = pack_hashes if pack_hashes is not None else {}
    if pack.name not in hashes:
        hashes[pack.name] = _file_digest(pack.path)
    span_size = len(template_span)
    pack_offset = segment.pack_offset + chunk.offset
    selector = f"uniform-equipment-tset:{outer_index}:{chunk_index}"
    target_record = {
        "chunk_index": chunk_index,
        "format": "P8 shared-index palettes",
        "outer_index": outer_index,
        "pack_offset": pack_offset,
        "selector": selector,
        "span_sha256": _digest(template_span),
        "span_size": span_size,
        "xiso_absolute_span_offset": pack_offset,
        "xiso_pack_path": f"vc_53450030/{pack.name}",
        # Layout-dependent and deliberately ignored when binding the user's
        # XISO. The absolute offset is re-derived from the located pack extent.
        "xiso_pack_sector": 0,
        "xiso_pack_sha256": hashes[pack.name],
        "xiso_pack_size": pack.size,
    }
    report = {
        "schema": "nfl2k5_uniform_equipment_texture_import/v1",
        "bounded_palette_fit": {
            "attempts": attempts,
            "selected_encoded_bytes": rebuild_info.recompressed_bytes,
            "stored_size_bound": chunk.stored_size,
        },
        "edits": edit_reports,
        "input_pngs": input_rows,
        "replacement": {
            "decoded_sha256": _digest(rebuilt_decoded),
            "span_sha256": _digest(rebuilt_span),
            "span_size": len(rebuilt_span),
            "zero_padding_bytes": rebuild_info.zero_padding_bytes,
        },
        "target": target_record,
        "claims": {
            "fixed_tset_span_only": True,
            "selected_palette_allocations_only": True,
            "shared_index_and_mip_chain_preserved": True,
            "unselected_palette_bytes_and_pixels_preserved": True,
            "system_descriptors_and_names_preserved": True,
            "runtime_visibility_proved": False,
        },
    }
    return rebuilt_span, previews, report, selector, target_record


__all__ = [
    "CATALOG_SHA256",
    "CATALOG_SIZE",
    "DEFAULT_CATALOG",
    "EquipmentTarget",
    "UniformEquipmentWriterError",
    "build_unified_uniform_equipment_imports",
    "load_targets",
]
