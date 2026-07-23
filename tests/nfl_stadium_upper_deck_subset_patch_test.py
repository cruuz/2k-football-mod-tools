#!/usr/bin/env python3
"""Full copied-volume proof for the NFL ``upper_deck`` subset writer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import nfl_stadium_upper_deck_subset_patch as writer  # noqa: E402
import nfl_stadium_upper_deck_subset_verify as verifier  # noqa: E402


INDEX = ROOT / "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
CATALOG = ROOT / "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json"
BOUNDARY = ROOT / "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json"
RECIPE_SCHEMA = ROOT / "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json"
PREFIX8 = ROOT / "reports/asset_samples/nfl_scne/stadium_upper_deck_prefix8_source_subset_recipe.v1.json"
NONIDENTITY4 = ROOT / "reports/asset_samples/nfl_scne/stadium_upper_deck_nonidentity4_source_subset_recipe.v1.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def contains_private_payload(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key in {"source_vertex_ids", "positions", "retail_records", "replacement_bytes"}
            or contains_private_payload(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_private_payload(item) for item in value)
    return isinstance(value, (bytes, bytearray))


def verify_case(output: Path, recipe: Path | None, identity_noop: bool) -> tuple[dict, dict]:
    manifest = writer.patch(
        INDEX, recipe, identity_noop, output, CATALOG, BOUNDARY, RECIPE_SCHEMA
    )
    report = verifier.verify(
        INDEX, BOUNDARY, CATALOG, RECIPE_SCHEMA, output, recipe,
        identity_noop=identity_noop,
    )
    assert manifest["mode"] == report["mode"]
    assert manifest["output"]["volume_sha256"] == report["output"]["volume_sha256"]
    assert not contains_private_payload(manifest)
    assert not contains_private_payload(report)
    return manifest, report


def run(report_path: Path) -> None:
    source_pack = INDEX.parent / "9"
    index_before = file_sha256(INDEX)
    pack_before = file_sha256(source_pack)
    assert index_before == writer.base.INDEX_SHA256 == verifier.INDEX_SHA256
    assert pack_before == writer.base.PACK_SHA256 == verifier.PACK_SHA256

    authorities = writer.load_authorities(CATALOG, BOUNDARY, RECIPE_SCHEMA)
    identity_request = writer.load_request(None, True, authorities)["summary"]
    prefix_request = writer.load_request(PREFIX8, False, authorities)["summary"]
    nonidentity_request = writer.load_request(NONIDENTITY4, False, authorities)["summary"]

    with tempfile.TemporaryDirectory(
        prefix=".nfl-upper-deck-subset-proof-", dir=ROOT / ".codex-tmp"
    ) as temporary:
        root = Path(temporary)
        identity_manifest, identity = verify_case(root / "identity", None, True)
        assert identity["mode"] == "identity_noop"
        assert identity["output"]["volume_sha256"] == writer.base.PACK_SHA256
        assert identity["output"]["pack_changed_byte_count"] == 0
        assert identity["decoded"]["decoded_changed_byte_count"] == 0
        assert identity["compression"]["consumed_bytes"] == 908_864
        assert identity["compression"]["scratch_bytes"] == 16

        prefix_manifest, prefix = verify_case(root / "prefix8", PREFIX8, False)
        assert prefix["mode"] == "count_only_prefix"
        assert prefix["request"]["new_vertex_count"] == 8
        assert prefix["decoded"]["decoded_changed_byte_count"] == 2
        assert prefix["decoded"]["stream_prefix_changed_byte_counts"] == [0, 0]
        assert prefix["decoded"]["output_sha256"] == (
            "dffa0cc9aa4599c94fe436ec8599c8b9597eacb0d377865c6454a733cf56f272"
        )
        assert prefix["compression"]["consumed_bytes"] == 908_863
        assert prefix["compression"]["scratch_bytes"] == 32

        nonidentity_manifest, nonidentity = verify_case(
            root / "nonidentity4", NONIDENTITY4, False
        )
        assert nonidentity["mode"] == "source_subset_remap"
        assert nonidentity["request"]["new_vertex_count"] == 4
        assert nonidentity["decoded"]["decoded_changed_byte_count"] == 64
        assert nonidentity["decoded"]["stream_prefix_changed_byte_counts"] == [34, 28]
        assert nonidentity["decoded"]["output_sha256"] == (
            "5503271598c6f55edb0f4d19b5232cadd55a9869029bf343287cb2157c4b9f93"
        )
        assert nonidentity["output"]["volume_sha256"] == (
            "65f3775e804db6c93a9f560737c6879d2fa8fb81e21559f33e755c5f8173d290"
        )
        assert nonidentity["compression"]["consumed_bytes"] == 908_822
        assert nonidentity["compression"]["scratch_bytes"] == 64
        assert nonidentity["topology"]["quad_count"] == 1
        assert nonidentity["topology"]["degenerate_triangle_count"] == 0

        try:
            writer.patch(
                INDEX, PREFIX8, False, root / "prefix8", CATALOG, BOUNDARY, RECIPE_SCHEMA
            )
        except writer.UpperDeckSubsetPatchError:
            existing_output_refused = True
        else:
            existing_output_refused = False
        assert existing_output_refused

        invalid = json.loads(PREFIX8.read_text(encoding="utf-8"))
        invalid["source_vertex_ids"][1] = invalid["source_vertex_ids"][0]
        invalid_path = root / "invalid-duplicate.json"
        invalid_path.write_bytes(canonical_json(invalid))
        try:
            writer.load_request(invalid_path, False, authorities)
        except writer.UpperDeckSubsetPatchError:
            writer_duplicate_refused = True
        else:
            writer_duplicate_refused = False
        try:
            verifier.load_recipe(invalid_path)
        except verifier.UpperDeckSubsetVerifyError:
            verifier_duplicate_refused = True
        else:
            verifier_duplicate_refused = False
        assert writer_duplicate_refused and verifier_duplicate_refused

        hardlink = root / "hardlink-alias"
        hardlink.mkdir()
        os.link(source_pack, hardlink / "9")
        shutil.copyfile(root / "identity/manifest.json", hardlink / "manifest.json")
        try:
            verifier.verify(
                INDEX, BOUNDARY, CATALOG, RECIPE_SCHEMA, hardlink, None,
                identity_noop=True,
            )
        except verifier.UpperDeckSubsetVerifyError as exc:
            hardlink_refused = "inode aliases" in str(exc)
        else:
            hardlink_refused = False
        assert hardlink_refused

        manifest_path = root / "nonidentity4/manifest.json"
        original_manifest = manifest_path.read_bytes()
        tampered = json.loads(original_manifest)
        tampered["claims"]["runtime_visibility_proved"] = True
        manifest_path.write_bytes(canonical_json(tampered))
        try:
            verifier.verify(
                INDEX, BOUNDARY, CATALOG, RECIPE_SCHEMA,
                root / "nonidentity4", NONIDENTITY4,
            )
        except verifier.UpperDeckSubsetVerifyError as exc:
            manifest_tamper_refused = "manifest differs" in str(exc)
        else:
            manifest_tamper_refused = False
        manifest_path.write_bytes(original_manifest)
        assert manifest_tamper_refused
        assert verifier.verify(
            INDEX, BOUNDARY, CATALOG, RECIPE_SCHEMA,
            root / "nonidentity4", NONIDENTITY4,
        )["mode"] == "source_subset_remap"

    index_after = file_sha256(INDEX)
    pack_after = file_sha256(source_pack)
    assert index_after == index_before and pack_after == pack_before
    report = {
        "schema": "nfl2k5_upper_deck_source_subset_roundtrip/v1",
        "authority": {
            "catalog": {
                "path": "reports/specs/nfl2k5_stadium_static_target_catalog.v1.json",
                "size": writer.CATALOG_SIZE,
                "sha256": writer.CATALOG_SHA256,
            },
            "changed_count_boundary": {
                "path": "reports/specs/nfl2k5_upper_deck_changed_count_boundary.v1.json",
                "size": writer.BOUNDARY_SIZE,
                "sha256": writer.BOUNDARY_SHA256,
            },
            "recipe_schema": {
                "path": "reports/specs/nfl2k5_upper_deck_source_subset_recipe.schema.json",
                "size": writer.RECIPE_SCHEMA_SIZE,
                "sha256": writer.RECIPE_SCHEMA_SHA256,
            },
        },
        "source": {
            "index_sha256_before": index_before,
            "index_sha256_after": index_after,
            "volume_9_sha256_before": pack_before,
            "volume_9_sha256_after": pack_after,
            "retail_modified": False,
        },
        "requests": {
            "identity_noop_request_sha256": identity_request["sha256"],
            "prefix8_recipe_path": "reports/asset_samples/nfl_scne/stadium_upper_deck_prefix8_source_subset_recipe.v1.json",
            "prefix8_recipe_sha256": prefix_request["sha256"],
            "nonidentity4_recipe_path": "reports/asset_samples/nfl_scne/stadium_upper_deck_nonidentity4_source_subset_recipe.v1.json",
            "nonidentity4_recipe_sha256": nonidentity_request["sha256"],
            "source_vertex_ids_embedded_in_report": False,
            "retail_records_embedded_in_report": False,
        },
        "target": {
            "target_id": writer.TARGET_ID,
            "shape_name": "upper_deck",
            "source_vertex_count": 12,
            "changed_vertex_counts": [4, 8],
            "stream_strides": [12, 10],
            "source_derived_records_only": True,
            "runtime_ownership_proved": False,
        },
        "identity_noop": identity,
        "count_only_prefix8": prefix,
        "nonidentity_source_subset4": nonidentity,
        "refusals": {
            "existing_output_directory": existing_output_refused,
            "duplicate_source_id_writer": writer_duplicate_refused,
            "duplicate_source_id_verifier": verifier_duplicate_refused,
            "hardlink_source_alias": hardlink_refused,
            "tampered_manifest": manifest_tamper_refused,
        },
        "claims": {
            "offline_fixed_span_changed_count_writer_implemented": True,
            "independent_changed_count_verifier_implemented": True,
            "identity_noop_whole_volume_exact": True,
            "count_only_prefix8_whole_volume_proved": True,
            "nonidentity_synchronized_whole_record_remap_proved": True,
            "arbitrary_external_vertex_authoring_proved": False,
            "bounds_or_culling_serializer_proved": False,
            "collision_or_lod_ownership_proved": False,
            "runtime_visibility_proved": False,
            "original_xbox_hardware_proved": False,
            "production_ready": False,
            "gui_exposed": False,
            "distribution_ready": False,
        },
    }
    assert not contains_private_payload(report)
    report_path.write_bytes(canonical_json(report))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit(f"error: refusing existing report: {args.report}")
    run(args.report)
    print(f"NFL_UPPER_DECK_SUBSET_ROUNDTRIP_PASS report={args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
