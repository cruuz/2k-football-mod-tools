#!/usr/bin/env python3
"""Copy-only writer for APF 2K8's 206 rectangular team wordmarks.

``uniform_textlogo_00.iff`` through ``uniform_textlogo_205.iff`` are a
selector-slot-6 family separate from the square ``uniform_logo`` helmet crest
and its frontend cache.  Every package owns one ``textlogo_color`` TXTR: tiled
Xenos DXT1/BC1 at 512x128 with a six-level packed mip chain.

This writer accepts only an exact, opaque 512x128 RGBA PNG.  The desktop editor
handles contain/cover fitting and transparency flattening before staging.  All
six mips are regenerated, inactive packed-tail bytes and the descriptor are
preserved, the H7A stream is rebuilt inside the original allocation, and the
rebuilt IFF is independently reparsed before it is returned.  The optional CLI
output is always a new copied ``0A``; the user-owned source is read-only.
"""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import stat
import struct
import sys
from typing import Mapping

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from PIL import Image, UnidentifiedImageError, __version__ as PILLOW_VERSION

import apf_inner
import apf_outer
import apf_pants_color_transport as bc1_transport
import apf_texture_patch as archive_patch
import apf_xenos_bc1_mip_layout as bc1_mips


SCHEMA = "apf2k8_textlogo_patch/v1"
CATALOG_SCHEMA = "apf2k8_textlogo_targets/v1"
CATALOG_PATH = _ROOT / "mod_editor" / "data" / "apf2k8_textlogo_targets.v1.json"
CATALOG_SHA256 = "39a1e0c944a846e24d7a11c52d6a0fbba4091959f01856d3a087efde01ba490c"
SOURCE_0A_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
CATALOG_COUNT = 206
SELECTOR_SLOT = 6
INNER_INDEX = 0
INNER_NAME = "textlogo_color"
WIDTH = 512
HEIGHT = 128
TEXTURE_LENGTH = 0x10000
BASE_LENGTH = 0x8000
MIP_LENGTH = 0x8000
DRAM_LENGTH = 0xE0
MAX_PNG_BYTES = 32 * 1024 * 1024


class TextLogoPatchError(ValueError):
    """Raised when a source, PNG, or fixed-allocation rebuild is unsafe."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_json(payload: bytes) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise TextLogoPatchError(f"text-logo catalog repeats {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(payload, object_pairs_hook=reject_duplicates)
    except TextLogoPatchError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise TextLogoPatchError(f"text-logo catalog is invalid JSON: {exc}") from exc


def load_targets() -> tuple[dict[str, object], ...]:
    """Load the retail-free, hash-pinned 0..205 package map."""

    payload = CATALOG_PATH.read_bytes()
    if _sha256(payload) != CATALOG_SHA256:
        raise TextLogoPatchError("text-logo target catalog changed")
    document = _strict_json(payload)
    if not isinstance(document, dict) or set(document) != {
        "game",
        "purpose",
        "schema",
        "selector_slot",
        "source_0a_sha256",
        "targets",
        "texture_contract",
    }:
        raise TextLogoPatchError("text-logo target catalog has unexpected fields")
    if (
        document["schema"] != CATALOG_SCHEMA
        or document["game"] != "apf2k8_xbox360_usa"
        or document["source_0a_sha256"] != SOURCE_0A_SHA256
        or document["selector_slot"] != SELECTOR_SLOT
    ):
        raise TextLogoPatchError("text-logo target catalog identity changed")
    contract = document["texture_contract"]
    if not isinstance(contract, dict) or contract != {
        "base_length": BASE_LENGTH,
        "format": "DXT1",
        "height": HEIGHT,
        "inner_name": INNER_NAME,
        "mip_length": MIP_LENGTH,
        "mip_levels": 6,
        "opaque_retail_alpha": True,
        "pitch_pixels": WIDTH,
        "width": WIDTH,
    }:
        raise TextLogoPatchError("text-logo texture contract changed")
    rows = document["targets"]
    if not isinstance(rows, list) or len(rows) != CATALOG_COUNT:
        raise TextLogoPatchError("text-logo target catalog is incomplete")
    expected_keys = {
        "asset_index",
        "inner_file",
        "outer_allocation",
        "outer_name",
        "outer_name_id",
        "outer_table_index",
    }
    seen_outer: set[int] = set()
    validated: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != expected_keys:
            raise TextLogoPatchError(f"text-logo target {index} has unexpected fields")
        if (
            row["asset_index"] != index
            or row["outer_name"] != f"uniform_textlogo_{index:02d}.iff"
            or not isinstance(row["outer_name_id"], str)
            or not str(row["outer_name_id"]).startswith("0x")
            or type(row["outer_table_index"]) is not int
            or not 0 <= int(row["outer_table_index"]) < 1543
        ):
            raise TextLogoPatchError(f"text-logo target {index} identity changed")
        allocation = row["outer_allocation"]
        inner = row["inner_file"]
        if (
            not isinstance(allocation, dict)
            or set(allocation) != {"sha256", "size"}
            or type(allocation["size"]) is not int
            or not 4096 <= int(allocation["size"]) <= 16384
            or not isinstance(allocation["sha256"], str)
            or len(str(allocation["sha256"])) != 64
            or not isinstance(inner, dict)
            or set(inner) != {"index", "name", "texture_sha256"}
            or inner["index"] != INNER_INDEX
            or inner["name"] != INNER_NAME
            or not isinstance(inner["texture_sha256"], str)
            or len(str(inner["texture_sha256"])) != 64
        ):
            raise TextLogoPatchError(f"text-logo target {index} pins changed")
        outer_index = int(row["outer_table_index"])
        if outer_index in seen_outer:
            raise TextLogoPatchError("two text-logo targets share one outer package")
        seen_outer.add(outer_index)
        validated.append(row)
    return tuple(validated)


def target_record(asset_index: int) -> dict[str, object]:
    if type(asset_index) is not int or not 0 <= asset_index < CATALOG_COUNT:
        raise TextLogoPatchError("text-logo asset index must be in 0..205")
    return load_targets()[asset_index]


def _strict_descriptor(metadata: Mapping[str, object]) -> None:
    expected = {
        "vc_file_id": "0xef64c05c",
        "vc_width": WIDTH,
        "vc_height": HEIGHT,
        "vc_base_data_length": BASE_LENGTH,
        "vc_mip_data_length": MIP_LENGTH,
        "pitch_pixels": WIDTH,
        "tiled": True,
        "format": 18,
        "endianness": 1,
        "stacked": False,
        "width": WIDTH,
        "height": HEIGHT,
        "swizzle_components": [0, 1, 2, 3],
        "mip_min_level": 0,
        "mip_max_level": 5,
        "dimension": 1,
        "packed_mips": True,
        "mip_address_pages": 8,
    }
    disagreements = {
        key: (metadata.get(key), wanted)
        for key, wanted in expected.items()
        if metadata.get(key) != wanted
    }
    if disagreements:
        raise TextLogoPatchError(
            f"uniform_textlogo descriptor left its proved class: {disagreements}"
        )


def _load_png(path: Path) -> tuple[bytes, str]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise TextLogoPatchError(f"cannot inspect text-logo PNG: {exc}") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_ISLNK(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= MAX_PNG_BYTES
    ):
        raise TextLogoPatchError(
            "text-logo PNG must be a private regular file under 32 MiB"
        )
    payload = path.read_bytes()
    try:
        after = path.lstat()
    except OSError as exc:
        raise TextLogoPatchError(f"cannot recheck text-logo PNG: {exc}") from exc
    if (
        len(payload) != info.st_size
        or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    ):
        raise TextLogoPatchError("text-logo PNG changed while being read")
    try:
        # Decode the exact bytes that were hashed and identity-checked above;
        # reopening the path would reintroduce a path-swap race.
        with Image.open(BytesIO(payload)) as image:
            image.load()
            if image.format != "PNG" or image.mode != "RGBA" or image.size != (WIDTH, HEIGHT):
                raise TextLogoPatchError(
                    "text-logo input must be an exact 512x128 RGBA PNG"
                )
            rgba = image.tobytes()
    except (UnidentifiedImageError, OSError) as exc:
        raise TextLogoPatchError(f"cannot decode text-logo PNG: {exc}") from exc
    if any(rgba[offset] != 255 for offset in range(3, len(rgba), 4)):
        raise TextLogoPatchError(
            "text-logo PNG must be opaque; the editor can flatten transparent art onto black"
        )
    return rgba, _sha256(payload)


def _read_source(
    index_path: Path, row: Mapping[str, object]
) -> tuple[
    apf_outer.Archive,
    apf_outer.Entry,
    apf_inner.IFFRecord,
    bytes,
    list[bytes],
    list[bytes],
    dict[str, object],
    bytes,
]:
    archive = apf_outer.parse_archive(index_path)
    outer_index = int(row["outer_table_index"])
    try:
        entry = archive.entries[outer_index]
    except IndexError as exc:
        raise TextLogoPatchError(f"outer archive has no entry {outer_index}") from exc
    if (
        entry.name_id != int(str(row["outer_name_id"]), 16)
        or entry.size != int(row["outer_allocation"]["size"])  # type: ignore[index]
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
    ):
        raise TextLogoPatchError("text-logo target no longer resolves to its pinned 0A range")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        decoded = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    if _sha256(original_entry) != row["outer_allocation"]["sha256"]:  # type: ignore[index]
        raise TextLogoPatchError("source text-logo package differs from its retail pin")
    if (
        record.block_count != 2
        or record.file_count != 1
        or record.warnings
        or len(decoded) != 2
        or len(stored) != 2
        or record.files[0].name != INNER_NAME
        or record.files[0].type_name != "TXTR"
    ):
        raise TextLogoPatchError("uniform_textlogo IFF structure changed")
    parts = record.files[0].parts
    if [(p.block_index, p.offset, p.length) for p in parts] != [
        (0, 0, DRAM_LENGTH),
        (1, 0, TEXTURE_LENGTH),
    ]:
        raise TextLogoPatchError("uniform_textlogo descriptor/VRAM ownership changed")
    metadata = apf_inner.parse_txtr_metadata(decoded[0][:DRAM_LENGTH])
    _strict_descriptor(metadata)
    texture = decoded[1][:TEXTURE_LENGTH]
    if _sha256(decoded[0] + texture) != row["inner_file"]["texture_sha256"]:  # type: ignore[index]
        raise TextLogoPatchError("source textlogo_color differs from its retail pin")
    return archive, entry, record, original_entry, decoded, stored, metadata, texture


def _choose_h7a(
    original_stored: bytes,
    original_decoded: bytes,
    changed_decoded: bytes,
    shift: int,
) -> tuple[bytes, dict[str, object]]:
    retail_payload = original_stored[apf_inner.H7A_HEADER_SIZE :]
    preserved, preserve_report = apf_inner.encode_h7a_preserving_tokens(
        retail_payload, original_decoded, changed_decoded, shift
    )
    candidates: list[tuple[str, bytes, dict[str, object]]] = [
        ("retail_token_preserving", preserved, dict(preserve_report))
    ]
    for limit in (256, 1024, 4096):
        encoded = archive_patch.compress_h7a(
            changed_decoded, shift, candidate_limit=limit
        )
        candidates.append(
            (
                f"greedy_candidate_limit_{limit}",
                encoded,
                {"candidate_limit": limit},
            )
        )
    mode, payload, report = min(candidates, key=lambda item: (len(item[1]), item[0]))
    if apf_inner.decompress_h7a(payload, len(changed_decoded), shift) != changed_decoded:
        raise TextLogoPatchError("text-logo H7A encode/decode round-trip failed")
    return payload, {
        "selected_mode": mode,
        "selected_payload_length": len(payload),
        "candidate_lengths": {name: len(value) for name, value, _ in candidates},
        "selected_report": report,
    }


def _rebuild_entry(
    entry: apf_outer.Entry,
    record: apf_inner.IFFRecord,
    original_entry: bytes,
    original_blocks: list[bytes],
    original_stored: list[bytes],
    new_texture: bytes,
) -> tuple[bytes, dict[str, object]]:
    if len(new_texture) != TEXTURE_LENGTH or len(original_blocks[1]) != TEXTURE_LENGTH:
        raise TextLogoPatchError("text-logo VRAM block length changed")
    descriptor = record.blocks[1]
    if not descriptor.is_compressed or descriptor.wrapper is None:
        raise TextLogoPatchError("text-logo VRAM block is not H7A-compressed")
    compressed, compression = _choose_h7a(
        original_stored[1], original_blocks[1], new_texture, descriptor.wrapper.shift
    )
    new_stored = list(original_stored)
    new_stored[1] = struct.pack(
        ">5I",
        apf_inner.H7A_MAGIC,
        TEXTURE_LENGTH,
        apf_inner.H7A_HEADER_SIZE + len(compressed),
        descriptor.unknown_10,
        descriptor.wrapper.shift,
    ) + compressed
    header = bytearray(original_entry[: record.header_size])
    body = bytearray()
    cursor = record.header_size
    blocks: list[dict[str, object]] = []
    for index, (old, stored) in enumerate(zip(record.blocks, new_stored)):
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            old.name_hash,
            old.type_hash,
            old.unknown_08,
            old.uncompressed_length,
            old.unknown_10,
            cursor,
            len(stored),
            old.indexed,
        )
        body.extend(stored)
        blocks.append(
            {
                "index": index,
                "stored_length_before": len(original_stored[index]),
                "stored_length_after": len(stored),
                "decoded_sha256_before": _sha256(original_blocks[index]),
                "decoded_sha256_after": _sha256(
                    original_blocks[index] if index == 0 else new_texture
                ),
            }
        )
        cursor += len(stored)
    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise TextLogoPatchError("uniform_textlogo IFF has no validated footer")
    footer_total = 8 + record.footer.payload_size
    footer = original_entry[record.file_length : record.file_length + footer_total]
    tail = original_entry[record.file_length + footer_total :]
    if any(tail):
        raise TextLogoPatchError("uniform_textlogo fixed-allocation tail is not zero")
    active = bytes(header) + bytes(body) + footer
    if len(active) > entry.size:
        raise TextLogoPatchError(
            "This wordmark needs "
            f"{len(active) - entry.size:,} more compressed bytes than package "
            "allocation permits. Use flatter colors, a simpler background, or "
            "less fine noise; the source and output were not changed."
        )
    rebuilt = active + bytes(entry.size - len(active))
    reader = archive_patch.BytesReader(rebuilt)
    reopened = apf_inner.parse_iff(reader, entry)
    reopened_blocks = [
        apf_inner.decode_block(reader, reopened, index, 1 << 30)
        for index in range(reopened.block_count)
    ]
    if reopened_blocks != [original_blocks[0], new_texture]:
        raise TextLogoPatchError("rebuilt text-logo IFF did not reopen as intended")
    before_parts = archive_patch._file_part_hashes(record, original_blocks)
    after_parts = archive_patch._file_part_hashes(reopened, reopened_blocks)
    changed_parts = [key for key in before_parts if before_parts[key] != after_parts[key]]
    if changed_parts != [(INNER_INDEX, 1)]:
        raise TextLogoPatchError(f"unexpected text-logo inner parts changed: {changed_parts}")
    return rebuilt, {
        "allocation_size": entry.size,
        "file_length_before": record.file_length,
        "file_length_after": new_file_length,
        "allocation_slack_after": entry.size - len(active),
        "footer_bit_exact": rebuilt[
            new_file_length : new_file_length + footer_total
        ] == footer,
        "dram_descriptor_part_bit_exact": before_parts[(0, 0)] == after_parts[(0, 0)],
        "changed_inner_parts": [
            {"file_index": 0, "part_index": 1, "block_index": 1}
        ],
        "blocks": blocks,
        "compression": compression,
        "rebuilt_iff_reparsed": True,
    }


def build_patch(
    index_path: Path, png_path: Path, asset_index: int
) -> archive_patch.PatchResult:
    """Compile one typed wordmark into its exact fixed outer package."""

    row = target_record(asset_index)
    (
        _archive,
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        metadata,
        texture,
    ) = _read_source(Path(index_path), row)
    locations = bc1_mips.derive_layout(metadata)
    if (
        len(locations) != 6
        or len(texture) != TEXTURE_LENGTH
        or bc1_mips.transport_roundtrip(texture, locations) != texture
    ):
        raise TextLogoPatchError("retail six-level wordmark BC1 transport is not exact")
    original_linear = [
        bc1_mips.extract_linear_bc1(texture, location) for location in locations
    ]
    original_rgba = [
        bc1_transport.decode_linear_bc1(linear, location)
        for linear, location in zip(original_linear, locations)
    ]
    wanted_base, png_sha = _load_png(Path(png_path))
    source = {
        "archive_index": str(index_path),
        "physical_volume": "0A",
        "outer_entry_index": int(row["outer_table_index"]),
        "outer_name": row["outer_name"],
        "inner_file_index": INNER_INDEX,
        "inner_name": INNER_NAME,
        "entry_sha256": _sha256(original_entry),
        "texture_sha256": _sha256(original_blocks[0] + texture),
        "png_sha256": png_sha,
    }
    layout = [location.manifest() for location in locations]
    if wanted_base == original_rgba[0]:
        return archive_patch.PatchResult(
            original_entry,
            {
                "schema": SCHEMA,
                "mode": "no_op",
                "source": source,
                "family_target": {
                    "asset_index": asset_index,
                    "outer_name": row["outer_name"],
                    "outer_table_index": row["outer_table_index"],
                    "fixed_allocation": row["outer_allocation"]["size"],  # type: ignore[index]
                    "selector_slot": SELECTOR_SLOT,
                    "target_catalog_sha256": CATALOG_SHA256,
                },
                "target": {"descriptor": metadata, "layout": layout},
                "validation": {
                    "input_matches_decoded_base": True,
                    "entry_bit_exact": True,
                    "all_six_levels_transport_bit_exact": True,
                    "source_opened_read_only": True,
                },
            },
        )
    wanted_levels = [wanted_base] + [
        Image.frombytes("RGBA", (WIDTH, HEIGHT), wanted_base)
        .resize((location.width, location.height), Image.Resampling.BOX)
        .tobytes()
        for location in locations[1:]
    ]
    new_texture = texture
    changed_linear: list[bytes] = []
    changed_indices: list[list[int]] = []
    encode_reports: list[dict[str, int]] = []
    for location, before, before_rgba, wanted in zip(
        locations, original_linear, original_rgba, wanted_levels
    ):
        encoded, indices, report = bc1_transport._encode_changed_blocks(
            before, before_rgba, wanted, location
        )
        new_texture = bc1_mips.insert_linear_bc1(new_texture, location, encoded)
        changed_linear.append(encoded)
        changed_indices.append(indices)
        encode_reports.append(report)
    if not changed_indices[0]:
        raise TextLogoPatchError("changed wordmark produced no changed base BC1 block")
    if bc1_mips.transport_roundtrip(new_texture, locations) != new_texture:
        raise TextLogoPatchError("patched wordmark BC1 transport is not bit-exact")
    mask = bc1_transport.active_byte_mask(len(texture), locations)
    inactive_before = bc1_transport.hash_inactive(texture, mask)
    inactive_after = bc1_transport.hash_inactive(new_texture, mask)
    if inactive_before != inactive_after:
        raise TextLogoPatchError("inactive wordmark packed-tail bytes changed")
    levels = []
    for location, before, after, wanted, indices, report in zip(
        locations,
        original_linear,
        changed_linear,
        wanted_levels,
        changed_indices,
        encode_reports,
    ):
        decoded = bc1_transport.decode_linear_bc1(after, location)
        levels.append(
            {
                "level": location.level,
                "width": location.width,
                "height": location.height,
                "packed_tail": location.packed_tail,
                "linear_bc1_sha256_before": _sha256(before),
                "linear_bc1_sha256_after": _sha256(after),
                "wanted_rgba_sha256": _sha256(wanted),
                "decoded_rgba_sha256_after": _sha256(decoded),
                "changed_dxt1_blocks": bc1_transport._indices_summary(indices),
                "encoder": report,
                "decode_back_metrics": archive_patch._rgba_metrics(wanted, decoded),
            }
        )
    rebuilt, iff = _rebuild_entry(
        entry,
        record,
        original_entry,
        original_blocks,
        original_stored,
        new_texture,
    )
    return archive_patch.PatchResult(
        rebuilt,
        {
            "schema": SCHEMA,
            "mode": "patched",
            "source": source,
            "family_target": {
                "asset_index": asset_index,
                "outer_name": row["outer_name"],
                "outer_table_index": row["outer_table_index"],
                "fixed_allocation": row["outer_allocation"]["size"],  # type: ignore[index]
                "selector_slot": SELECTOR_SLOT,
                "target_catalog_sha256": CATALOG_SHA256,
            },
            "target": {"descriptor": metadata, "layout": layout},
            "levels": levels,
            "texture": {
                "length": len(texture),
                "sha256_before": _sha256(texture),
                "sha256_after": _sha256(new_texture),
                "inactive_padding_sha256_before": inactive_before,
                "inactive_padding_sha256_after": inactive_after,
                "inactive_padding_bit_exact": True,
            },
            "iff": iff,
            "binary_patch_manifest": {
                "physical_volume": "0A",
                "physical_offset": entry.segments[0].pack_offset,
                "replacement_length": entry.size,
                "original_sha256": _sha256(original_entry),
                "replacement_sha256": _sha256(rebuilt),
                **archive_patch._changed_extents(original_entry, rebuilt),
                "contains_replacement_bytes": False,
            },
            "validation": {
                "all_six_levels_regenerated": True,
                "all_six_levels_decoded_back": True,
                "all_six_levels_transport_bit_exact": True,
                "inactive_mip_padding_preserved": True,
                "h7a_decode_encode_decode_exact": True,
                "rebuilt_iff_reparsed": True,
                "footer_bit_exact": True,
                "descriptor_part_bit_exact": True,
                "fixed_outer_allocation": True,
                "source_opened_read_only": True,
            },
            "backend": {
                "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX mip filter",
                "dxt1": "project-native deterministic opaque BC1 encoder",
                "xenos_layout": f"Xenia-derived, commit {bc1_mips.XENIA_COMMIT}",
                "h7a": "retail-token preserving plus bounded greedy fit candidates",
            },
            "runtime_boundary": (
                "Package ownership and transport are offline-proved. Runtime menu "
                "surface consumption is not claimed without a capture."
            ),
        },
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="user-owned retail APF 0A")
    parser.add_argument("--asset-index", required=True, type=int, help="wordmark index 0..205")
    parser.add_argument("--png", required=True, type=Path, help="exact opaque 512x128 RGBA PNG")
    parser.add_argument("--output-entry", type=Path, help="new rebuilt logical IFF")
    parser.add_argument("--output-volume", type=Path, help="new copied 0A")
    parser.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_path = args.manifest.expanduser()
    reservation: archive_patch.OutputReservation | None = None
    try:
        index_path = args.index.expanduser()
        png_path = args.png.expanduser()
        output_entry = args.output_entry.expanduser() if args.output_entry else None
        output_volume = args.output_volume.expanduser() if args.output_volume else None
        archive_patch._preflight_output_paths(
            [index_path, png_path],
            [
                ("manifest", manifest_path),
                ("output entry", output_entry),
                ("output volume", output_volume),
            ],
        )
        reservation = archive_patch._reserve_new(manifest_path)
        row = target_record(args.asset_index)
        result = build_patch(index_path, png_path, args.asset_index)
        document = result.manifest
        if output_entry is not None:
            archive_patch._write_new(output_entry, result.entry_bytes)
            document["output_entry"] = {
                "path": str(output_entry),
                "size": len(result.entry_bytes),
                "sha256": _sha256(result.entry_bytes),
            }
        if output_volume is not None:
            archive = apf_outer.parse_archive(index_path)
            document["copied_volume"] = archive_patch._write_copied_volume(
                index_path,
                output_volume,
                archive.entries[int(row["outer_table_index"])],
                result.entry_bytes,
            )
        archive_patch._commit_reserved(
            manifest_path,
            reservation,
            (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        archive_patch._close_reserved(reservation)
        reservation = None
        print(
            "APF_TEXTLOGO_PATCH_PASS "
            f"mode={document['mode']} asset={args.asset_index} "
            f"outer={row['outer_table_index']} sha256={_sha256(result.entry_bytes)}"
        )
    except (
        TextLogoPatchError,
        bc1_mips.MipLayoutError,
        archive_patch.PatchError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        OSError,
    ) as exc:
        if reservation is not None:
            archive_patch._abort_reserved(manifest_path, reservation)
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
