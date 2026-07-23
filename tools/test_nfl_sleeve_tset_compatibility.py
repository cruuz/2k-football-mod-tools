#!/usr/bin/env python3
"""All-corpus, importer, and fail-closed tests for NFL 2K5 sleeve TSETs."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import tempfile

from nfl_outer import parse_archive
from nfl_scene_probe import read_entry_range
import nfl2k5_uniform_sleeve_png_workflow as workflow
from nfl_sleeve_tset_dynamic_validate import (
    DynamicValidationError,
    independent_decode_target,
    validate_dynamic_import,
)
import nfl_sleeve_tset_png_import as importer
from nfl_sleeve_tset_targets import (
    TargetError,
    load_report,
    normalize_selector,
    select_target,
    target_from_row,
)
import nfl_tset_png_import as legacy
from nfl_txtr import HEADER, TxtrError, encode_rgba_png, \
    rebuild_compressed_chunk_fixed_span, swizzle_2d
import nfl_uniform_color_xiso_direct_patch as common


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
INVENTORY = ROOT / "reports/assets/nfl2k5_resource_chunks_v2.json"
COMPATIBILITY = ROOT / "reports/assets/nfl2k5_sleeve_tset_compatibility.json"
SYNTHETIC_DECODED_SHA256 = \
    "50c063abb8a8c04bc9ba0b15dc1af958d3493c9f33fbd4a358d1e1ecd8f3fc78"


def expect_failure(callback, exceptions: tuple[type[BaseException], ...], label: str) \
        -> None:
    try:
        callback()
    except exceptions:
        return
    raise AssertionError(f"{label} did not fail closed")


def user_fixture() -> bytes:
    colors = (
        (14, 32, 100, 255), (255, 170, 5, 255),
        (230, 235, 240, 255), (40, 180, 90, 255),
    )
    rgba = b"".join(
        bytes(colors[((x // 16) ^ (y // 16)) & 3])
        for y in range(128) for x in range(128)
    )
    return encode_rgba_png(128, 128, rgba)


def noise_fixture() -> bytes:
    state = 0x243F6A88
    rgba = bytearray()
    for _ in range(128 * 128):
        channels = []
        for _channel in range(3):
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            channels.append(state >> 24)
        rgba.extend((*channels, 255))
    return encode_rgba_png(128, 128, bytes(rgba))


def synthetic_decoded(system: bytes) -> bytes:
    assert len(system) == 256
    video = bytearray(importer.VIDEO_BYTES)
    offset = 0
    for level, (width, height) in enumerate(importer.MIP_DIMENSIONS):
        shift = max(0, 3 - level)
        indices = bytes(
            1 + (((x >> shift) ^ (y >> shift) ^ level) & 15)
            for y in range(height) for x in range(width)
        )
        video[offset:offset + len(indices)] = swizzle_2d(
            indices, width, height, 1
        )
        offset += len(indices)
    assert offset == importer.INDEX_CHAIN_BYTES
    clean = [(0, 0, 0, 0)] + [
        ((37 * index) & 255, (83 * index) & 255,
         (149 * index) & 255, 255)
        for index in range(1, 17)
    ]
    mud = [(0, 0, 0, 0)] + [
        (red * 3 // 5, green * 3 // 5, blue * 3 // 5, alpha)
        for red, green, blue, alpha in clean[1:]
    ]
    video[
        importer.CLEAN_PALETTE_OFFSET:
        importer.CLEAN_PALETTE_OFFSET + importer.PALETTE_BYTES
    ] = legacy.palette_bytes(clean)
    video[
        importer.MUD_PALETTE_OFFSET:
        importer.MUD_PALETTE_OFFSET + importer.PALETTE_BYTES
    ] = legacy.palette_bytes(mud)
    result = system + bytes(video)
    assert hashlib.sha256(result).hexdigest() == SYNTHETIC_DECODED_SHA256
    return result


def main() -> int:
    _, report, _ = load_report(COMPATIBILITY)
    assert report["summary"] == {
        "package_count": 634,
        "pair_count": 317,
        "home_count": 317,
        "away_count": 317,
        "layout_class_count": 1,
        "allocation_class_count": 275,
        "compatible_package_count": 634,
        "incompatible_package_count": 0,
        "compatible_home_count": 317,
        "compatible_away_count": 317,
        "pack_counts": {"9": 13, "A": 207, "B": 304, "C": 110},
        "stored_size_minimum": 5648,
        "stored_size_maximum": 20496,
        "all_spans_single_pack_segment": True,
        "all_source_xiso_spans_match": True,
        "all_system_blocks_identical": True,
        "all_interpalette_gaps_zero": True,
    }
    targets = [target_from_row(report, row) for row in report["packages"]]
    assert len({target.selector for target in targets}) == 634
    assert len({target.chunk_offset for target in targets}) == 466
    assert len({target.stored_size for target in targets}) == 193
    assert len({(target.overlap_scratch_bytes, target.stored_size)
                for target in targets}) == 275
    assert Counter(target.overlap_scratch_bytes for target in targets) == {
        16: 411, 32: 84, 48: 56, 64: 49,
        80: 23, 96: 8, 112: 2, 128: 1,
    }
    assert Counter(target.offset_bits for target in targets) == {
        10: 4, 11: 491, 12: 136, 13: 3,
    }
    assert len({target.stream_tag for target in targets}) == 67
    assert {target.layout_signature_sha256 for target in targets} == {
        "32ee17c87175240bfff761e2046232c2e7a0066f05c85385456fdff8b868af31"
    }
    assert normalize_selector("09", "home", 0) == ("09", "H", 0)
    for args in (("9", "H", 0), ("09", "X", 0), ("09", "H", -1)):
        expect_failure(
            lambda args=args: normalize_selector(*args),
            (TargetError,), f"invalid selector {args}",
        )

    archive = parse_archive(INDEX)
    encoded_by_bits: dict[int, set[int]] = defaultdict(set)
    minimum_stored_by_bits: dict[int, int] = {}
    rebuilt_scratch: list[int] = []
    control_span_sha = None
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
        replacement_decoded = synthetic_decoded(source_decoded[:256])
        replacement_span, info = rebuild_compressed_chunk_fixed_span(
            source_span, replacement_decoded
        )
        replacement_roundtrip, replacement_metrics = independent_decode_target(
            replacement_span[HEADER.size:], target
        )
        assert replacement_roundtrip == replacement_decoded
        assert replacement_metrics["consumed_bytes"] == info.recompressed_bytes
        assert len(replacement_span) == target.span_size
        rebuilt_header = HEADER.unpack_from(replacement_span)
        assert rebuilt_header[:5] == target.complete_header[:5]
        assert rebuilt_header[6:] == target.complete_header[6:]
        assert rebuilt_header[5] == info.rebuilt_overlap_scratch_bytes
        assert info.overlap_scratch_changed is True
        assert info.loader_in_place_end_guard is True
        assert info.loader_in_place_alias_guard is True
        assert replacement_span[HEADER.size + info.recompressed_bytes:] == \
            bytes(info.zero_padding_bytes)
        encoded_by_bits[target.offset_bits].add(info.recompressed_bytes)
        minimum_stored_by_bits[target.offset_bits] = min(
            target.stored_size,
            minimum_stored_by_bits.get(target.offset_bits, target.stored_size),
        )
        rebuilt_scratch.append(info.rebuilt_overlap_scratch_bytes)
        if target.selector == "09H0":
            assert target.overlap_scratch_bytes == 64
            assert info.recompressed_bytes == 3447
            assert info.zero_padding_bytes == 8057
            assert info.exact_minimum_overlap_scratch_bytes == 8056
            assert info.rebuilt_overlap_scratch_bytes == 8064
            assert target.overlap_scratch_bytes < \
                info.exact_minimum_overlap_scratch_bytes
            control_span_sha = hashlib.sha256(replacement_span).hexdigest()

    assert encoded_by_bits == {
        10: {1950}, 11: {2497}, 12: {3447}, 13: {5577},
    }
    assert minimum_stored_by_bits == {
        10: 8720, 11: 5648, 12: 8240, 13: 11024,
    }
    assert min(rebuilt_scratch) == 3152 and max(rebuilt_scratch) == 14928
    assert control_span_sha == \
        "ed1a23532a3e3cfa273431d72777aeeb381e9ff6244ac944624e15951b1f9f96"

    fixture_payload = user_fixture()
    with tempfile.TemporaryDirectory(prefix="nfl-compatible-sleeve-test-") as name:
        temporary = Path(name)
        clean = temporary / "user_sleeve.png"
        clean.write_bytes(fixture_payload)
        strict_mud = temporary / "strict_identity_mud.png"
        strict_mud.write_bytes(fixture_payload)
        cases = (
            ("06", "H", 2, None, "darken_60", "smallest"),
            ("27", "A", 0, strict_mud, "identity", "away"),
        )
        for code, side, variant, mud, mode, stem in cases:
            *_, target = select_target(code, side, variant, COMPATIBILITY)
            span = temporary / f"{stem}.bin"
            manifest = temporary / f"{stem}.json"
            previews = temporary / f"{stem}-previews"
            result = importer.run(
                INDEX, INVENTORY, COMPATIBILITY, target,
                clean, mud, mode, span, manifest, previews,
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
                clean_png_name=clean.name,
                clean_png_payload=clean.read_bytes(),
                mud_png_name=mud.name if mud else None,
                mud_png_payload=mud.read_bytes() if mud else None,
                preview_payloads={
                    child.name: child.read_bytes() for child in previews.iterdir()
                },
                replacement_span_name=span.name,
                import_manifest_name=manifest.name,
                preview_directory_name=previews.name,
            )
            assert validated.selector == target.selector
            assert evidence["validated"]["preview_count"] == 10
            assert validated.loader_in_place_end_guard is True
            assert validated.loader_in_place_alias_guard is True
            assert result["layout"]["interpalette_gap_zero_and_preserved"] is True

            forged = json.loads(manifest.read_bytes())
            forged["target"]["chunk_offset"] += 16
            forged_payload = (
                json.dumps(forged, indent=2, sort_keys=True) + "\n"
            ).encode()
            expect_failure(
                lambda target=target, source_span=source_span, span=span,
                       forged_payload=forged_payload, mud=mud, previews=previews:
                    validate_dynamic_import(
                        target=target,
                        compatibility_path=COMPATIBILITY,
                        source_span=source_span,
                        replacement_span=span.read_bytes(),
                        import_manifest_payload=forged_payload,
                        clean_png_name=clean.name,
                        clean_png_payload=clean.read_bytes(),
                        mud_png_name=mud.name if mud else None,
                        mud_png_payload=mud.read_bytes() if mud else None,
                        preview_payloads={
                            child.name: child.read_bytes()
                            for child in previews.iterdir()
                        },
                    ),
                (DynamicValidationError,), f"forged target {target.selector}",
            )

        noise = temporary / "incompressible.png"
        noise.write_bytes(noise_fixture())
        *_, smallest = select_target("06", "H", 2, COMPATIBILITY)
        expect_failure(
            lambda: importer.run(
                INDEX, INVENTORY, COMPATIBILITY, smallest,
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
            lambda: select_target("09", "H", 0, symlink_report),
            (TargetError,), "symlink compatibility report",
        )
        forged_report = temporary / "forged-compatibility.json"
        damaged = bytearray(COMPATIBILITY.read_bytes())
        damaged[-2] ^= 1
        forged_report.write_bytes(damaged)
        expect_failure(
            lambda: select_target("09", "H", 0, forged_report),
            (TargetError,), "forged compatibility report",
        )

        sentinel = temporary / "existing-output.iso"
        sentinel.write_bytes(b"DO NOT OVERWRITE")
        before = hashlib.sha256(sentinel.read_bytes()).hexdigest()
        *_, target = select_target("09", "H", 0, COMPATIBILITY)
        expect_failure(
            lambda: workflow.run(
                source_xiso=temporary / "not-needed.iso",
                compatibility_path=COMPATIBILITY,
                target=target,
                clean_png=clean,
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
        "NFL_SLEEVE_TSET_COMPATIBILITY_TESTS_PASS packages=634 pairs=317 "
        "layouts=1 allocations=275 compatible=634 offsets=466 stored_classes=193 "
        "fixture_all_634=true smallest=06H2 strict_mud=true overflow_refused=true "
        "forged_rejected=true symlink_refused=true o_excl=true "
        "v3_loader_alias_guard=true runtime=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
