#!/usr/bin/env python3
"""Import PNG artwork into any statically compatible NFL 2K5 pants TSET."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from nfl_outer import parse_archive
from nfl_txtr import HEADER, TxtrError, compress_vc_lz, decode_chunk, encode_rgba_png, \
    minimum_vc_lz_overlap_scratch, rebuild_compressed_chunk_fixed_span, \
    swizzle_2d, unswizzle_2d
import nfl_tset_png_import as legacy
from nfl_uniform_inventory import inventory_record, logical_name_candidates, parse_tset, \
    read_and_validate_span
from nfl_pants_tset_targets import DEFAULT_REPORT, PantsTarget, TargetError, select_target


SCHEMA = "nfl2k5_pants_tset_png_import/v3"
INVENTORY_SCHEMA = "nfl2k5_resource_chunk_inventory/v1"
BASE_WIDTH = 512
BASE_HEIGHT = 256
MIP_LEVELS = 6
MIP_DIMENSIONS = tuple(
    (BASE_WIDTH >> level, BASE_HEIGHT >> level) for level in range(MIP_LEVELS)
)
INDEX_CHAIN_BYTES = sum(width * height for width, height in MIP_DIMENSIONS)
CLEAN_PALETTE_OFFSET = INDEX_CHAIN_BYTES
PALETTE_BYTES = 1024
INTERPALETTE_GAP_OFFSET = CLEAN_PALETTE_OFFSET + PALETTE_BYTES
INTERPALETTE_GAP_BYTES = 0
MUD_PALETTE_OFFSET = INTERPALETTE_GAP_OFFSET + INTERPALETTE_GAP_BYTES
VIDEO_BYTES = MUD_PALETTE_OFFSET + PALETTE_BYTES


class ImportError(ValueError):
    """Raised when a target/template/PNG/fixed allocation fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ImportError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_rgba_png(path: Path) -> tuple[int, int, bytes, str]:
    """Read only a bounded, regular, exact 512x256 RGBA8 PNG."""

    require(path.exists() and not path.is_symlink(),
            f"PNG must be a non-symlink file: {path}")
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), f"PNG is not a regular file: {path}")
    require(info.st_size <= legacy.MAX_PNG_BYTES,
            "PNG exceeds the 32 MiB file bound")
    payload = path.read_bytes()
    width, height, rgba = legacy.decode_rgba_png(
        payload, (BASE_WIDTH, BASE_HEIGHT)
    )
    return width, height, rgba, sha256_bytes(payload)


def generate_mips(rgba: bytes, width: int, height: int) \
        -> list[legacy.MipLevel]:
    """Generate the exact six-level 512x256 pants chain."""

    require((width, height) == (BASE_WIDTH, BASE_HEIGHT) and
            len(rgba) == width * height * 4,
            "base pants RGBA dimensions/size mismatch")
    result = [legacy.MipLevel(0, width, height, rgba)]
    current = rgba
    current_width = width
    current_height = height
    for level in range(1, MIP_LEVELS):
        require(current_width % 2 == 0 and current_height % 2 == 0,
                "pants mip dimensions cannot be halved exactly")
        next_width = current_width // 2
        next_height = current_height // 2
        downsampled = bytearray(next_width * next_height * 4)
        for y in range(next_height):
            for x in range(next_width):
                sources = (
                    ((y * 2) * current_width + x * 2) * 4,
                    ((y * 2) * current_width + x * 2 + 1) * 4,
                    (((y * 2) + 1) * current_width + x * 2) * 4,
                    (((y * 2) + 1) * current_width + x * 2 + 1) * 4,
                )
                target = (y * next_width + x) * 4
                for channel in range(4):
                    total = sum(current[source + channel] for source in sources)
                    downsampled[target + channel] = (total + 2) // 4
        current = bytes(downsampled)
        current_width = next_width
        current_height = next_height
        result.append(legacy.MipLevel(
            level, current_width, current_height, current
        ))
    require(tuple((item.width, item.height) for item in result) == MIP_DIMENSIONS,
            "generated pants mip dimensions differ from pinned chain")
    return result


def decode_tset_levels(decoded: bytes) \
        -> tuple[list[legacy.MipLevel], list[legacy.MipLevel]]:
    """Decode the proved shared-index pants layout."""

    require(len(decoded) == 256 + VIDEO_BYTES, "decoded pants TSET size mismatch")
    video = decoded[256:]
    require(video[INTERPALETTE_GAP_OFFSET:
                  INTERPALETTE_GAP_OFFSET + INTERPALETTE_GAP_BYTES] ==
            bytes(INTERPALETTE_GAP_BYTES),
            "pants inter-palette gap is not the proved zero block")
    clean_palette = legacy.parse_palette(video, CLEAN_PALETTE_OFFSET)
    mud_palette = legacy.parse_palette(video, MUD_PALETTE_OFFSET)
    clean: list[legacy.MipLevel] = []
    mud: list[legacy.MipLevel] = []
    offset = 0
    for level, (level_width, level_height) in enumerate(MIP_DIMENSIONS):
        size = level_width * level_height
        swizzled = video[offset:offset + size]
        require(len(swizzled) == size, f"pants mip {level} is truncated")
        indices = unswizzle_2d(swizzled, level_width, level_height, 1)
        clean.append(legacy.MipLevel(
            level, level_width, level_height,
            legacy.rgba_from_indices(indices, clean_palette),
        ))
        mud.append(legacy.MipLevel(
            level, level_width, level_height,
            legacy.rgba_from_indices(indices, mud_palette),
        ))
        offset += size
    require(offset == CLEAN_PALETTE_OFFSET,
            "pants mip chain does not end at clean palette")
    return clean, mud


def target_record(inventory_value: dict[str, object], target: PantsTarget) \
        -> tuple[dict[str, object], object]:
    require(inventory_value.get("schema") == INVENTORY_SCHEMA,
            "chunk inventory schema mismatch")
    rows = [
        row for row in inventory_value["chunks"]
        if int(row["outer_index"]) == target.outer_index and
        int(row["chunk_index"]) == target.chunk_index
    ]
    require(len(rows) == 1, "selected target inventory row absent or ambiguous")
    item = rows[0]
    record = inventory_record(item)
    require(record.outer_index == target.outer_index and
            int(record.outer_id, 0) == target.outer_id and
            record.outer_size == target.outer_size and
            record.chunk_index == target.chunk_index and
            record.chunk_offset == target.chunk_offset and
            record.kind == "TSET" and
            record.stored_size == target.stored_size and
            record.word_08 == target.system_bytes and
            record.word_0c == target.video_bytes and
            record.word_10 == target.compression_magic and
            record.word_14 == target.overlap_scratch_bytes,
            "selected target inventory/wrapper fields differ from compatibility report")
    return item, record


def import_png(index: Path, inventory_path: Path, compatibility_path: Path,
               target: PantsTarget, clean_png: Path, mud_png: Path | None,
               mud_mode: str) \
        -> tuple[bytes, list[tuple[str, bytes]], dict[str, object]]:
    require(INDEX_CHAIN_BYTES == 174720 and CLEAN_PALETTE_OFFSET == 174720 and
            INTERPALETTE_GAP_OFFSET == 175744 and MUD_PALETTE_OFFSET == 175744 and
            VIDEO_BYTES == 176768,
            "shared P8 mip/palette arithmetic mismatch")
    compatibility_resolved, _, compatibility_payload, selected = select_target(
        target.asset_code, target.side, target.variant, compatibility_path
    )
    require(selected == target, "selected compatibility target changed")
    inventory_value = json.loads(inventory_path.read_bytes())
    item, record = target_record(inventory_value, target)

    archive = parse_archive(index)
    entry = archive.entries[target.outer_index]
    logical = logical_name_candidates().get(entry.name_id)
    require(entry.name_id == target.outer_id and entry.size == target.outer_size and
            logical is not None and logical.name == target.logical_name,
            "selected archive entry identity/logical name mismatch")
    require(any(
        segment.pack_ordinal == target.pack_ordinal and
        segment.pack_name == target.pack_name and
        segment.pack_offset <= target.pack_offset and
        target.pack_offset + target.span_size <= segment.pack_offset + segment.size
        for segment in entry.segments
    ), "selected target span does not fit its proved archive segment")
    record, template_span, template_decoded, template_info = read_and_validate_span(
        archive, item
    )
    template_stream = template_span[
        HEADER.size:HEADER.size + template_info.consumed_bytes
    ] if template_info is not None else b""
    template_exact_alias_scratch = minimum_vc_lz_overlap_scratch(
        template_stream, target.stored_size, target.decoded_size
    )
    require(HEADER.unpack_from(template_span) == target.complete_header and
            len(template_span) == target.span_size and
            len(template_decoded) == target.decoded_size and
            sha256_bytes(template_span) == target.span_sha256 and
            sha256_bytes(template_decoded) == target.decoded_sha256 and
            template_info is not None and
            template_info.consumed_bytes == target.lz_consumed_bytes and
            target.stored_size - template_info.consumed_bytes == target.lz_unused_bytes and
            template_exact_alias_scratch ==
                target.retail_exact_minimum_overlap_scratch_bytes and
            target.overlap_scratch_bytes >= template_exact_alias_scratch,
            "selected template span/decode/compression provenance mismatch")
    _, template_refs, _ = parse_tset(template_decoded, record, logical, None)
    require([ref["name"] for ref in template_refs] == ["pants00", "pants00_mud"] and
            [ref["record_offset"] for ref in template_refs] == [24, 60] and
            [ref["name_offset"] for ref in template_refs] == [84, 100] and
            [ref["descriptor_offset"] for ref in template_refs] == [124, 156] and
            [ref["root_offset"] for ref in template_refs] == [0, 0] and
            [ref["pixel_offset"] for ref in template_refs] == [0, 0] and
            [ref["palette_offset"] for ref in template_refs] == [174720, 175744] and
            all(ref["packed_format"] == "0x08960b29" and
                ref["packed_size"] == 0 and ref["descriptor_flags"] == "0x80000000" and
                ref["format_name"] == "P8" and ref["mip_levels"] == 6 and
                ref["width"] == 512 and ref["height"] == 256
                for ref in template_refs),
            "selected template descriptor layout differs from compatible class")
    template_gap = template_decoded[
        256 + INTERPALETTE_GAP_OFFSET:
        256 + INTERPALETTE_GAP_OFFSET + INTERPALETTE_GAP_BYTES
    ]
    require(template_gap == bytes(INTERPALETTE_GAP_BYTES),
            "selected template inter-palette gap differs from compatible class")

    clean_width, clean_height, clean_rgba, clean_png_sha = read_rgba_png(clean_png)
    clean_mips = generate_mips(clean_rgba, clean_width, clean_height)
    clean_palette, index_levels, quantization = legacy.quantize_levels(clean_mips)
    clean_expected = [
        legacy.MipLevel(level.level, level.width, level.height,
                        legacy.rgba_from_indices(indices, clean_palette))
        for level, indices in zip(clean_mips, index_levels)
    ]

    if mud_png is not None:
        require(mud_mode == "identity",
                "--mud-png cannot be combined with a derived non-identity mud mode")
        mud_width, mud_height, mud_rgba, mud_png_sha = read_rgba_png(mud_png)
        mud_mips = generate_mips(mud_rgba, mud_width, mud_height)
        mud_palette_full = legacy.palette_for_shared_mud(index_levels, mud_mips)
        highest_used = max(index for level in index_levels for index in level)
        mud_palette = mud_palette_full[:highest_used + 1]
        mud_expected = mud_mips
        mud_source = {
            "kind": "second_png_exact_shared_indices",
            "file_name": mud_png.name,
            "sha256": mud_png_sha,
        }
    else:
        mud_palette = legacy.derive_mud_palette(clean_palette, mud_mode)
        mud_expected = [
            legacy.MipLevel(level.level, level.width, level.height,
                            legacy.rgba_from_indices(indices, mud_palette))
            for level, indices in zip(clean_mips, index_levels)
        ]
        mud_source = {"kind": "derived_palette", "mode": mud_mode}

    index_chain = b"".join(
        swizzle_2d(indices, level.width, level.height, 1)
        for level, indices in zip(clean_mips, index_levels)
    )
    require(len(index_chain) == INDEX_CHAIN_BYTES,
            "encoded shared mip index chain size mismatch")
    rebuilt_decoded = bytearray(template_decoded)
    rebuilt_decoded[256:256 + INDEX_CHAIN_BYTES] = index_chain
    rebuilt_decoded[
        256 + CLEAN_PALETTE_OFFSET:
        256 + CLEAN_PALETTE_OFFSET + PALETTE_BYTES
    ] = legacy.palette_bytes(clean_palette)
    rebuilt_decoded[
        256 + MUD_PALETTE_OFFSET:
        256 + MUD_PALETTE_OFFSET + PALETTE_BYTES
    ] = legacy.palette_bytes(mud_palette)
    rebuilt_decoded_bytes = bytes(rebuilt_decoded)
    _, rebuilt_refs, _ = parse_tset(rebuilt_decoded_bytes, record, logical, None)
    template_descriptors = legacy.descriptor_projection(template_refs)
    rebuilt_descriptors = legacy.descriptor_projection(rebuilt_refs)
    require(rebuilt_descriptors == template_descriptors and
            rebuilt_decoded_bytes[:target.system_bytes] ==
            template_decoded[:target.system_bytes] and
            rebuilt_decoded_bytes[
                256 + INTERPALETTE_GAP_OFFSET:
                256 + INTERPALETTE_GAP_OFFSET + INTERPALETTE_GAP_BYTES
            ] == template_gap,
            "target system/descriptors/inter-palette gap changed")

    compressed, compression_info = compress_vc_lz(
        rebuilt_decoded_bytes,
        stream_tag=target.stream_tag,
        offset_bits=target.offset_bits,
        max_encoded_size=target.stored_size,
    )
    rebuilt_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        template_span, rebuilt_decoded_bytes
    )
    expected_rebuilt_header = list(target.complete_header)
    expected_rebuilt_header[5] = rebuild_info.rebuilt_overlap_scratch_bytes
    require(rebuild_info.recompressed_bytes == len(compressed) and
            rebuilt_span[HEADER.size:HEADER.size + len(compressed)] == compressed and
            rebuild_info.zero_padding_bytes == target.stored_size - len(compressed) and
            HEADER.unpack_from(rebuilt_span) == tuple(expected_rebuilt_header) and
            rebuild_info.loader_in_place_end_guard and
            rebuild_info.loader_in_place_alias_guard and
            len(rebuilt_span) == target.span_size,
            "target-specific fixed-span compressor/rebuilder disagreement")
    decoded_roundtrip, roundtrip_info = decode_chunk(rebuilt_span, record.as_chunk())
    require(roundtrip_info is not None and decoded_roundtrip == rebuilt_decoded_bytes and
            roundtrip_info.consumed_bytes == len(compressed),
            "rebuilt target span compressed decode mismatch")
    decoded_clean, decoded_mud = decode_tset_levels(decoded_roundtrip)
    require(decoded_clean == clean_expected and decoded_mud == mud_expected,
            "decoded target mip chain differs from requested input")

    previews: list[tuple[str, bytes]] = []
    preview_rows: list[dict[str, object]] = []
    for role, levels in (("clean", decoded_clean), ("mud", decoded_mud)):
        for level in levels:
            name = f"{role}_mip{level.level}_{level.width}x{level.height}.png"
            payload = encode_rgba_png(level.width, level.height, level.rgba)
            parsed = legacy.decode_rgba_png(payload, (level.width, level.height))
            require(parsed == (level.width, level.height, level.rgba),
                    f"generated target preview failed strict reparse: {name}")
            previews.append((name, payload))
            preview_rows.append({
                "role": role,
                "level": level.level,
                "width": level.width,
                "height": level.height,
                "rgba_sha256": sha256_bytes(level.rgba),
                "png_file": name,
                "png_sha256": sha256_bytes(payload),
                "strictly_reparsed": True,
            })

    report: dict[str, object] = {
        "schema": SCHEMA,
        "source_index": str(index),
        "canonical_inventory": str(inventory_path),
        "compatibility_report": {
            "path": str(compatibility_resolved),
            "sha256": sha256_bytes(compatibility_payload),
            "layout_signature_sha256": target.layout_signature_sha256,
        },
        "target": {
            "asset_code": target.asset_code,
            "side": target.side,
            "variant": target.variant,
            "selector": target.selector,
            "logical_name": target.logical_name,
            "outer_index": target.outer_index,
            "outer_id": f"0x{target.outer_id:08x}",
            "outer_size": target.outer_size,
            "chunk_index": target.chunk_index,
            "chunk_offset": target.chunk_offset,
            "stored_size": target.stored_size,
            "complete_span_size": target.span_size,
            "system_bytes": target.system_bytes,
            "video_bytes": target.video_bytes,
            "template_overlap_scratch_bytes": target.overlap_scratch_bytes,
            "template_exact_minimum_overlap_scratch_bytes":
                target.retail_exact_minimum_overlap_scratch_bytes,
            "rebuilt_overlap_scratch_bytes":
                rebuild_info.rebuilt_overlap_scratch_bytes,
            "stream_tag": target.stream_tag,
            "offset_bits": target.offset_bits,
            "template_span_sha256": target.span_sha256,
            "template_decoded_sha256": target.decoded_sha256,
            "layout_signature_sha256": target.layout_signature_sha256,
            "pack_name": target.pack_name,
            "pack_ordinal": target.pack_ordinal,
            "span_pack_offset": target.pack_offset,
            "xiso_pack_path": target.xiso_pack_path,
            "xiso_pack_sector": target.xiso_pack_sector,
            "xiso_absolute_span_offset": target.xiso_absolute_span_offset,
            "system_bytes_preserved": True,
            "descriptor_records_preserved": True,
            "interpalette_gap_preserved": True,
        },
        "input": {
            "clean": {
                "file_name": clean_png.name,
                "sha256": clean_png_sha,
                "width": clean_width,
                "height": clean_height,
                "format": "RGBA8_noninterlaced",
            },
            "mud": mud_source,
        },
        "mips": {
            "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
            "level_count": MIP_LEVELS,
            "dimensions": [list(item) for item in MIP_DIMENSIONS],
            "linear_index_bytes_by_level": [
                width * height for width, height in MIP_DIMENSIONS
            ],
            "total_index_chain_bytes": len(index_chain),
            "each_level_swizzled_independently": True,
        },
        "quantization": {
            "algorithm": "weighted_median_cut_rgba_then_nearest_rgba_squared_error",
            "tie_breaks": "channel R,G,B,A; stable lexical colors; lowest palette index",
            **quantization,
            "clean_palette_entries": len(clean_palette),
            "mud_palette_entries": len(mud_palette),
            "shared_index_chain": True,
        },
        "layout": {
            "index_offset": 0,
            "clean_palette_offset": CLEAN_PALETTE_OFFSET,
            "interpalette_gap_offset": INTERPALETTE_GAP_OFFSET,
            "interpalette_gap_bytes": INTERPALETTE_GAP_BYTES,
            "interpalette_gap_zero_and_preserved": True,
            "mud_palette_offset": MUD_PALETTE_OFFSET,
            "palette_bytes_each": PALETTE_BYTES,
            "video_bytes": VIDEO_BYTES,
            "unused_palette_entries_zero_filled": True,
        },
        "compression": asdict(compression_info),
        "rebuild": {
            **asdict(rebuild_info),
            "decoded_roundtrip_sha256": sha256_bytes(decoded_roundtrip),
            "complete_span_sha256": sha256_bytes(rebuilt_span),
            "complete_span_size": len(rebuilt_span),
            "fixed_span_fit": len(compressed) <= target.stored_size,
            "zero_padding_verified": rebuilt_span[HEADER.size + len(compressed):] ==
                bytes(target.stored_size - len(compressed)),
        },
        "previews": preview_rows,
        "claims": {
            "real_png_input_consumed": True,
            "all_clean_and_mud_mips_generated": True,
            "all_mips_swizzled_and_decoded": True,
            "all_preview_pngs_strictly_reparsed": True,
            "two_reference_shared_index_layout_preserved": True,
            "zero_interpalette_gap_preserved": True,
            "target_selected_from_pinned_634_package_compatibility_inventory": True,
            "target_wrapper_preserved_except_loader_overlap_scratch": True,
            "loader_in_place_decode_guarded": True,
            "fixed_span_only": True,
            "output_exclusively_created": True,
            "originals_modified": False,
            "xiso_created": False,
            "title_executed": False,
            "runtime_visibility_proved": False,
            "models_or_other_texture_chunks_supported": False,
            "portme": (
                "PORTME: separately audit any non-pants chunk or model layout before import."
            ),
        },
    }
    return rebuilt_span, previews, report


def run(index: Path, inventory: Path, compatibility: Path, target: PantsTarget,
        clean_png: Path, mud_png: Path | None, mud_mode: str,
        output_span: Path, output_manifest: Path, preview_dir: Path) \
        -> dict[str, object]:
    output_span = output_span.parent.resolve(strict=True) / output_span.name
    output_manifest = output_manifest.parent.resolve(strict=True) / output_manifest.name
    preview_dir = preview_dir.parent.resolve(strict=True) / preview_dir.name
    require(len({output_span, output_manifest, preview_dir}) == 3 and
            not output_span.exists() and not output_manifest.exists() and
            not preview_dir.exists(),
            "output span, manifest, or preview directory already exists/collides")
    rebuilt_span, previews, report = import_png(
        index, inventory, compatibility, target, clean_png, mud_png, mud_mode
    )
    created_files: list[tuple[Path, tuple[int, int]]] = []
    preview_identity: tuple[int, int] | None = None
    success = False
    try:
        os.mkdir(preview_dir, 0o755)
        info = preview_dir.stat(follow_symlinks=False)
        preview_identity = (info.st_dev, info.st_ino)
        for name, payload in previews:
            path = preview_dir / name
            identity = legacy.exclusive_write(path, payload)
            created_files.append((path, identity))
        span_identity = legacy.exclusive_write(output_span, rebuilt_span)
        created_files.append((output_span, span_identity))
        report["outputs"] = {
            "span_file": output_span.name,
            "manifest_file": output_manifest.name,
            "preview_directory": preview_dir.name,
            "preview_file_count": len(previews),
        }
        manifest_payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        manifest_identity = legacy.exclusive_write(output_manifest, manifest_payload)
        created_files.append((output_manifest, manifest_identity))
        written_span = output_span.read_bytes()
        expected_written_header = list(target.complete_header)
        expected_written_header[5] = report["rebuild"][
            "rebuilt_overlap_scratch_bytes"
        ]
        require(written_span == rebuilt_span and
                HEADER.unpack_from(written_span) == tuple(expected_written_header),
                "written generalized target span readback mismatch")
        inventory_value = json.loads(inventory.read_bytes())
        _, disk_record = target_record(inventory_value, target)
        disk_decoded, disk_info = decode_chunk(written_span, disk_record.as_chunk())
        require(disk_info is not None and
                sha256_bytes(disk_decoded) == report["rebuild"]["decoded_sha256"] and
                json.loads(output_manifest.read_bytes()) == report,
                "written generalized target decode/manifest readback mismatch")
        success = True
        return report
    finally:
        if not success:
            for path, identity in reversed(created_files):
                try:
                    info = path.stat(follow_symlinks=False)
                    if (info.st_dev, info.st_ino) == identity:
                        path.unlink()
                except FileNotFoundError:
                    pass
            if preview_identity is not None:
                try:
                    info = preview_dir.stat(follow_symlinks=False)
                    if (info.st_dev, info.st_ino) == preview_identity:
                        preview_dir.rmdir()
                except FileNotFoundError:
                    pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--compatibility", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--target-code", required=True)
    parser.add_argument("--target-side", required=True)
    parser.add_argument("--target-variant", required=True, type=int)
    parser.add_argument("--clean-png", required=True, type=Path)
    parser.add_argument("--mud-png", type=Path)
    parser.add_argument("--mud-mode", choices=("identity", "darken_60"), default="identity")
    parser.add_argument("--output-span", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        *_, target = select_target(
            args.target_code, args.target_side, args.target_variant, args.compatibility
        )
        result = run(
            args.index, args.inventory, args.compatibility, target,
            args.clean_png, args.mud_png, args.mud_mode,
            args.output_span, args.manifest, args.preview_dir,
        )
    except (OSError, ValueError, json.JSONDecodeError, TxtrError, TargetError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_PANTS_TSET_PNG_IMPORT_OK "
        f"target={target.selector} outer={target.outer_index} pack={target.pack_name} "
        f"encoded={result['compression']['encoded_bytes']}/{target.stored_size} "
        f"zero_pad={result['rebuild']['zero_padding_bytes']} mips=6 previews=12 "
        "xiso=false runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
