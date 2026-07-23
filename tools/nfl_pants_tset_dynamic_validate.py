#!/usr/bin/env python3
"""Independently validate a selected compatible pants PNG-import span."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import struct

import nfl_tset_png_import as legacy
import nfl_tset_png_import_verify as independent_png
from nfl_txtr import HEADER, compress_vc_lz, minimum_vc_lz_overlap_scratch, \
    rebuild_compressed_chunk_fixed_span
import nfl_pants_tset_png_import as pants
from nfl_pants_tset_png_import import SCHEMA
from nfl_pants_tset_targets import PantsTarget, load_report


class DynamicValidationError(ValueError):
    """Raised when a selected import cannot be reconstructed exactly."""


@dataclass(frozen=True)
class ValidatedImport:
    selector: str
    logical_name: str
    outer_index: int
    span_sha256: str
    decoded_sha256: str
    import_manifest_sha256: str
    clean_png_sha256: str
    mud_source_kind: str
    mud_png_sha256: str | None
    encoded_bytes: int
    stored_size: int
    zero_padding_bytes: int
    template_overlap_scratch_bytes: int
    template_exact_minimum_overlap_scratch_bytes: int
    rebuilt_overlap_scratch_bytes: int
    rebuilt_exact_minimum_overlap_scratch_bytes: int
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


def validate_pants_descriptors(decoded: bytes) -> None:
    """Independently validate the universal chunk-3 pants system block."""

    require(len(decoded) == 256 + pants.VIDEO_BYTES and
            sha256_bytes(decoded[:256]) ==
            "a9591e8d3ebf355824db06d6689b780f8c1ff222a00877042788fd3723ce77c4",
            "pants decoded size/system block mismatch")
    require(struct.unpack_from("<II", decoded, 0) == (0x0D, 2),
            "pants TSET root mismatch")
    for index, name in enumerate(("pants00", "pants00_mud")):
        base = 0x18 + index * 0x24
        require(decoded[base:base + 4] == b"TXTR",
                "embedded pants TXTR marker missing")
        name_offset = independent_png.relative_pointer(decoded, base + 4, "name")
        descriptor_offset = independent_png.relative_pointer(
            decoded, base + 8, "descriptor"
        )
        root_offset = independent_png.relative_pointer(decoded, base + 0x14, "root")
        require(name_offset == (84 if index == 0 else 100) and
                independent_png.utf16z(decoded, name_offset, 256, "name") == name,
                f"embedded pants name {index} mismatch")
        require(root_offset == 0 and
                descriptor_offset == (124 if index == 0 else 156),
                f"pants descriptor/root {index} mismatch")
        words = struct.unpack_from("<6I", decoded, descriptor_offset)
        require(words == (
            0, 0,
            pants.CLEAN_PALETTE_OFFSET if index == 0 else pants.MUD_PALETTE_OFFSET,
            0x08960B29, 0, 0x80000000,
        ), f"pants descriptor words {index} mismatch")
    require(decoded[
        256 + pants.INTERPALETTE_GAP_OFFSET:
        256 + pants.INTERPALETTE_GAP_OFFSET + pants.INTERPALETTE_GAP_BYTES
    ] == bytes(pants.INTERPALETTE_GAP_BYTES),
            "pants decoded inter-palette gap mismatch")


def independent_decode_target(stream: bytes, target: PantsTarget) \
        -> tuple[bytes, dict[str, int]]:
    """Independent VC-LZ decoder parameterized only by the selected target."""

    require(len(stream) >= 10, "VC-LZ stream prefix is truncated")
    output_size, stream_tag = struct.unpack_from("<II", stream, 0)
    offset_bits = stream[8]
    require(output_size == target.decoded_size and
            stream_tag == target.stream_tag and offset_bits == target.offset_bits and
            1 <= offset_bits <= 15,
            "VC-LZ target prefix mismatch")
    length_bits = 16 - offset_bits
    distance_mask = (1 << offset_bits) - 1
    length_mask = (1 << length_bits) - 1
    output = bytearray(output_size)
    source_offset = 9
    flags = stream[source_offset]
    source_offset += 1
    flag_mask = 1
    output_offset = 0
    literal_count = 0
    match_count = 0
    maximum_distance = 0
    maximum_length = 0
    while output_offset < output_size:
        if flags & flag_mask:
            require(source_offset + 2 <= len(stream), "truncated VC-LZ match")
            code = struct.unpack_from("<H", stream, source_offset)[0]
            source_offset += 2
            distance = code & distance_mask
            length = ((code >> offset_bits) & length_mask) + 3
            require(0 < distance <= output_offset and
                    output_offset + length <= output_size,
                    "invalid VC-LZ match distance/length")
            for index in range(length - 1, -1, -1):
                output[output_offset + index] = output[
                    output_offset - distance + index
                ]
            output_offset += length
            match_count += 1
            maximum_distance = max(maximum_distance, distance)
            maximum_length = max(maximum_length, length)
        else:
            require(source_offset < len(stream), "truncated VC-LZ literal")
            output[output_offset] = stream[source_offset]
            source_offset += 1
            output_offset += 1
            literal_count += 1
        flag_mask = (flag_mask << 1) & 0xFF
        if flag_mask == 0 and output_offset < output_size:
            require(source_offset < len(stream), "missing VC-LZ flag byte")
            flags = stream[source_offset]
            source_offset += 1
            flag_mask = 1
    return bytes(output), {
        "consumed_bytes": source_offset,
        "literal_count": literal_count,
        "match_count": match_count,
        "maximum_distance": maximum_distance,
        "maximum_length": maximum_length,
    }


def parse_manifest(payload: bytes) -> dict[str, object]:
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            require(key not in value, f"duplicate JSON key: {key}")
            value[key] = item
        return value

    try:
        value = json.loads(payload, object_pairs_hook=no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DynamicValidationError("import manifest is invalid JSON") from exc
    require(isinstance(value, dict) and
            payload == (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
            "import manifest is not canonical JSON")
    return value


def validate_dynamic_import(
    *,
    target: PantsTarget,
    compatibility_path: Path,
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
    compatibility_resolved, _, compatibility_payload = load_report(compatibility_path)
    require(len(source_span) == len(replacement_span) == target.span_size,
            "source/replacement target span size mismatch")
    replacement_header = HEADER.unpack_from(replacement_span)
    require(sha256_bytes(source_span) == target.span_sha256 and
            HEADER.unpack_from(source_span) == target.complete_header and
            replacement_header[:5] == target.complete_header[:5] and
            replacement_header[6:] == target.complete_header[6:] and
            replacement_header[5] >= target.overlap_scratch_bytes and
            replacement_header[5] % 16 == 0,
            "target source hash or wrapper mismatch")
    source_decoded, source_metrics = independent_decode_target(
        source_span[HEADER.size:], target
    )
    source_exact_alias_scratch = minimum_vc_lz_overlap_scratch(
        source_span[
            HEADER.size:HEADER.size + source_metrics["consumed_bytes"]
        ],
        target.stored_size,
        target.decoded_size,
    )
    require(len(source_decoded) == target.decoded_size and
            sha256_bytes(source_decoded) == target.decoded_sha256 and
            source_metrics["consumed_bytes"] == target.lz_consumed_bytes and
            source_exact_alias_scratch ==
                target.retail_exact_minimum_overlap_scratch_bytes and
            target.overlap_scratch_bytes >= source_exact_alias_scratch,
            "target source independent decode mismatch")
    validate_pants_descriptors(source_decoded)

    manifest = parse_manifest(import_manifest_payload)
    require(set(manifest) == {
        "schema", "source_index", "canonical_inventory", "compatibility_report",
        "target", "input", "mips", "quantization", "layout", "compression",
        "rebuild", "previews", "claims", "outputs",
    } and manifest.get("schema") == SCHEMA,
            "import manifest schema/top-level fields mismatch")
    require(isinstance(manifest.get("source_index"), str) and
            bool(manifest.get("source_index")) and
            isinstance(manifest.get("canonical_inventory"), str) and
            bool(manifest.get("canonical_inventory")),
            "import manifest source inventory paths are invalid")
    require(manifest.get("compatibility_report") == {
        "path": str(compatibility_resolved),
        "sha256": sha256_bytes(compatibility_payload),
        "layout_signature_sha256": target.layout_signature_sha256,
    }, "import compatibility-report provenance mismatch")
    require(manifest.get("target") == {
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
        "rebuilt_overlap_scratch_bytes": replacement_header[5],
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
    }, "import target selector/layout/mapping mismatch")

    input_record = manifest.get("input")
    require(isinstance(input_record, dict) and set(input_record) == {"clean", "mud"},
            "import input fields mismatch")
    clean_sha = sha256_bytes(clean_png_payload)
    require(input_record.get("clean") == {
        "file_name": clean_png_name,
        "sha256": clean_sha,
        "width": 512,
        "height": 256,
        "format": "RGBA8_noninterlaced",
    }, "clean PNG provenance mismatch")
    width, height, clean_rgba = legacy.decode_rgba_png(
        clean_png_payload, (pants.BASE_WIDTH, pants.BASE_HEIGHT)
    )
    clean_mips = pants.generate_mips(clean_rgba, width, height)
    clean_palette, index_levels, quantization = legacy.quantize_levels(clean_mips)
    clean_expected = [
        legacy.MipLevel(level.level, level.width, level.height,
                        legacy.rgba_from_indices(indices, clean_palette))
        for level, indices in zip(clean_mips, index_levels)
    ]

    mud_record = input_record.get("mud")
    require(isinstance(mud_record, dict), "mud provenance is not an object")
    mud_kind = mud_record.get("kind")
    mud_sha: str | None = None
    if mud_kind == "derived_palette":
        require(mud_png_name is None and mud_png_payload is None,
                "manifest derives mud but a mud PNG was supplied")
        mode = mud_record.get("mode")
        require(mode in {"identity", "darken_60"} and
                mud_record == {"kind": "derived_palette", "mode": mode},
                "derived mud record mismatch")
        mud_palette = legacy.derive_mud_palette(clean_palette, str(mode))
        mud_expected = [
            legacy.MipLevel(level.level, level.width, level.height,
                            legacy.rgba_from_indices(indices, mud_palette))
            for level, indices in zip(clean_mips, index_levels)
        ]
    elif mud_kind == "second_png_exact_shared_indices":
        require(mud_png_name is not None and mud_png_payload is not None,
                "manifest requires a mud PNG")
        mud_sha = sha256_bytes(mud_png_payload)
        require(mud_record == {
            "kind": "second_png_exact_shared_indices",
            "file_name": mud_png_name,
            "sha256": mud_sha,
        }, "mud PNG provenance mismatch")
        mud_width, mud_height, mud_rgba = legacy.decode_rgba_png(
            mud_png_payload, (pants.BASE_WIDTH, pants.BASE_HEIGHT)
        )
        mud_expected = pants.generate_mips(mud_rgba, mud_width, mud_height)
        full_palette = legacy.palette_for_shared_mud(index_levels, mud_expected)
        highest_used = max(index for level in index_levels for index in level)
        mud_palette = full_palette[:highest_used + 1]
    else:
        raise DynamicValidationError(f"unsupported mud source: {mud_kind!r}")

    quant_record = manifest.get("quantization")
    require(quant_record == {
        "algorithm": "weighted_median_cut_rgba_then_nearest_rgba_squared_error",
        "tie_breaks": "channel R,G,B,A; stable lexical colors; lowest palette index",
        **quantization,
        "clean_palette_entries": len(clean_palette),
        "mud_palette_entries": len(mud_palette),
        "shared_index_chain": True,
    }, "quantization metrics differ from raw PNG reconstruction")
    require(manifest.get("mips") == {
        "filter": "unpremultiplied_rgba_2x2_box_round_nearest",
        "level_count": 6,
        "dimensions": [list(item) for item in pants.MIP_DIMENSIONS],
        "linear_index_bytes_by_level": [
            mip_width * mip_height for mip_width, mip_height in pants.MIP_DIMENSIONS
        ],
        "total_index_chain_bytes": pants.INDEX_CHAIN_BYTES,
        "each_level_swizzled_independently": True,
    }, "mip manifest differs from compatible layout")
    require(manifest.get("layout") == {
        "index_offset": 0,
        "clean_palette_offset": pants.CLEAN_PALETTE_OFFSET,
        "interpalette_gap_offset": pants.INTERPALETTE_GAP_OFFSET,
        "interpalette_gap_bytes": pants.INTERPALETTE_GAP_BYTES,
        "interpalette_gap_zero_and_preserved": True,
        "mud_palette_offset": pants.MUD_PALETTE_OFFSET,
        "palette_bytes_each": 1024,
        "video_bytes": pants.VIDEO_BYTES,
        "unused_palette_entries_zero_filled": True,
    }, "video layout manifest mismatch")

    index_chain = b"".join(
        legacy.swizzle_2d(indices, level.width, level.height, 1)
        for level, indices in zip(clean_mips, index_levels)
    )
    expected_decoded = bytearray(source_decoded)
    expected_decoded[256:256 + pants.INDEX_CHAIN_BYTES] = index_chain
    expected_decoded[
        256 + pants.CLEAN_PALETTE_OFFSET:
        256 + pants.CLEAN_PALETTE_OFFSET + 1024
    ] = legacy.palette_bytes(clean_palette)
    expected_decoded[
        256 + pants.MUD_PALETTE_OFFSET:
        256 + pants.MUD_PALETTE_OFFSET + 1024
    ] = legacy.palette_bytes(mud_palette)
    expected_decoded_bytes = bytes(expected_decoded)
    replacement_decoded, replacement_metrics = independent_decode_target(
        replacement_span[HEADER.size:], target
    )
    require(replacement_decoded == expected_decoded_bytes,
            "replacement decode does not derive from supplied PNG(s)/target template")
    validate_pants_descriptors(replacement_decoded)
    video = replacement_decoded[256:]
    clean_palette_independent = independent_png.parse_palette(
        video, pants.CLEAN_PALETTE_OFFSET
    )
    mud_palette_independent = independent_png.parse_palette(
        video, pants.MUD_PALETTE_OFFSET
    )
    decoded_indices: list[bytes] = []
    decoded_clean: list[bytes] = []
    decoded_mud: list[bytes] = []
    offset = 0
    for mip_width, mip_height in pants.MIP_DIMENSIONS:
        size = mip_width * mip_height
        indices = independent_png.independent_unswizzle(
            video[offset:offset + size], mip_width, mip_height
        )
        decoded_indices.append(indices)
        decoded_clean.append(independent_png.expand(indices, clean_palette_independent))
        decoded_mud.append(independent_png.expand(indices, mud_palette_independent))
        offset += size
    require(decoded_indices == index_levels and
            decoded_clean == [level.rgba for level in clean_expected] and
            decoded_mud == [level.rgba for level in mud_expected],
            "independent mip decode differs from deterministic reconstruction")

    encoded, compression_info = compress_vc_lz(
        expected_decoded_bytes,
        stream_tag=target.stream_tag,
        offset_bits=target.offset_bits,
        max_encoded_size=target.stored_size,
    )
    exact_span, rebuild_info = rebuild_compressed_chunk_fixed_span(
        source_span, expected_decoded_bytes
    )
    require(exact_span == replacement_span and
            replacement_metrics["consumed_bytes"] == len(encoded) and
            replacement_span[HEADER.size + len(encoded):] ==
                bytes(target.stored_size - len(encoded)),
            "replacement is not the deterministic target fixed-span rebuild")
    require(manifest.get("compression") == asdict(compression_info),
            "compression manifest differs from deterministic recompression")
    require(manifest.get("rebuild") == {
        **asdict(rebuild_info),
        "decoded_roundtrip_sha256": sha256_bytes(expected_decoded_bytes),
        "complete_span_sha256": sha256_bytes(replacement_span),
        "complete_span_size": target.span_size,
        "fixed_span_fit": True,
        "zero_padding_verified": True,
    }, "rebuild manifest differs from exact target span")

    expected_preview_rows: list[dict[str, object]] = []
    expected_names: set[str] = set()
    for role, levels in (("clean", decoded_clean), ("mud", decoded_mud)):
        for level_index, rgba in enumerate(levels):
            mip_width, mip_height = pants.MIP_DIMENSIONS[level_index]
            name = f"{role}_mip{level_index}_{mip_width}x{mip_height}.png"
            expected_names.add(name)
            require(name in preview_payloads and
                    legacy.decode_rgba_png(
                        preview_payloads[name], (mip_width, mip_height)
                    ) == (mip_width, mip_height, rgba),
                    f"preview differs from decoded target mip: {name}")
            expected_preview_rows.append({
                "role": role,
                "level": level_index,
                "width": mip_width,
                "height": mip_height,
                "rgba_sha256": sha256_bytes(rgba),
                "png_file": name,
                "png_sha256": sha256_bytes(preview_payloads[name]),
                "strictly_reparsed": True,
            })
    require(set(preview_payloads) == expected_names and
            manifest.get("previews") == expected_preview_rows,
            "preview file set/manifest rows mismatch")
    require(manifest.get("claims") == {
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
        "portme": "PORTME: separately audit any non-pants chunk or model layout before import.",
    }, "import scope/claims mismatch")
    outputs = manifest.get("outputs")
    require(isinstance(outputs, dict) and set(outputs) == {
        "span_file", "manifest_file", "preview_directory", "preview_file_count"
    } and outputs.get("preview_file_count") == 12,
            "import output provenance fields mismatch")
    if replacement_span_name is not None:
        require(outputs.get("span_file") == replacement_span_name,
                "replacement filename provenance mismatch")
    if import_manifest_name is not None:
        require(outputs.get("manifest_file") == import_manifest_name,
                "manifest filename provenance mismatch")
    if preview_directory_name is not None:
        require(outputs.get("preview_directory") == preview_directory_name,
                "preview-directory provenance mismatch")

    validated = ValidatedImport(
        selector=target.selector,
        logical_name=target.logical_name,
        outer_index=target.outer_index,
        span_sha256=sha256_bytes(replacement_span),
        decoded_sha256=sha256_bytes(replacement_decoded),
        import_manifest_sha256=sha256_bytes(import_manifest_payload),
        clean_png_sha256=clean_sha,
        mud_source_kind=str(mud_kind),
        mud_png_sha256=mud_sha,
        encoded_bytes=len(encoded),
        stored_size=target.stored_size,
        zero_padding_bytes=target.stored_size - len(encoded),
        template_overlap_scratch_bytes=target.overlap_scratch_bytes,
        template_exact_minimum_overlap_scratch_bytes=
            target.retail_exact_minimum_overlap_scratch_bytes,
        rebuilt_overlap_scratch_bytes=int(replacement_header[5]),
        rebuilt_exact_minimum_overlap_scratch_bytes=
            int(rebuild_info.exact_minimum_overlap_scratch_bytes),
        loader_in_place_end_guard=bool(rebuild_info.loader_in_place_end_guard),
        loader_in_place_alias_guard=bool(rebuild_info.loader_in_place_alias_guard),
        palette_entries=len(clean_palette),
        quantization_differing_pixels=int(quantization["differing_pixel_count"]),
        mip_count=6,
        preview_count=12,
        shared_indices=True,
    )
    return validated, {
        "validated": asdict(validated),
        "quantization": quantization,
        "mud_mode": mud_record,
        "compression": asdict(compression_info),
        "source_independent_decode": source_metrics,
        "replacement_independent_decode": replacement_metrics,
    }
