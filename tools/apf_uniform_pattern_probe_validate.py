#!/usr/bin/env python3
"""Independently validate the prepared APF outer-875 pattern probe."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

import apf_inner
import apf_outer
import apf_texture_patch as archive_patch
import apf_uniform_mip_patch as uniform_patch
import apf_xenos_mip_layout as xenos_mips


EXPECTED_SOURCE_0A_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)
EXPECTED_SOURCE_XEX_SHA256 = (
    "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
)
EXPECTED_ENTRY_SHA256 = uniform_patch.EXPECTED_ENTRY_SHA256
EXPECTED_TEXTURE_SHA256 = uniform_patch.EXPECTED_TEXTURE_SHA256
EXPECTED_RGBA_SHA256 = (
    "ccf1e04695f19f274c489faf62bd1e57f018b4aba96f9795dbac4f25d6a0362d"
)
EXPECTED_PNG_SHA256 = (
    "fbfb1b9736db8f87bb8baf7e304f13aab1c61b68e356e72879791ebf5e9b93e5"
)
RED = (255, 0, 0, 255)
CYAN = (0, 255, 255, 255)
ALPHA64 = (0, 255, 255, 64)


class ValidationError(ValueError):
    """Raised when any prepared-probe invariant fails."""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()


def _hash_tree(root: Path) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        relative = path.relative_to(root).as_posix()
        result[relative] = {
            "size": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
    return result


def validate(
    source_index: Path,
    fixture_png: Path,
    fixture_manifest_path: Path,
    writer_manifest_path: Path,
    patched_entry_path: Path,
    patched_volume_path: Path,
    report_path: Path,
) -> None:
    paths = (
        source_index,
        fixture_png,
        fixture_manifest_path,
        writer_manifest_path,
        patched_entry_path,
        patched_volume_path,
    )
    _require(all(path.is_file() for path in paths), "one or more required inputs are absent")
    _require(not report_path.exists(), "refusing an existing validation report")
    _require(report_path.parent.is_dir(), "validation report parent is absent")

    source_game = source_index.parent
    patched_game = patched_volume_path.parent
    archive = apf_outer.parse_archive(source_index)
    _require(len(archive.entries) > uniform_patch.ENTRY_INDEX, "outer entry 875 is absent")
    entry = archive.entries[uniform_patch.ENTRY_INDEX]
    _require(len(entry.segments) == 1, "outer entry 875 is no longer contiguous")
    segment = entry.segments[0]
    _require(segment.pack_name == "0A", "outer entry 875 is no longer in volume 0A")

    source_0a_sha = _sha256_file(source_index)
    source_xex_sha = _sha256_file(source_game / "default.xex")
    _require(source_0a_sha == EXPECTED_SOURCE_0A_SHA256, "retail source 0A hash drifted")
    _require(source_xex_sha == EXPECTED_SOURCE_XEX_SHA256, "retail source XEX hash drifted")

    with apf_inner.ArchiveReader(archive) as source_reader:
        source_entry = source_reader.read(entry, 0, entry.size)
    _require(_sha256_bytes(source_entry) == EXPECTED_ENTRY_SHA256, "source entry hash drifted")

    png_data = fixture_png.read_bytes()
    with Image.open(fixture_png) as image:
        image.load()
        _require(image.size == (1024, 1024), "fixture dimensions are not 1024x1024")
        _require(image.mode == "RGBA", "fixture file is not stored as RGBA")
        base = image.copy()
    base_rgba = base.tobytes()
    _require(_sha256_bytes(png_data) == EXPECTED_PNG_SHA256, "fixture PNG hash drifted")
    _require(_sha256_bytes(base_rgba) == EXPECTED_RGBA_SHA256, "fixture RGBA hash drifted")

    fixture_manifest = json.loads(fixture_manifest_path.read_text(encoding="utf-8"))
    writer_manifest = json.loads(writer_manifest_path.read_text(encoding="utf-8"))
    _require(fixture_manifest["schema"] == "apf_uniform_pattern_probe_fixture/v1", "fixture schema drifted")
    _require(fixture_manifest["geometry"]["symbolic_rows"] == ["RRRC", "RCCC", "RRCC", "RCCA"], "symbolic orientation changed")
    _require(fixture_manifest["input"]["rgba_sha256"] == EXPECTED_RGBA_SHA256, "fixture manifest RGBA hash differs")
    _require(fixture_manifest["input"]["png_sha256"] == EXPECTED_PNG_SHA256, "fixture manifest PNG hash differs")
    _require(fixture_manifest["mips"]["level_8_single_bc3_block_encode_decode_exact"] is True, "fixture alpha proof is absent")

    _require(writer_manifest["schema"] == uniform_patch.SCHEMA, "writer schema drifted")
    _require(writer_manifest["mode"] == "patched", "writer did not take the patched path")
    _require(writer_manifest["source"]["entry_sha256"] == EXPECTED_ENTRY_SHA256, "writer source entry differs")
    _require(writer_manifest["source"]["texture_sha256"] == EXPECTED_TEXTURE_SHA256, "writer source texture differs")
    _require(writer_manifest["source"]["png_rgba_sha256"] == EXPECTED_RGBA_SHA256, "writer used another PNG")

    patched_entry = patched_entry_path.read_bytes()
    patched_entry_sha = _sha256_bytes(patched_entry)
    _require(len(patched_entry) == entry.size == 32768, "patched entry is not the fixed allocation size")
    _require(patched_entry_sha == writer_manifest["output_entry"]["sha256"], "patched entry hash differs from writer manifest")
    _require(patched_entry_sha == writer_manifest["copied_volume"]["replacement_read_back_sha256"], "copied-volume entry differs from standalone entry")

    memory_reader = archive_patch.BytesReader(patched_entry)
    record = apf_inner.parse_iff(memory_reader, entry)
    blocks = [
        apf_inner.decode_block(memory_reader, record, index, 1 << 30)
        for index in range(record.block_count)
    ]
    _require(record.file_count == 1 and record.block_count == 2, "patched IFF structure drifted")
    target = record.files[0]
    _require(target.name == "jersey_color" and target.type_name == "TXTR", "patched target identity drifted")
    _require(len(target.parts) == 2, "patched TXTR does not have DRAM/VRAM parts")
    dram_part, texture_part = target.parts
    dram = blocks[dram_part.block_index][dram_part.offset : dram_part.offset + dram_part.length]
    texture = blocks[texture_part.block_index][texture_part.offset : texture_part.offset + texture_part.length]
    metadata = apf_inner.parse_txtr_metadata(dram)
    uniform_patch._strict_descriptor(metadata)  # type: ignore[attr-defined]
    locations = xenos_mips.derive_layout(metadata)
    _require(xenos_mips.transport_roundtrip(texture, locations) == texture, "patched tiled transport is not bit exact")

    level_reports: list[dict[str, object]] = []
    fixture_levels = fixture_manifest["mips"]["levels"]
    writer_levels = writer_manifest["levels"]
    for location, fixture_level, writer_level in zip(locations, fixture_levels, writer_levels):
        wanted = base.resize((location.width, location.height), Image.Resampling.BOX).tobytes()
        linear = xenos_mips.extract_linear_bc3(texture, location)
        decoded = uniform_patch._decode_linear_bc3(linear, location)  # type: ignore[attr-defined]
        _require(decoded == wanted, f"mip {location.level} decode differs from the fixture")
        wanted_sha = _sha256_bytes(wanted)
        _require(fixture_level["rgba_sha256"] == wanted_sha, f"fixture mip {location.level} hash differs")
        _require(writer_level["wanted_rgba_sha256"] == wanted_sha, f"writer wanted mip {location.level} hash differs")
        _require(writer_level["decoded_rgba_sha256_after"] == wanted_sha, f"writer decoded mip {location.level} hash differs")
        _require(writer_level["decode_back_metrics"]["different_components"] == 0, f"writer reports mip {location.level} loss")

        counts = Counter(
            tuple(decoded[offset : offset + 4])
            for offset in range(0, len(decoded), 4)
        )
        total = location.width * location.height
        expected_counts = Counter({RED: total * 7 // 16, CYAN: total * 8 // 16, ALPHA64: total // 16})
        _require(counts == expected_counts, f"mip {location.level} orientation/alpha counts differ")
        alpha64_pixels = sum(1 for offset in range(3, len(decoded), 4) if decoded[offset] == 64)
        non_endpoint_alpha = sum(1 for offset in range(3, len(decoded), 4) if decoded[offset] not in (64, 255))
        _require(alpha64_pixels == total // 16 and non_endpoint_alpha == 0, f"mip {location.level} alpha endpoints differ")
        level_reports.append(
            {
                "level": location.level,
                "size": [location.width, location.height],
                "rgba_sha256": wanted_sha,
                "decoded_exact": True,
                "pixel_counts": {
                    "opaque_red": counts[RED],
                    "opaque_cyan": counts[CYAN],
                    "alpha64_cyan": counts[ALPHA64],
                },
                "non_endpoint_alpha_pixels": non_endpoint_alpha,
            }
        )

    required_writer_flags = (
        "all_nine_levels_regenerated",
        "all_nine_levels_decoded_back",
        "all_nine_levels_transport_bit_exact",
        "inactive_mip_padding_preserved",
        "h7a_decode_encode_decode_exact",
        "rebuilt_iff_reparsed",
        "footer_bit_exact",
        "unrelated_dram_part_preserved",
        "fixed_outer_allocation",
        "source_opened_read_only",
    )
    _require(all(writer_manifest["validation"][key] is True for key in required_writer_flags), "one or more writer safety flags failed")
    _require(writer_manifest["iff"]["allocation_slack_after"] > 0, "rebuilt IFF has no allocation slack")

    patched_0a_sha = _sha256_file(patched_volume_path)
    _require(patched_0a_sha == writer_manifest["copied_volume"]["output_volume_sha256"], "patched 0A hash differs")
    _require(_sha256_file(source_index) == EXPECTED_SOURCE_0A_SHA256, "source 0A changed during validation")
    replacement_sha = archive_patch.sha256_range(patched_volume_path, segment.pack_offset, entry.size)
    _require(replacement_sha == patched_entry_sha, "patched 0A replacement range differs")
    prefix_size = segment.pack_offset
    suffix_offset = segment.pack_offset + entry.size
    suffix_size = source_index.stat().st_size - suffix_offset
    prefix_sha = archive_patch.sha256_range(source_index, 0, prefix_size)
    suffix_sha = archive_patch.sha256_range(source_index, suffix_offset, suffix_size)
    _require(prefix_sha == archive_patch.sha256_range(patched_volume_path, 0, prefix_size), "patched 0A prefix changed")
    _require(suffix_sha == archive_patch.sha256_range(patched_volume_path, suffix_offset, suffix_size), "patched 0A suffix changed")

    source_tree = _hash_tree(source_game)
    patched_tree = _hash_tree(patched_game)
    _require(source_tree.keys() == patched_tree.keys(), "copied game file set differs")
    unrelated = [name for name in source_tree if name != "0A"]
    _require(all(source_tree[name] == patched_tree[name] for name in unrelated), "an unrelated copied-game file differs")
    _require(source_tree["0A"]["sha256"] == EXPECTED_SOURCE_0A_SHA256, "tree source 0A hash differs")
    _require(patched_tree["0A"]["sha256"] == patched_0a_sha, "tree patched 0A hash differs")

    report = {
        "schema": "apf_uniform_pattern_probe_validation/v1",
        "status": "PASS",
        "runtime": {
            "emulator_launched_by_preparation": False,
            "controller_constraint": {
                "status": "VIOLATED_TRANSIENT_HOTPLUG_ONLY",
                "cause": (
                    "The helper was invoked once with --help, but it does not parse "
                    "arguments; it created /dev/input/event20 and immediately closed "
                    "on stdin EOF."
                ),
                "tap_or_button_events_sent": False,
                "device_persisted": False,
                "emulator_launched": False,
            },
            "title_executed": False,
            "runtime_uv_alpha_mip_result": "not tested; prepared for a later matched run",
        },
        "fixture": {
            "png": str(fixture_png),
            "png_sha256": EXPECTED_PNG_SHA256,
            "rgba_sha256": EXPECTED_RGBA_SHA256,
            "symbolic_rows": ["RRRC", "RCCC", "RRCC", "RCCA"],
            "orientation_cue": "large red F on opaque cyan",
            "alpha_sentinel": "bottom-right 256x256 cyan tile at alpha 64; all other pixels alpha 255",
            "levels": level_reports,
        },
        "source": {
            "game_dir": str(source_game),
            "0A_sha256_before_and_after": EXPECTED_SOURCE_0A_SHA256,
            "default_xex_sha256": EXPECTED_SOURCE_XEX_SHA256,
            "entry_875_sha256": EXPECTED_ENTRY_SHA256,
            "texture_sha256": EXPECTED_TEXTURE_SHA256,
        },
        "prepared_copy": {
            "game_dir": str(patched_game),
            "entry_path": str(patched_entry_path),
            "entry_sha256": patched_entry_sha,
            "0A_sha256": patched_0a_sha,
            "entry_offset": segment.pack_offset,
            "entry_size": entry.size,
            "prefix_sha256": prefix_sha,
            "suffix_sha256": suffix_sha,
            "unrelated_files_bit_exact": True,
            "unrelated_file_count": len(unrelated),
            "tree": patched_tree,
        },
        "writer": {
            "manifest": str(writer_manifest_path),
            "manifest_sha256": _sha256_file(writer_manifest_path),
            "fixture_manifest_sha256": _sha256_file(fixture_manifest_path),
            "texture_sha256_after": _sha256_bytes(texture),
            "file_length_after": writer_manifest["iff"]["file_length_after"],
            "allocation_slack_after": writer_manifest["iff"]["allocation_slack_after"],
            "all_nine_mips_decode_exact": True,
            "alpha64_survives_every_mip_exactly": True,
            "inactive_padding_bit_exact": True,
            "h7a_decode_encode_decode_exact": True,
            "fixed_allocation_fit": True,
        },
        "claim_boundary": (
            "The asymmetric two-color/alpha64 pattern is exact through PNG, all nine "
            "BOX mips, BC3 encode/decode, Xenos tiled placement, packed-tail placement, "
            "H7A, rebuilt IFF, and the copied 0A. No runtime was executed, so UV "
            "orientation, material alpha behavior, selected mip behavior, and hardware "
            "fidelity remain unproved until a matched capture."
        ),
    }
    _write_new(report_path, (json.dumps(report, indent=2) + "\n").encode("utf-8"))
    print(
        "APF_UNIFORM_PATTERN_PROBE_VALIDATION_PASS "
        f"mips={len(level_reports)} alpha64_base={level_reports[0]['pixel_counts']['alpha64_cyan']} "  # type: ignore[index]
        f"slack={report['writer']['allocation_slack_after']} runtime=false"  # type: ignore[index]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-index", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--fixture-manifest", required=True, type=Path)
    parser.add_argument("--writer-manifest", required=True, type=Path)
    parser.add_argument("--patched-entry", required=True, type=Path)
    parser.add_argument("--patched-volume", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate(
            args.source_index.expanduser(),
            args.fixture.expanduser(),
            args.fixture_manifest.expanduser(),
            args.writer_manifest.expanduser(),
            args.patched_entry.expanduser(),
            args.patched_volume.expanduser(),
            args.report.expanduser(),
        )
    except (ValidationError, OSError, KeyError, ValueError, apf_outer.FormatError, apf_inner.FormatError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
