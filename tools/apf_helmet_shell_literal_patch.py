#!/usr/bin/env python3
"""Native-material writer for the APF 2K8 ``helmet_color`` shell texture.

The retail shell surface (material 1) is opaque and glossy: ``helmet_color``
is a tiled Xenos DXN/BC5 two-channel stripe mask and ``helmet_normal`` is BC5,
lit through ``SpecularLightmapSampler``.  The bounded crest lane (material 2,
4_4_4_4 palette masks) is matte by comparison, which is why full-shell crest
wraps never look retail.

This writer takes the opposite route: it keeps the retail material route,
draw routing, overlays, crest packages and menu logos untouched, and repaints
the shell *texture* literally.  ``bake_shell_atlas_literal`` bakes one literal
painted side canvas (shell body colour + authored crest art + AA fringe) into
the stock 256x1024 shell UV space, and this module stores that RGBA as tiled
Xenos DXT1/BC1 in the ``helmet_color`` slot: the DRAM descriptor is rewritten
from the proved retail DXN class to the proved BC1 class (the same descriptor
field set the ``uniform_textlogo``/``pants_color`` families carry), all seven
mip levels are regenerated, and every other byte of the package -- including
``helmet_normal`` and its descriptor -- is preserved.

The retail source is read-only; outputs are new files or a new copied volume.
Runtime visibility is not claimed here; the Xenia capture lane does that.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any, Mapping

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from PIL import Image, __version__ as PILLOW_VERSION

import apf_helmet_crest_wrap_patch as wrap
import apf_helmet_family_patch as family
import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_xenos_bc1_mip_layout as bc1_mips
import nfl_dxt1

SCHEMA = wrap.LITERAL_SCHEMA
INNER_INDEX = 0
INNER_NAME = "helmet_color"
SIBLING_NAME = "helmet_normal"
DRAM_PART_LEN = 0xE0
COLOR_VRAM_LEN = 0x60000
BC1_ACTIVE_LEN = 0x30000
BC1_FORMAT = 18
BC1_BASE_LEN = 0x20000
BC1_MIP_LEN = 0x10000
BC1_MIP_ADDRESS_PAGES = 0x20
VC_BASE_LEN_OFFSET = 0x70
VC_MIP_LEN_OFFSET = 0x74
FETCH_DWORD1_OFFSET = 0x98
FETCH_DWORD5_OFFSET = 0xA8
H7A_CANDIDATE_LIMIT = 1024
MAX_DECODED = 1 << 30

BC1_PRODUCTION_CAVEAT = (
    "The deterministic opaque BC1 encoder is the project-native proof encoder, "
    "not a production perceptual compressor; visually inspect mods before "
    "broad release."
)


class LiteralShellError(ValueError):
    """Raised when the helmet package or the literal bake is unsafe."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def strict_retail_descriptor(metadata: Mapping[str, object]) -> None:
    """Fail closed unless the descriptor is the proved retail DXN class."""

    required = {
        "vc_file_id": "0xcf7f3bdf",
        "vc_width": 256,
        "vc_height": 1024,
        "vc_base_data_length": 0x40000,
        "vc_mip_data_length": 0x20000,
        "pitch_pixels": 256,
        "tiled": True,
        "format": 49,
        "endianness": 1,
        "stacked": False,
        "width": 256,
        "height": 1024,
        "swizzle_components": [0, 1, 2, 3],
        "mip_min_level": 0,
        "mip_max_level": 6,
        "dimension": 1,
        "packed_mips": True,
        "mip_address_pages": 64,
    }
    disagreements = {
        key: (metadata.get(key), wanted)
        for key, wanted in required.items()
        if metadata.get(key) != wanted
    }
    if disagreements:
        raise LiteralShellError(
            f"PORTME: helmet_color left its proved retail DXN class: "
            f"{disagreements}"
        )


def strict_bc1_descriptor(metadata: Mapping[str, object]) -> None:
    """Fail closed unless the descriptor is the proved BC1 class we author."""

    required = {
        "vc_file_id": "0xcf7f3bdf",
        "vc_width": 256,
        "vc_height": 1024,
        "vc_base_data_length": BC1_BASE_LEN,
        "vc_mip_data_length": BC1_MIP_LEN,
        "pitch_pixels": 256,
        "tiled": True,
        "format": BC1_FORMAT,
        "endianness": 1,
        "stacked": False,
        "width": 256,
        "height": 1024,
        "swizzle_components": [0, 1, 2, 3],
        "mip_min_level": 0,
        "mip_max_level": 6,
        "dimension": 1,
        "packed_mips": True,
        "mip_address_pages": BC1_MIP_ADDRESS_PAGES,
    }
    disagreements = {
        key: (metadata.get(key), wanted)
        for key, wanted in required.items()
        if metadata.get(key) != wanted
    }
    if disagreements:
        raise LiteralShellError(
            f"authored BC1 helmet_color descriptor is not the proved class: "
            f"{disagreements}"
        )


def patched_descriptor(original: bytes) -> bytes:
    """Rewrite one retail 224-byte helmet_color DRAM descriptor to BC1."""

    if len(original) != DRAM_PART_LEN:
        raise LiteralShellError("helmet_color DRAM descriptor length changed")
    out = bytearray(original)
    struct.pack_into(">I", out, VC_BASE_LEN_OFFSET, BC1_BASE_LEN)
    struct.pack_into(">I", out, VC_MIP_LEN_OFFSET, BC1_MIP_LEN)
    dword1 = struct.unpack_from(">I", out, FETCH_DWORD1_OFFSET)[0]
    dword5 = struct.unpack_from(">I", out, FETCH_DWORD5_OFFSET)[0]
    struct.pack_into(
        ">I", out, FETCH_DWORD1_OFFSET, (dword1 & ~0x3F) | BC1_FORMAT
    )
    struct.pack_into(
        ">I",
        out,
        FETCH_DWORD5_OFFSET,
        (dword5 & 0xFFF) | (BC1_MIP_ADDRESS_PAGES << 12),
    )
    strict_bc1_descriptor(apf_inner.parse_txtr_metadata(bytes(out)))
    return bytes(out)


def _encode_levels(
    atlas_rgba: bytes, locations: tuple[bc1_mips.MipLocation, ...],
) -> tuple[list[bytes], list[dict[str, object]]]:
    """BOX-downsample the baked atlas and BC1-encode every mip level.

    Palette-limited artwork (the common case for crest art) is re-snapped to
    its base palette after the BOX resize: averaging otherwise invents a new
    colour per mip texel, which both looks dusty at distance and costs real
    bytes in the fixed H7A allocation.
    """

    palette = sorted({
        atlas_rgba[offset : offset + 3]
        for offset in range(0, len(atlas_rgba), 4)
    })
    linears: list[bytes] = []
    reports: list[dict[str, object]] = []
    for location in locations:
        if location.level == 0:
            level_rgba = atlas_rgba
        else:
            resized = Image.frombytes(
                "RGBA", (locations[0].width, locations[0].height), atlas_rgba
            ).resize(
                (location.width, location.height), Image.Resampling.BOX
            ).tobytes()
            if len(palette) <= 64:
                out = bytearray()
                for offset in range(0, len(resized), 4):
                    pixel = resized[offset : offset + 3]
                    out += min(
                        palette,
                        key=lambda color: sum(
                            (a - b) ** 2 for a, b in zip(pixel, color)
                        ),
                    ) + b"\xff"
                level_rgba = bytes(out)
            else:
                level_rgba = resized
        linear, info = nfl_dxt1.encode_dxt1_opaque(
            level_rgba, location.width, location.height
        )
        if len(linear) != location.logical_block_count * 8:
            raise LiteralShellError(
                f"mip {location.level} BC1 length differs from the layout"
            )
        linears.append(linear)
        reports.append({
            "level": location.level,
            "width": location.width,
            "height": location.height,
            "linear_bc1_sha256": sha256(linear),
            "total_squared_rgb_error": info.total_squared_rgb_error,
            "endpoint_pair_evaluations": info.endpoint_pair_evaluations,
            "selector_evaluations": info.selector_evaluations,
        })
    return linears, reports


def expected_texture(
    original_texture: bytes,
    atlas_rgba: bytes,
    locations: tuple[bc1_mips.MipLocation, ...],
) -> tuple[bytes, list[dict[str, object]]]:
    """Deterministically re-derive the whole helmet_color VRAM subpart."""

    if len(original_texture) != COLOR_VRAM_LEN:
        raise LiteralShellError("helmet_color VRAM subpart length changed")
    linears, reports = _encode_levels(atlas_rgba, locations)
    rebuilt = bytes(original_texture)
    for location, linear in zip(locations, linears):
        rebuilt = bc1_mips.insert_linear_bc1(rebuilt, location, linear)
    return rebuilt, reports


def _validate_structure(
    record: apf_inner.IFFRecord, blocks: list[bytes],
) -> tuple[dict[str, object], bytes]:
    if record.block_count != 2 or record.file_count != 2 or record.warnings:
        raise LiteralShellError("PORTME: helmet IFF structure changed")
    if [item.name for item in record.files] != [INNER_NAME, SIBLING_NAME] or any(
        item.type_name != "TXTR" for item in record.files
    ):
        raise LiteralShellError("PORTME: helmet inner file roster changed")
    expected = [
        [(0, 0x000, 0xE0), (1, 0x000000, 0x60000)],
        [(0, 0x0E0, 0xE0), (1, 0x060000, 0x160000)],
    ]
    actual = [
        [(part.block_index, part.offset, part.length) for part in item.parts]
        for item in record.files
    ]
    if actual != expected:
        raise LiteralShellError("PORTME: helmet DRAM/VRAM subpart layout changed")
    metadata = apf_inner.parse_txtr_metadata(blocks[0][:DRAM_PART_LEN])
    strict_retail_descriptor(metadata)
    return metadata, blocks[1][:COLOR_VRAM_LEN]


def _compress_block(
    original_stored: bytes,
    original_decoded: bytes,
    changed_decoded: bytes,
    shift: int,
) -> tuple[bytes, dict[str, object]]:
    """Retail-token-preserving H7A with a bounded greedy fallback."""

    candidates: list[tuple[str, bytes, dict[str, object]]] = []
    try:
        preserved, report = apf_inner.encode_h7a_preserving_tokens(
            original_stored[apf_inner.H7A_HEADER_SIZE:],
            original_decoded,
            changed_decoded,
            shift,
        )
        candidates.append(("retail_token_preserving", preserved, dict(report)))
    except apf_inner.FormatError:
        pass
    greedy_payloads = [
        archive_patch.compress_h7a(changed_decoded, shift, candidate_limit=limit)
        for limit in (256, H7A_CANDIDATE_LIMIT)
    ]
    for limit, encoded in zip((256, H7A_CANDIDATE_LIMIT), greedy_payloads):
        candidates.append((f"greedy_candidate_limit_{limit}", encoded, {
            "candidate_limit": limit,
        }))
    optimal = archive_patch.compress_h7a_best(
        changed_decoded, shift, greedy=min(greedy_payloads, key=len)
    )
    candidates.append(("optimal_parse", optimal, {}))
    mode, payload, report = min(candidates, key=lambda item: (len(item[1]), item[0]))
    if apf_inner.decompress_h7a(payload, len(changed_decoded), shift) != changed_decoded:
        raise LiteralShellError("helmet H7A encode/decode round-trip failed")
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
    new_blocks: list[bytes],
) -> tuple[bytes, dict[str, object]]:
    descriptor = record.blocks
    new_stored = []
    compression: list[dict[str, object]] = []
    for index, block in enumerate(record.blocks):
        if not block.is_compressed or block.wrapper is None:
            raise LiteralShellError(f"helmet block {index} is not H7A-compressed")
        if new_blocks[index] == original_blocks[index]:
            new_stored.append(original_stored[index])
            compression.append({"index": index, "mode": "unchanged"})
            continue
        payload, report = _compress_block(
            original_stored[index],
            original_blocks[index],
            new_blocks[index],
            block.wrapper.shift,
        )
        new_stored.append(struct.pack(
            ">5I",
            apf_inner.H7A_MAGIC,
            len(new_blocks[index]),
            apf_inner.H7A_HEADER_SIZE + len(payload),
            block.unknown_10,
            block.wrapper.shift,
        ) + payload)
        report["index"] = index
        report["shift"] = block.wrapper.shift
        compression.append(report)
    header = bytearray(original_entry[:record.header_size])
    body = bytearray()
    cursor = record.header_size
    for index, (block, stored) in enumerate(zip(record.blocks, new_stored)):
        struct.pack_into(
            ">8I",
            header,
            apf_inner.IFF_HEADER_SIZE + index * apf_inner.IFF_BLOCK_SIZE,
            block.name_hash,
            block.type_hash,
            block.unknown_08,
            block.uncompressed_length,
            block.unknown_10,
            cursor,
            len(stored),
            block.indexed,
        )
        body.extend(stored)
        cursor += len(stored)
    new_file_length = record.header_size + len(body)
    struct.pack_into(">I", header, 0x08, new_file_length)
    if record.footer is None:
        raise LiteralShellError("PORTME: helmet IFF has no footer")
    footer_size = 8 + record.footer.payload_size
    footer = original_entry[record.file_length:record.file_length + footer_size]
    if any(original_entry[record.file_length + footer_size:]):
        raise LiteralShellError("PORTME: helmet allocation tail is nonzero")
    active = bytes(header) + bytes(body) + footer
    if len(active) > entry.size:
        raise LiteralShellError(
            f"rebuilt helmet IFF exceeds its fixed allocation by "
            f"{len(active) - entry.size} bytes"
        )
    rebuilt = active + bytes(entry.size - len(active))
    memory = archive_patch.BytesReader(rebuilt)
    check_record = apf_inner.parse_iff(memory, entry)
    check_blocks = [
        apf_inner.decode_block(memory, check_record, index, MAX_DECODED)
        for index in range(check_record.block_count)
    ]
    if check_blocks != new_blocks:
        raise LiteralShellError("rebuilt helmet IFF does not decode as intended")
    before_parts = archive_patch._file_part_hashes(record, original_blocks)
    after_parts = archive_patch._file_part_hashes(check_record, check_blocks)
    changed = sorted(
        key for key in before_parts if before_parts[key] != after_parts[key]
    )
    if changed != [(0, 0), (0, 1)]:
        raise LiteralShellError(f"unexpected helmet inner parts changed: {changed}")
    return rebuilt, {
        "allocation_size": entry.size,
        "file_length_before": record.file_length,
        "file_length_after": new_file_length,
        "allocation_slack_after": entry.size - len(active),
        "h7a": compression,
        "footer_bit_exact": rebuilt[
            new_file_length:new_file_length + footer_size
        ] == footer,
        "rebuilt_iff_reparsed": True,
        "helmet_normal_preserved": (
            before_parts[(1, 0)] == after_parts[(1, 0)]
            and before_parts[(1, 1)] == after_parts[(1, 1)]
        ),
        "changed_inner_parts": [
            {"file_index": 0, "part_index": 0, "block_index": 0},
            {"file_index": 0, "part_index": 1, "block_index": 1},
        ],
    }


def build_patch(
    index_path: Path,
    literal_rgba: bytes,
    asset_index: int,
    *,
    shell_color: int = wrap.DEFAULT_SHELL_COLOR_ARGB,
) -> archive_patch.PatchResult:
    """Compile one literal shell bake into its exact fixed helmet package."""

    row = family.target_record(asset_index)
    archive = apf_outer.parse_archive(Path(index_path))
    entry_index = int(row["outer_table_index"])
    try:
        entry = archive.entries[entry_index]
    except IndexError as exc:
        raise LiteralShellError(
            f"outer archive has no entry {entry_index}"
        ) from exc
    if (
        entry.name_id != int(str(row["outer_name_id"]), 16)
        or len(entry.segments) != 1
        or entry.segments[0].pack_name != "0A"
    ):
        raise LiteralShellError("catalog target does not resolve to one 0A segment")
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        original_entry = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, MAX_DECODED)
            for index in range(record.block_count)
        ]
        stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    if sha256(original_entry) != row["outer_allocation"]["sha256"]:
        raise LiteralShellError("source helmet entry differs from catalog hash")
    metadata, texture = _validate_structure(record, blocks)
    if sha256(texture) != row["inner_file"]["texture_sha256"]:
        raise LiteralShellError("source helmet_color differs from catalog hash")

    # The semantic->shell-UV mapping is proved against the pinned helmet_00
    # SCNE (outer 1310); the family catalog guarantees the same shared mesh.
    source_outer = wrap.read_source_outer(Path(index_path))
    parsed = wrap._parse_outer(source_outer, source=True)
    atlas, bake_report = wrap.bake_shell_atlas_literal(
        parsed.system, literal_rgba, shell_color=shell_color
    )

    new_descriptor = patched_descriptor(blocks[0][:DRAM_PART_LEN])
    locations = bc1_mips.derive_layout(
        apf_inner.parse_txtr_metadata(new_descriptor)
    )
    if len(locations) != 7:
        raise LiteralShellError("BC1 helmet_color mip chain is not seven levels")
    if bc1_mips.transport_roundtrip(texture, locations) != texture:
        raise LiteralShellError("retail DXN bytes alias the BC1 layout")
    new_texture, level_reports = expected_texture(texture, atlas, locations)
    mask = bytearray(len(texture))
    for location in locations:
        for y in range(location.height_blocks):
            for x in range(location.width_blocks):
                relative = apf_inner._tiled_2d_offset(
                    x + location.origin_block_x,
                    y + location.origin_block_y,
                    location.pitch_blocks,
                    3,
                )
                start = location.data_offset + relative
                mask[start:start + 8] = b"\1" * 8
    # Tiled small mips leave padding holes inside their 32-aligned extents;
    # the invariant is that no active block lands beyond the declared mip
    # span and that derive_layout proved the active blocks alias-free.
    if any(mask[BC1_ACTIVE_LEN:]):
        raise LiteralShellError("BC1 active block beyond the declared mip span")
    active_mask = bytes(mask)
    new_block0 = new_descriptor + blocks[0][DRAM_PART_LEN:]
    new_block1 = bytearray(blocks[1])
    new_block1[:COLOR_VRAM_LEN] = new_texture
    new_blocks = [new_block0, bytes(new_block1)]
    rebuilt, iff = _rebuild_entry(
        entry, record, original_entry, blocks, stored, new_blocks
    )
    manifest = {
        "schema": SCHEMA,
        "mode": "native_material_literal",
        "source": {
            "archive_index": str(index_path),
            "physical_volume": "0A",
            "outer_entry_index": entry_index,
            "outer_name": row["outer_name"],
            "inner_file_index": INNER_INDEX,
            "inner_name": INNER_NAME,
            "entry_sha256": sha256(original_entry),
            "texture_sha256": sha256(texture),
            "retail_volume_sha256": family.EXPECTED_VOLUME_SHA256,
        },
        "family_target": {
            "asset_index": asset_index,
            "outer_name": row["outer_name"],
            "outer_table_index": entry_index,
            "fixed_allocation": row["outer_allocation"]["size"],
            "catalog_sha256": family.EXPECTED_CATALOG_SHA256,
            "team_bank_use_count": row["team_bank_use_count"],
            "editing_affects_every_listed_use": True,
        },
        "bake": bake_report,
        "descriptor": {
            "retail": metadata,
            "authored": apf_inner.parse_txtr_metadata(new_descriptor),
            "codec_change": "DXN/BC5 stripe mask -> DXT1/BC1 literal RGB",
            "dram_descriptor_bytes_changed": DRAM_PART_LEN,
        },
        "levels": level_reports,
        "texture": {
            "length": len(texture),
            "sha256_before": sha256(texture),
            "sha256_after": sha256(new_texture),
            "bc1_active_span_bytes": BC1_ACTIVE_LEN,
            "inactive_padding_sha256": sha256(bytes(
                value for index, value in enumerate(texture)
                if not active_mask[index]
            )),
            "inactive_padding_preserved": all(
                new_texture[index] == texture[index]
                for index in range(len(texture))
                if not active_mask[index]
            ),
        },
        "iff": iff,
        "binary_patch_manifest": {
            "physical_volume": "0A",
            "physical_offset": entry.segments[0].pack_offset,
            "replacement_length": entry.size,
            "original_sha256": sha256(original_entry),
            "replacement_sha256": sha256(rebuilt),
            **archive_patch._changed_extents(original_entry, rebuilt),
            "contains_replacement_bytes": False,
        },
        "validation": {
            "all_seven_levels_regenerated": True,
            "bc1_transport_roundtrip_exact": (
                bc1_mips.transport_roundtrip(new_texture, locations) == new_texture
            ),
            "inactive_vram_padding_bit_exact": (
                new_texture[BC1_ACTIVE_LEN:] == texture[BC1_ACTIVE_LEN:]
            ),
            "helmet_normal_preserved": True,
            "draw_routes_and_overlays_untouched": True,
            "crest_packages_and_menu_logos_untouched": True,
            "rebuilt_iff_reparsed": True,
            "footer_bit_exact": True,
            "fixed_outer_allocation": True,
            "source_opened_read_only": True,
        },
        "backend": {
            "png_and_mips": f"Pillow {PILLOW_VERSION}; BOX mip filter",
            "bc1": "project-native deterministic opaque BC1 encoder",
            "xenos_layout": f"Xenia-derived, commit {bc1_mips.XENIA_COMMIT}",
            "h7a": "retail-token preserving plus bounded greedy fit candidates",
        },
        "portme": [
            "validate the copied volume in Xenia and on hardware",
            BC1_PRODUCTION_CAVEAT,
        ],
    }
    return archive_patch.PatchResult(rebuilt, manifest)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path,
                        help="user-owned retail APF 0A")
    parser.add_argument("--asset-index", required=True, type=int,
                        help="uniform_helmet index 0..23")
    parser.add_argument("--literal-png", type=Path,
                        help="exact opaque 512x512 literal painted RGBA PNG")
    parser.add_argument("--mask-png", type=Path,
                        help="or: opaque 512x512 APF region mask, converted")
    parser.add_argument("--shell-color", default="FF004C54",
                        help="shell body ARGB hex (default FF004C54)")
    parser.add_argument("--output-entry", type=Path)
    parser.add_argument("--output-volume", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if (args.literal_png is None) == (args.mask_png is None):
            raise LiteralShellError(
                "supply exactly one of --literal-png or --mask-png"
            )
        if args.literal_png is not None:
            literal = wrap._read_rgba_png(args.literal_png, "literal PNG")
        else:
            literal = wrap.literal_rgba_from_region_mask(
                wrap._read_rgba_png(args.mask_png, "mask PNG")
            )
        shell_color = int(args.shell_color, 16)
        result = build_patch(
            args.index, literal, args.asset_index, shell_color=shell_color
        )
        document = result.manifest
        if args.output_entry is not None:
            archive_patch._write_new(args.output_entry, result.entry_bytes)
            document["output_entry"] = {
                "path": str(args.output_entry),
                "size": len(result.entry_bytes),
                "sha256": sha256(result.entry_bytes),
            }
        if args.output_volume is not None:
            archive = apf_outer.parse_archive(args.index)
            document["copied_volume"] = archive_patch._write_copied_volume(
                args.index,
                args.output_volume,
                archive.entries[int(document["family_target"]["outer_table_index"])],
                result.entry_bytes,
            )
        archive_patch._write_new(
            args.manifest,
            (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        print(json.dumps({
            "outer_entry_sha256": sha256(result.entry_bytes),
            "schema": SCHEMA,
        }, sort_keys=True))
    except (
        LiteralShellError,
        wrap.PatchError,
        bc1_mips.MipLayoutError,
        archive_patch.PatchError,
        apf_inner.FormatError,
        apf_outer.FormatError,
        nfl_dxt1.Dxt1Error,
        OSError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
