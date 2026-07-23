#!/usr/bin/env python3
"""All-target and representative changed-output tests for APF shoulders."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_shoulder_family_patch as family_patch  # noqa: E402
import apf_texture_patch as archive_patch  # noqa: E402


INDEX = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
SOURCE_PNG = WORKSPACE / "reports/assets/apf_uniform_samples/team00_bank0_shoulder_05_shoulder_color.png"
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
CONTROLLED_TARGETS = [5, 8, 23]
EXPECTED_BLOCK_COUNTS = [65536, 16384, 4096, 1024, 256, 64, 16, 4, 1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run(report_path: Path, full_copy: bool) -> None:
    source_before = sha256_file(INDEX)
    assert source_before == EXPECTED_VOLUME_SHA256
    catalog = json.loads(family_patch.CATALOG.read_text(encoding="utf-8"))
    assert hashlib.sha256(family_patch.CATALOG.read_bytes()).hexdigest() == family_patch.EXPECTED_CATALOG_SHA256
    targets = [family_patch.target_record(index) for index in range(24)]
    assert len({row["outer_table_index"] for row in targets}) == 24
    assert len({row["paired_normal_package"]["outer_table_index"] for row in targets}) == 24
    for invalid in (-1, 24):
        try:
            family_patch.target_record(invalid)
        except family_patch.ShoulderFamilyPatchError:
            pass
        else:
            raise AssertionError(f"invalid target {invalid} accepted")

    no_op = family_patch.build_patch(INDEX, SOURCE_PNG, 5)
    assert no_op.manifest["mode"] == "no_op"
    assert no_op.manifest["validation"]["entry_bit_exact"] is True
    assert hashlib.sha256(no_op.entry_bytes).hexdigest() == targets[5]["outer_allocation"]["sha256"]

    archive = apf_outer.parse_archive(INDEX)
    controlled = []
    copied_summary = None
    with tempfile.TemporaryDirectory(prefix="apf-shoulder-family-test-") as temporary:
        temp = Path(temporary)
        solid = temp / "rgba-magenta.png"
        Image.new("RGBA", (1024, 1024), (255, 0, 255, 255)).save(solid)
        results = {}
        for asset_index in CONTROLLED_TARGETS:
            result = family_patch.build_patch(INDEX, solid, asset_index)
            results[asset_index] = result
            row = targets[asset_index]
            manifest = result.manifest
            assert manifest["schema"] == "apf_shoulder_family_patch/v1"
            assert manifest["transport_schema"] == "apf_shoulder_color_transport/v1"
            assert manifest["mode"] == "patched"
            assert manifest["family_target"]["asset_index"] == asset_index
            assert manifest["family_target"]["paired_normal_package_edited"] is False
            assert len(result.entry_bytes) == row["outer_allocation"]["size"]
            assert [level["changed_bc3_blocks"]["count"] for level in manifest["levels"]] == EXPECTED_BLOCK_COUNTS
            assert all(
                level["decode_back_metrics"]["different_components"] == 0
                for level in manifest["levels"]
            )
            assert manifest["texture"]["inactive_padding_bit_exact"] is True
            assert manifest["iff"]["footer_bit_exact"] is True
            assert manifest["iff"]["dram_block_preserved"] is True
            assert manifest["iff"]["three_sibling_textures_preserved"] is True
            assert manifest["iff"]["allocation_slack_after"] >= 0
            assert manifest["binary_patch_manifest"]["contains_replacement_bytes"] is False
            controlled.append(
                {
                    "asset_index": asset_index,
                    "outer_table_index": row["outer_table_index"],
                    "paired_normal_outer_table_index": row["paired_normal_package"]["outer_table_index"],
                    "allocation_size": len(result.entry_bytes),
                    "retail_entry_sha256": row["outer_allocation"]["sha256"],
                    "patched_entry_sha256": hashlib.sha256(result.entry_bytes).hexdigest(),
                    "allocation_slack_after": manifest["iff"]["allocation_slack_after"],
                    "all_nine_levels_zero_error_decode_back": True,
                    "inactive_padding_bit_exact": True,
                    "footer_bit_exact": True,
                    "dram_block_preserved": True,
                    "three_sibling_textures_preserved": True,
                    "paired_normal_package_edited": False,
                }
            )

        try:
            archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                INDEX,
                INDEX,
                archive.entries[int(targets[23]["outer_table_index"])],
                results[23].entry_bytes,
            )
        except archive_patch.PatchError:
            source_output_refused = True
        else:
            source_output_refused = False
        assert source_output_refused
        existing = temp / "existing-0A"
        existing.write_bytes(b"sentinel")
        try:
            archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                INDEX,
                existing,
                archive.entries[int(targets[23]["outer_table_index"])],
                results[23].entry_bytes,
            )
        except archive_patch.PatchError:
            existing_refused = True
        else:
            existing_refused = False
        assert existing_refused and existing.read_bytes() == b"sentinel"

        if full_copy:
            copied_path = temp / "copied-game/0A"
            copied = archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                INDEX,
                copied_path,
                archive.entries[int(targets[23]["outer_table_index"])],
                results[23].entry_bytes,
            )
            assert copied["source_volume_sha256_before"] == EXPECTED_VOLUME_SHA256
            assert copied["source_volume_sha256_after"] == EXPECTED_VOLUME_SHA256
            assert copied["outside_replacement"]["source_and_output_match"] is True
            for pack in archive.packs[1:]:
                (copied_path.parent / pack.name).symlink_to(pack.path)
            reparsed = apf_outer.parse_archive(copied_path)
            entry = reparsed.entries[int(targets[23]["outer_table_index"])]
            normal_entry = reparsed.entries[
                int(targets[23]["paired_normal_package"]["outer_table_index"])
            ]
            with apf_inner.ArchiveReader(reparsed) as reader:
                record = apf_inner.parse_iff(reader, entry)
                entry_bytes = reader.read(entry, 0, entry.size)
                block_1 = apf_inner.decode_block(reader, record, 1, 1 << 30)
                normal_bytes = reader.read(normal_entry, 0, normal_entry.size)
            assert entry_bytes == results[23].entry_bytes
            texture = block_1[:0x160000]
            assert hashlib.sha256(texture).hexdigest() == results[23].manifest["texture"]["sha256_after"]
            assert hashlib.sha256(normal_bytes).hexdigest() == targets[23]["paired_normal_package"]["allocation_sha256"]
            copied_summary = {
                "asset_index": 23,
                "source_volume_sha256_before": copied["source_volume_sha256_before"],
                "source_volume_sha256_after": copied["source_volume_sha256_after"],
                "output_volume_sha256": copied["output_volume_sha256"],
                "outside_replacement": copied["outside_replacement"],
                "copied_archive_reparsed": True,
                "copied_entry_sha256": hashlib.sha256(entry_bytes).hexdigest(),
                "copied_texture_sha256": hashlib.sha256(texture).hexdigest(),
                "paired_normal_package_sha256": hashlib.sha256(normal_bytes).hexdigest(),
            }

    source_after = sha256_file(INDEX)
    assert source_after == source_before
    report = {
        "schema": "apf_shoulder_family_patch_roundtrip/v1",
        "catalog": {
            "schema": catalog["schema"],
            "sha256": family_patch.EXPECTED_CATALOG_SHA256,
            "target_count": 24,
            "paired_normal_count": 24,
            "all_targets_have_independent_retail_hash_pins": True,
        },
        "source": {
            "volume": str(INDEX.relative_to(WORKSPACE)),
            "sha256_before": source_before,
            "sha256_after": source_after,
            "modified": False,
        },
        "target_selection": {
            "accepted": list(range(24)),
            "rejected": [-1, 24],
            "unique_outer_entry_count": 24,
        },
        "no_op": {"asset_index": 5, "entry_bit_exact": True},
        "controlled_edit": {
            "description": "RGBA-exact magenta 1024x1024; contains no retail pixels",
            "replacement_pixels_embedded": False,
            "representative_asset_indices": CONTROLLED_TARGETS,
            "results": controlled,
        },
        "copied_volume": copied_summary,
        "safety": {
            "source_path_as_output_refused": True,
            "existing_output_refused": True,
            "fixed_allocation_gate_retained": True,
            "arbitrary_png_fit_guaranteed": False,
            "retail_source_modified": False,
            "replacement_bytes_embedded_in_report": False,
        },
        "conclusion": {
            "copy_only_all_24_target_cli_exposed": True,
            "per_entry_retail_hash_gate": True,
            "representative_changed_entries_reparsed": True,
            "copied_volume_roundtrip_proved": full_copy,
            "all_three_sibling_textures_preserved": True,
            "paired_normal_package_preserved": True,
            "team_bank_sharing_reported": True,
            "xenia_runtime_visibility_proved": False,
            "hardware_runtime_visibility_proved": False,
            "production_bc3_ready": False,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_SHOULDER_FAMILY_PATCH_TEST_PASS targets=24 controlled=3 "
        f"copied_volume={str(full_copy).lower()}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--full-copy", action="store_true")
    args = parser.parse_args()
    run(args.report, args.full_copy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
