#!/usr/bin/env python3
"""Validate any fresh 09H0 PNG-import span without pinned content hashes.

The validator reconstructs the deterministic decoded/video data from the raw
PNG input(s) and retail template, recompresses it, and requires exact equality
with the proposed span.  It therefore does not trust hashes asserted by the
import manifest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import struct

import nfl_tset_png_import as importer
import nfl_tset_png_import_verify as independent_png
from nfl_tset_fixed_span_verify import independent_decode
from nfl_txtr import HEADER, compress_vc_lz, rebuild_compressed_chunk_fixed_span


SCHEMA = "nfl2k5_tset_png_import/v2"
SOURCE_SPAN_SHA256 = "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862"
SOURCE_DECODED_SHA256 = "92a7e5ed6b8d0b468c4782509cf6335f88dfa06e189d7b624f80600ce727aa1e"
SPAN_SIZE = 74720
STORED_SIZE = 74688


class DynamicValidationError(ValueError):
    """Raised when a dynamic PNG-import artifact cannot be independently proved."""


@dataclass(frozen=True)
class ValidatedImport:
    span_sha256: str
    decoded_sha256: str
    import_manifest_sha256: str
    clean_png_sha256: str
    mud_source_kind: str
    mud_png_sha256: str | None
    encoded_bytes: int
    zero_padding_bytes: int
    template_overlap_scratch_bytes: int
    rebuilt_overlap_scratch_bytes: int
    loader_in_place_end_guard: bool
    loader_in_place_alias_guard: bool
    palette_entries: int
    quantization_differing_pixels: int
    mip_count: int
    preview_count: int
    shared_indices: bool


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DynamicValidationError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_dynamic_import(
    *,
    source_span: bytes,
    replacement_span: bytes,
    import_manifest_payload: bytes,
    clean_png_name: str,
    clean_png_payload: bytes,
    mud_png_name: str | None,
    mud_png_payload: bytes | None,
    preview_payloads: dict[str, bytes],
    replacement_span_name: str | None = None,
    import_manifest_name: str | None = None,
    preview_directory_name: str | None = None,
) -> tuple[ValidatedImport, dict[str, object]]:
    require(len(source_span) == len(replacement_span) == SPAN_SIZE,
            "source/replacement span size mismatch")
    require(sha256_bytes(source_span) == SOURCE_SPAN_SHA256,
            "retail source TSET span hash mismatch")
    expected_header = (b"TSET", STORED_SIZE, 256, 176768,
                       0xFEEDBEEF, 32, 0, 0)
    replacement_header = HEADER.unpack_from(replacement_span)
    require(HEADER.unpack_from(source_span) == expected_header and
            replacement_header[:5] == expected_header[:5] and
            replacement_header[6:] == expected_header[6:] and
            replacement_header[5] >= expected_header[5] and
            replacement_header[5] % 16 == 0,
            "source/replacement TSET wrapper mismatch")
    source_decoded, source_metrics = independent_decode(source_span[HEADER.size:])
    require(sha256_bytes(source_decoded) == SOURCE_DECODED_SHA256 and
            source_metrics["consumed_bytes"] == 74674,
            "retail source TSET decode mismatch")

    def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON object key: {key}")
            result[key] = value
        return result

    try:
        manifest = json.loads(
            import_manifest_payload,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DynamicValidationError("PNG-import manifest is invalid JSON") from exc
    require(isinstance(manifest, dict), "PNG-import manifest root must be an object")
    require(
        import_manifest_payload ==
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        "PNG-import manifest is not the importer's canonical JSON encoding",
    )
    require(set(manifest) == {
        "schema", "source_index", "canonical_inventory", "target", "input",
        "mips", "quantization", "layout", "compression", "rebuild",
        "previews", "claims", "outputs",
    }, "PNG-import manifest top-level fields mismatch")
    require(manifest.get("schema") == SCHEMA, "PNG-import manifest schema mismatch")
    require(isinstance(manifest.get("source_index"), str) and
            bool(manifest.get("source_index")) and
            isinstance(manifest.get("canonical_inventory"), str) and
            bool(manifest.get("canonical_inventory")),
            "PNG-import manifest source provenance fields are invalid")
    target = manifest.get("target")
    require(target == {
        "logical_name": "09H0.IFF",
        "outer_index": 3685,
        "outer_id": "0x9a4832d6",
        "chunk_index": 1,
        "chunk_offset": 0x70,
        "stored_size": STORED_SIZE,
        "complete_span_size": SPAN_SIZE,
        "template_overlap_scratch_bytes": 32,
        "rebuilt_overlap_scratch_bytes": replacement_header[5],
        "template_span_sha256": SOURCE_SPAN_SHA256,
        "template_decoded_sha256": SOURCE_DECODED_SHA256,
        "system_bytes_preserved": True,
        "descriptor_records_preserved": True,
    }, "PNG-import manifest target/layout mismatch")

    input_record = manifest.get("input")
    require(isinstance(input_record, dict) and set(input_record) == {"clean", "mud"},
            "PNG-import manifest input fields mismatch")
    clean_record = input_record.get("clean")
    clean_sha = sha256_bytes(clean_png_payload)
    require(clean_record == {
        "file_name": clean_png_name,
        "sha256": clean_sha,
        "width": 512,
        "height": 256,
        "format": "RGBA8_noninterlaced",
    }, "clean PNG manifest provenance mismatch")
    width, height, clean_rgba = importer.decode_rgba_png(clean_png_payload)
    clean_mips = importer.generate_mips(clean_rgba, width, height)
    clean_palette, index_levels, quantization = importer.quantize_levels(clean_mips)
    clean_expected = [
        importer.MipLevel(level.level, level.width, level.height,
                          importer.rgba_from_indices(indices, clean_palette))
        for level, indices in zip(clean_mips, index_levels)
    ]

    quant_record = manifest.get("quantization")
    require(quant_record == {
        "algorithm": "weighted_median_cut_rgba_then_nearest_rgba_squared_error",
        "tie_breaks": "channel R,G,B,A; stable lexical colors; lowest palette index",
        **quantization,
        "clean_palette_entries": len(clean_palette),
        # Filled after the mud palette is reconstructed below.
        "mud_palette_entries": quant_record.get("mud_palette_entries")
        if isinstance(quant_record, dict) else None,
        "shared_index_chain": True,
    }, "quantization algorithm/metrics manifest mismatch")

    mud_record = input_record.get("mud")
    require(isinstance(mud_record, dict), "mud input record is not an object")
    mud_kind = mud_record.get("kind")
    mud_sha: str | None = None
    if mud_kind == "derived_palette":
        require(mud_png_payload is None and mud_png_name is None,
                "manifest derives mud but a mud PNG was supplied")
        mode = mud_record.get("mode")
        require(mode in ("identity", "darken_60"), "invalid derived mud mode")
        require(mud_record == {"kind": "derived_palette", "mode": mode},
                "derived mud manifest fields mismatch")
        mud_palette = importer.derive_mud_palette(clean_palette, str(mode))
        mud_expected = [
            importer.MipLevel(level.level, level.width, level.height,
                              importer.rgba_from_indices(indices, mud_palette))
            for level, indices in zip(clean_mips, index_levels)
        ]
    elif mud_kind == "second_png_exact_shared_indices":
        require(mud_png_payload is not None and mud_png_name is not None,
                "manifest requires a mud PNG but none was supplied")
        mud_sha = sha256_bytes(mud_png_payload)
        require(mud_record.get("file_name") == mud_png_name and
                mud_record.get("sha256") == mud_sha,
                "mud PNG manifest provenance mismatch")
        require(mud_record == {
            "kind": "second_png_exact_shared_indices",
            "file_name": mud_png_name,
            "sha256": mud_sha,
        }, "mud PNG manifest fields mismatch")
        mud_width, mud_height, mud_rgba = importer.decode_rgba_png(mud_png_payload)
        mud_expected = importer.generate_mips(mud_rgba, mud_width, mud_height)
        mud_palette_full = importer.palette_for_shared_mud(index_levels, mud_expected)
        highest_used = max(index for level in index_levels for index in level)
        mud_palette = mud_palette_full[:highest_used + 1]
    else:
        raise DynamicValidationError(f"unsupported manifest mud source {mud_kind!r}")
    require(isinstance(quant_record, dict) and
            quant_record.get("mud_palette_entries") == len(mud_palette),
            "mud palette entry count differs from reconstruction")

    index_chain = b"".join(
        importer.swizzle_2d(indices, level.width, level.height, 1)
        for level, indices in zip(clean_mips, index_levels)
    )
    require(len(index_chain) == importer.INDEX_CHAIN_BYTES,
            "reconstructed shared mip index chain size mismatch")
    expected_decoded = bytearray(source_decoded)
    expected_decoded[256:256 + importer.INDEX_CHAIN_BYTES] = index_chain
    expected_decoded[
        256 + importer.CLEAN_PALETTE_OFFSET:
        256 + importer.CLEAN_PALETTE_OFFSET + 1024
    ] = importer.palette_bytes(clean_palette)
    expected_decoded[
        256 + importer.MUD_PALETTE_OFFSET:
        256 + importer.MUD_PALETTE_OFFSET + 1024
    ] = importer.palette_bytes(mud_palette)
    expected_decoded_bytes = bytes(expected_decoded)

    replacement_decoded, replacement_metrics = independent_decode(
        replacement_span[HEADER.size:]
    )
    require(replacement_decoded == expected_decoded_bytes,
            "replacement decoded bytes do not derive from supplied PNG(s)")
    independent_png.validate_descriptors(replacement_decoded)
    # The frozen artifact verifier's decode_mips intentionally pins the
    # 32-color CODEX MOD fixture.  Decode arbitrary imports here with only its
    # independent Morton unswizzler/palette parser, then compare against the
    # freshly reconstructed user-image chain below.
    video = replacement_decoded[256:]
    independent_clean_palette = independent_png.parse_palette(
        video, importer.CLEAN_PALETTE_OFFSET
    )
    independent_mud_palette = independent_png.parse_palette(
        video, importer.MUD_PALETTE_OFFSET
    )
    decoded_indices: list[bytes] = []
    decoded_clean: list[bytes] = []
    decoded_mud: list[bytes] = []
    mip_offset = 0
    for level_width, level_height in importer.MIP_DIMENSIONS:
        mip_size = level_width * level_height
        indices = independent_png.independent_unswizzle(
            video[mip_offset:mip_offset + mip_size], level_width, level_height
        )
        decoded_indices.append(indices)
        decoded_clean.append(independent_png.expand(indices, independent_clean_palette))
        decoded_mud.append(independent_png.expand(indices, independent_mud_palette))
        mip_offset += mip_size
    require(mip_offset == importer.INDEX_CHAIN_BYTES and
            decoded_indices == index_levels,
            "independent unswizzle differs from reconstructed shared index chain")
    require(decoded_clean == [level.rgba for level in clean_expected] and
            decoded_mud == [level.rgba for level in mud_expected],
            "replacement decoded mip chain differs from deterministic reconstruction")

    stream_tag = int.from_bytes(source_span[HEADER.size + 4:HEADER.size + 8], "little")
    offset_bits = source_span[HEADER.size + 8]
    encoded, compression_info = compress_vc_lz(
        expected_decoded_bytes,
        stream_tag=stream_tag,
        offset_bits=offset_bits,
        max_encoded_size=STORED_SIZE,
    )
    exact_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        source_span, expected_decoded_bytes
    )
    require(exact_span == replacement_span,
            "replacement span is not the deterministic fixed-span rebuild")
    require(replacement_metrics["consumed_bytes"] == len(encoded) and
            replacement_span[HEADER.size + len(encoded):] ==
            bytes(STORED_SIZE - len(encoded)),
            "replacement stream consumption/zero padding mismatch")

    compression_record = manifest.get("compression", {})
    require(compression_record == asdict(compression_info),
            "compression manifest differs from deterministic recompression")
    rebuild_record = manifest.get("rebuild")
    require(rebuild_record == {
        **asdict(rebuild_info),
        "decoded_roundtrip_sha256": sha256_bytes(expected_decoded_bytes),
        "complete_span_sha256": sha256_bytes(replacement_span),
        "complete_span_size": SPAN_SIZE,
        "fixed_span_fit": True,
        "zero_padding_verified": True,
    }, "rebuild manifest differs from exact deterministic span")

    mip_record = manifest.get("mips")
    require(mip_record == {
        "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
        "level_count": 6,
        "dimensions": [list(item) for item in importer.MIP_DIMENSIONS],
        "linear_index_bytes_by_level": [
            width * height for width, height in importer.MIP_DIMENSIONS
        ],
        "total_index_chain_bytes": importer.INDEX_CHAIN_BYTES,
        "each_level_swizzled_independently": True,
    }, "mip manifest layout mismatch")
    layout_record = manifest.get("layout")
    require(layout_record == {
        "index_offset": 0,
        "clean_palette_offset": importer.CLEAN_PALETTE_OFFSET,
        "mud_palette_offset": importer.MUD_PALETTE_OFFSET,
        "palette_bytes_each": 1024,
        "video_bytes": importer.VIDEO_BYTES,
        "unused_palette_entries_zero_filled": True,
    }, "video layout manifest mismatch")

    preview_rows = manifest.get("previews")
    require(isinstance(preview_rows, list) and len(preview_rows) == 12,
            "preview manifest row count mismatch")
    expected_preview_names: set[str] = set()
    expected_preview_rows: list[dict[str, object]] = []
    for role, levels in (("clean", decoded_clean), ("mud", decoded_mud)):
        for level_index, rgba in enumerate(levels):
            level_width, level_height = importer.MIP_DIMENSIONS[level_index]
            name = f"{role}_mip{level_index}_{level_width}x{level_height}.png"
            expected_preview_names.add(name)
            require(name in preview_payloads, f"preview payload absent: {name}")
            payload = preview_payloads[name]
            parsed = importer.decode_rgba_png(payload, (level_width, level_height))
            require(parsed == (level_width, level_height, rgba),
                    f"preview PNG differs from decoded TSET mip: {name}")
            expected_preview_rows.append({
                "role": role,
                "level": level_index,
                "width": level_width,
                "height": level_height,
                "rgba_sha256": sha256_bytes(rgba),
                "png_file": name,
                "png_sha256": sha256_bytes(payload),
                "strictly_reparsed": True,
            })
    require(set(preview_payloads) == expected_preview_names,
            "preview payload file set differs from exact twelve mips")
    require(preview_rows == expected_preview_rows,
            "preview manifest rows differ from exact decoded mip sequence")

    claims = manifest.get("claims")
    require(claims == {
        "real_png_input_consumed": True,
        "all_clean_and_mud_mips_generated": True,
        "all_mips_swizzled_and_decoded": True,
        "all_preview_pngs_strictly_reparsed": True,
        "two_reference_shared_index_layout_preserved": True,
        "target_wrapper_preserved_except_loader_overlap_scratch": True,
        "loader_in_place_decode_guarded": True,
        "fixed_span_only": True,
        "output_exclusively_created": True,
        "originals_modified": False,
        "xiso_created": False,
        "title_executed": False,
        "runtime_visibility_proved": False,
        "general_tset_layout_support": False,
        "portme": (
            "PORTME: validate this span in a copied archive/XISO and runtime only "
            "after the offline artifact and manifest are frozen."
        ),
    }, "PNG-import manifest scope/claims mismatch")

    outputs = manifest.get("outputs")
    require(isinstance(outputs, dict) and set(outputs) == {
        "span_file", "manifest_file", "preview_directory", "preview_file_count"
    } and outputs.get("preview_file_count") == 12,
            "PNG-import manifest output fields mismatch")
    if replacement_span_name is not None:
        require(outputs.get("span_file") == replacement_span_name,
                "PNG-import manifest span filename provenance mismatch")
    if import_manifest_name is not None:
        require(outputs.get("manifest_file") == import_manifest_name,
                "PNG-import manifest filename provenance mismatch")
    if preview_directory_name is not None:
        require(outputs.get("preview_directory") == preview_directory_name,
                "PNG-import manifest preview-directory provenance mismatch")

    validated = ValidatedImport(
        span_sha256=sha256_bytes(replacement_span),
        decoded_sha256=sha256_bytes(replacement_decoded),
        import_manifest_sha256=sha256_bytes(import_manifest_payload),
        clean_png_sha256=clean_sha,
        mud_source_kind=str(mud_kind),
        mud_png_sha256=mud_sha,
        encoded_bytes=len(encoded),
        zero_padding_bytes=STORED_SIZE - len(encoded),
        template_overlap_scratch_bytes=32,
        rebuilt_overlap_scratch_bytes=int(replacement_header[5]),
        loader_in_place_end_guard=bool(rebuild_info.loader_in_place_end_guard),
        loader_in_place_alias_guard=bool(rebuild_info.loader_in_place_alias_guard),
        palette_entries=len(clean_palette),
        quantization_differing_pixels=quantization["differing_pixel_count"],
        mip_count=6,
        preview_count=12,
        shared_indices=True,
    )
    evidence = {
        "validated": asdict(validated),
        "quantization": quantization,
        "mud_mode": mud_record,
        "compression": asdict(compression_info),
        "replacement_independent_decode": replacement_metrics,
    }
    return validated, evidence
