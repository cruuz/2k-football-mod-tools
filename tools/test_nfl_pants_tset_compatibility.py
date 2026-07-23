#!/usr/bin/env python3
"""All-corpus, importer, and fail-closed tests for NFL 2K5 pants TSETs."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import tempfile

from nfl_outer import parse_archive
from nfl_scene_probe import read_entry_range
import nfl2k5_uniform_pants_png_workflow as workflow
from nfl_pants_tset_dynamic_validate import (
    DynamicValidationError,
    independent_decode_target,
    validate_dynamic_import,
)
import nfl_pants_tset_png_import as importer
from nfl_pants_tset_targets import (
    TargetError,
    load_report,
    normalize_selector,
    select_target,
    target_from_row,
)
import nfl_tset_png_import as legacy
from nfl_txtr import (
    HEADER,
    TxtrError,
    compress_vc_lz,
    encode_rgba_png,
    minimum_vc_lz_overlap_scratch,
    swizzle_2d,
)
import nfl_uniform_color_xiso_direct_patch as common


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INVENTORY = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
COMPATIBILITY = ROOT / "reports/assets/nfl2k5_pants_tset_compatibility.json"
FIXTURE = ROOT / "reports/assets/nfl2k5_lions_diagnostic_codex_mod.png"
FIXTURE_PNG_SHA256 = (
    "6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8"
)
FIXTURE_DECODED_SHA256 = (
    "bbd1905e3a625298eb24990cabeabb16ddc40c09755307a0fb737d8651fc1f61"
)
ENCODED_BYTES_BY_OFFSET_BITS = {11: 13689, 12: 22284, 13: 38506, 14: 63243}


def expect_failure(callback, exceptions: tuple[type[BaseException], ...],
                   label: str) -> None:
    try:
        callback()
    except exceptions:
        return
    raise AssertionError(f"{label} did not fail closed")


def fixture_decoded(system: bytes) -> tuple[bytes, dict[int, bytes]]:
    assert len(system) == 256
    width, height, rgba, digest = importer.read_rgba_png(FIXTURE)
    assert digest == FIXTURE_PNG_SHA256
    mips = importer.generate_mips(rgba, width, height)
    clean_palette, index_levels, quantization = legacy.quantize_levels(mips)
    assert quantization == {
        "input_unique_rgba_colors": 32,
        "palette_entries": 32,
        "total_squared_rgba_error": 0,
        "maximum_channel_error": 0,
        "differing_pixel_count": 0,
        "total_pixel_count": 174720,
    }
    mud_palette = legacy.derive_mud_palette(clean_palette, "darken_60")
    video = bytearray(importer.VIDEO_BYTES)
    offset = 0
    for level, indices in zip(mips, index_levels):
        encoded = swizzle_2d(indices, level.width, level.height, 1)
        video[offset:offset + len(encoded)] = encoded
        offset += len(encoded)
    assert offset == importer.INDEX_CHAIN_BYTES
    video[
        importer.CLEAN_PALETTE_OFFSET:
        importer.CLEAN_PALETTE_OFFSET + importer.PALETTE_BYTES
    ] = legacy.palette_bytes(clean_palette)
    video[
        importer.MUD_PALETTE_OFFSET:
        importer.MUD_PALETTE_OFFSET + importer.PALETTE_BYTES
    ] = legacy.palette_bytes(mud_palette)
    result = system + bytes(video)
    assert hashlib.sha256(result).hexdigest() == FIXTURE_DECODED_SHA256
    streams: dict[int, bytes] = {}
    for offset_bits in ENCODED_BYTES_BY_OFFSET_BITS:
        stream, _ = compress_vc_lz(
            result, stream_tag=0, offset_bits=offset_bits
        )
        assert len(stream) == ENCODED_BYTES_BY_OFFSET_BITS[offset_bits]
        streams[offset_bits] = stream
    return result, streams


def noise_fixture() -> bytes:
    colors = [
        ((index * 37) & 255, (index * 83) & 255,
         (index * 149) & 255, 255)
        for index in range(256)
    ]
    state = 0x243F6A88
    rgba = bytearray()
    for _ in range(importer.BASE_WIDTH * importer.BASE_HEIGHT):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        rgba.extend(colors[state >> 24])
    return encode_rgba_png(
        importer.BASE_WIDTH, importer.BASE_HEIGHT, bytes(rgba)
    )


def main() -> int:
    _, report, _ = load_report(COMPATIBILITY)
    summary = report["summary"]
    assert summary == {
        "package_count": 634,
        "pair_count": 317,
        "home_count": 317,
        "away_count": 317,
        "layout_class_count": 1,
        "allocation_class_count": 324,
        "compatible_package_count": 634,
        "incompatible_package_count": 0,
        "compatible_home_count": 317,
        "compatible_away_count": 317,
        "pack_counts": {"9": 13, "A": 207, "B": 304, "C": 110},
        "stored_size_minimum": 61328,
        "stored_size_maximum": 118880,
        "all_spans_single_pack_segment": True,
        "all_source_xiso_spans_match": True,
        "all_system_blocks_identical": True,
        "all_interpalette_gaps_zero": True,
        "retail_exact_alias_scratch_minimum": 0,
        "retail_exact_alias_scratch_maximum": 87,
        "all_retail_wrappers_cover_exact_alias_requirement": True,
    }
    targets = [target_from_row(report, row) for row in report["packages"]]
    assert len({target.selector for target in targets}) == 634
    assert len({target.chunk_offset for target in targets}) == 341
    assert len({target.stored_size for target in targets}) == 298
    assert len({(target.overlap_scratch_bytes, target.stored_size)
                for target in targets}) == 324
    assert Counter(target.overlap_scratch_bytes for target in targets) == {
        16: 392, 32: 140, 48: 67, 64: 23, 80: 11, 96: 1,
    }
    assert Counter(target.offset_bits for target in targets) == {
        11: 5, 12: 425, 13: 202, 14: 2,
    }
    assert len({target.stream_tag for target in targets}) == 52
    assert len({target.retail_exact_minimum_overlap_scratch_bytes
                for target in targets}) == 62
    assert min(target.retail_exact_minimum_overlap_scratch_bytes
               for target in targets) == 0
    assert max(target.retail_exact_minimum_overlap_scratch_bytes
               for target in targets) == 87
    assert normalize_selector("84", "home", 0) == ("84", "H", 0)
    for args in (("8", "H", 0), ("84", "X", 0), ("84", "H", -1)):
        expect_failure(
            lambda args=args: normalize_selector(*args),
            (TargetError,), f"invalid selector {args}",
        )

    archive = parse_archive(INDEX)
    first = targets[0]
    first_span = read_entry_range(
        archive, archive.entries[first.outer_index],
        first.chunk_offset, first.span_size,
    )
    first_decoded, _ = independent_decode_target(
        first_span[HEADER.size:], first
    )
    replacement_decoded, encoded_by_bits = fixture_decoded(first_decoded[:256])
    minimum_stored_by_bits: dict[int, int] = {}
    rebuilt_scratch: list[int] = []
    exact_scratch: list[int] = []

    for target in targets:
        source_span = read_entry_range(
            archive, archive.entries[target.outer_index],
            target.chunk_offset, target.span_size,
        )
        assert HEADER.unpack_from(source_span) == target.complete_header
        source_decoded, source_metrics = independent_decode_target(
            source_span[HEADER.size:], target
        )
        assert hashlib.sha256(source_decoded).hexdigest() == target.decoded_sha256
        assert source_metrics["consumed_bytes"] == target.lz_consumed_bytes
        source_stream = source_span[
            HEADER.size:HEADER.size + source_metrics["consumed_bytes"]
        ]
        source_exact = minimum_vc_lz_overlap_scratch(
            source_stream, target.stored_size, target.decoded_size
        )
        assert source_exact == target.retail_exact_minimum_overlap_scratch_bytes
        assert target.overlap_scratch_bytes >= source_exact

        encoded = bytearray(encoded_by_bits[target.offset_bits])
        struct.pack_into("<I", encoded, 4, target.stream_tag)
        encoded_bytes = bytes(encoded)
        assert len(encoded_bytes) <= target.stored_size
        padding = target.stored_size - len(encoded_bytes)
        exact = minimum_vc_lz_overlap_scratch(
            encoded_bytes, target.stored_size, target.decoded_size
        )
        required = (max(padding, exact) + 15) & ~15
        scratch = max(target.overlap_scratch_bytes, required)
        fields = list(target.complete_header)
        fields[5] = scratch
        replacement_span = HEADER.pack(*fields) + encoded_bytes + bytes(padding)
        roundtrip, metrics = independent_decode_target(
            replacement_span[HEADER.size:], target
        )
        assert roundtrip == replacement_decoded
        assert metrics["consumed_bytes"] == len(encoded_bytes)
        assert scratch >= padding and scratch >= exact and scratch % 16 == 0
        minimum_stored_by_bits[target.offset_bits] = min(
            target.stored_size,
            minimum_stored_by_bits.get(target.offset_bits, target.stored_size),
        )
        rebuilt_scratch.append(scratch)
        exact_scratch.append(exact)

    assert minimum_stored_by_bits == {
        11: 61680, 12: 61328, 13: 76400, 14: 118880,
    }
    assert min(exact_scratch) == 37890 and max(exact_scratch) == 76281
    assert min(rebuilt_scratch) == 37904 and max(rebuilt_scratch) == 76304
    assert all(rebuilt != target.overlap_scratch_bytes
               for rebuilt, target in zip(rebuilt_scratch, targets))

    BUILD.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="nfl-compatible-pants-test-", dir=BUILD
    ) as name:
        temporary = Path(name)
        *_, target = select_target("84", "H", 0, COMPATIBILITY)
        span = temporary / "replacement.bin"
        manifest = temporary / "import.json"
        previews = temporary / "previews"
        result = importer.run(
            INDEX, INVENTORY, COMPATIBILITY, target,
            FIXTURE, None, "darken_60", span, manifest, previews,
        )
        source_span = read_entry_range(
            archive, archive.entries[target.outer_index],
            target.chunk_offset, target.span_size,
        )
        validated, evidence = validate_dynamic_import(
            target=target,
            compatibility_path=COMPATIBILITY,
            source_span=source_span,
            replacement_span=span.read_bytes(),
            import_manifest_payload=manifest.read_bytes(),
            clean_png_name=FIXTURE.name,
            clean_png_payload=FIXTURE.read_bytes(),
            mud_png_name=None,
            mud_png_payload=None,
            preview_payloads={
                child.name: child.read_bytes() for child in previews.iterdir()
            },
            replacement_span_name=span.name,
            import_manifest_name=manifest.name,
            preview_directory_name=previews.name,
        )
        assert validated.selector == "84H0"
        assert validated.encoded_bytes == 22284
        assert validated.preview_count == 12 and validated.mip_count == 6
        assert validated.template_exact_minimum_overlap_scratch_bytes == 23
        assert validated.rebuilt_exact_minimum_overlap_scratch_bytes == 39033
        assert evidence["validated"]["loader_in_place_alias_guard"] is True
        assert result["layout"]["interpalette_gap_bytes"] == 0

        forged = json.loads(manifest.read_bytes())
        forged["target"]["chunk_offset"] += 16
        forged_payload = (
            json.dumps(forged, indent=2, sort_keys=True) + "\n"
        ).encode()
        expect_failure(
            lambda: validate_dynamic_import(
                target=target,
                compatibility_path=COMPATIBILITY,
                source_span=source_span,
                replacement_span=span.read_bytes(),
                import_manifest_payload=forged_payload,
                clean_png_name=FIXTURE.name,
                clean_png_payload=FIXTURE.read_bytes(),
                mud_png_name=None,
                mud_png_payload=None,
                preview_payloads={
                    child.name: child.read_bytes()
                    for child in previews.iterdir()
                },
            ),
            (DynamicValidationError,), "forged target manifest",
        )

        noise = temporary / "incompressible.png"
        noise.write_bytes(noise_fixture())
        expect_failure(
            lambda: importer.run(
                INDEX, INVENTORY, COMPATIBILITY, target,
                noise, None, "identity",
                temporary / "oversize.bin", temporary / "oversize.json",
                temporary / "oversize-previews",
            ),
            (TxtrError, importer.ImportError), "smallest allocation overflow",
        )
        assert not (temporary / "oversize.bin").exists()
        assert not (temporary / "oversize.json").exists()
        assert not (temporary / "oversize-previews").exists()

        symlink_report = temporary / "compatibility-link.json"
        symlink_report.symlink_to(COMPATIBILITY)
        expect_failure(
            lambda: select_target("84", "H", 0, symlink_report),
            (TargetError,), "symlink compatibility report",
        )
        forged_report = temporary / "forged-compatibility.json"
        damaged = bytearray(COMPATIBILITY.read_bytes())
        damaged[-2] ^= 1
        forged_report.write_bytes(damaged)
        expect_failure(
            lambda: select_target("84", "H", 0, forged_report),
            (TargetError,), "forged compatibility report",
        )

        sentinel = temporary / "existing-output.iso"
        sentinel.write_bytes(b"DO NOT OVERWRITE")
        before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        expect_failure(
            lambda: workflow.run(
                source_xiso=temporary / "not-needed.iso",
                compatibility_path=COMPATIBILITY,
                target=target,
                clean_png=FIXTURE,
                mud_png=None,
                mud_mode="identity",
                output_xiso=sentinel,
                manifest_path=temporary / "unused.json",
                preview_dir=temporary / "unused-previews",
            ),
            (common.PatchError,), "workflow O_EXCL preflight",
        )
        assert hashlib.sha256(sentinel.read_bytes()).hexdigest() == before

    print(
        "NFL_PANTS_TSET_COMPATIBILITY_TESTS_PASS packages=634 pairs=317 "
        "layouts=1 allocations=324 compatible=634 offsets=341 stored_classes=298 "
        "fixture_all_634=true smallest=84H0 overflow_refused=true "
        "forged_rejected=true symlink_refused=true o_excl=true "
        "v3_loader_alias_guard=true runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
