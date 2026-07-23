#!/usr/bin/env python3
"""Generate/validate the hashes-only APF same-count POSITION0 proof report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports/assets/apf_scne_same_count_position_roundtrip.json"
REPORT_SCHEMA = "apf2k8_scne_same_count_position_roundtrip/v1"

PINS = {
    "recipe_schema": ("reports/specs/apf2k8_scne_same_count_position_recipe.schema.json", 4064, "8094a4a64325728082091e87ba3fcd0e5ed30c8c6f06f1e7074934720438af51"),
    "nonretail_zero_sample": ("reports/asset_samples/apf_scene/stadium_polySurface19930_nonretail_zero_recipe.json", 1938, "fc3b3e010cc534634470e29e8395a5e56c6b0cbc2d714464355a27be3f59764b"),
    "noop_manifest": ("reports/assets/apf_scne_same_count_position_noop_manifest.json", 5821, "b735c62338158315052717f4f7ba7352aafc4e43e0017f1126f3e4a4b2585d23"),
    "noop_verification": ("reports/assets/apf_scne_same_count_position_noop_verification.json", 2479, "1be207ffd820faa7356d0c7f0d73f166bda06271a537dc936c049b696ac4deb9"),
    "changed_manifest": ("reports/assets/apf_scne_same_count_position_changed_manifest.json", 5925, "62673e228fcc501669d9bd3fd98d16598d872bf1e24b8ef81f190228b8aae116"),
    "changed_verification": ("reports/assets/apf_scne_same_count_position_changed_verification.json", 2481, "b2873a1c45057eb434444aebe9eb15f625bf0af7995c25bf689bc7b7005759ae"),
}


class ProofError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ProofError(f"top level is not an object: {path}")
    return value


def _pin_inputs() -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for key, (relative, size, digest) in PINS.items():
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size != size or _sha(path) != digest:
            raise ProofError(f"proof input identity drift: {key}")
        output[key] = {"path": relative, "size_bytes": size, "sha256": digest}
    return output


def build_report() -> dict[str, Any]:
    pins = _pin_inputs()
    noop_manifest = _load(ROOT / PINS["noop_manifest"][0])
    noop_verify = _load(ROOT / PINS["noop_verification"][0])
    changed_manifest = _load(ROOT / PINS["changed_manifest"][0])
    changed_verify = _load(ROOT / PINS["changed_verification"][0])
    if noop_manifest.get("mode") != "no_op" or noop_verify.get("mode") != "no_op":
        raise ProofError("no-op witness mode drift")
    if changed_manifest.get("mode") != "changed" or changed_verify.get("mode") != "changed":
        raise ProofError("changed witness mode drift")
    if noop_manifest["result"]["output_pack_sha256"] != "9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb":
        raise ProofError("no-op whole-pack identity drift")
    if changed_manifest["result"]["output_pack_sha256"] != "6f275ccb780acfee0cba9cd59c38e4bb2aedb18d01dec7030d61546441026b40":
        raise ProofError("changed whole-pack identity drift")
    if noop_manifest["recipe"]["sha256"] != "1adf02c37cb458afef1509a8cbe4cfa82260b897833553222af5d1fa97403faf":
        raise ProofError("local-only no-op recipe identity drift")
    if changed_manifest["recipe"]["sha256"] != "18ae4558668a1a1831031bb6191e3ff914abaaa867ca369836f8673521173d2b":
        raise ProofError("local-only changed recipe identity drift")
    for manifest, verification in ((noop_manifest, noop_verify), (changed_manifest, changed_verify)):
        if manifest["claims"] != verification["claims"]:
            raise ProofError("writer/verifier claim boundary drift")
        if not all(verification["checks"].values()):
            raise ProofError("independent verification check is false")
        if manifest["preservation"]["non_target_part_count"] != 12 or manifest["preservation"]["sibling_part_count"] != 11:
            raise ProofError("part preservation counts drift")
    return {
        "schema": REPORT_SCHEMA,
        "status": "offline byte-level same-count POSITION0 write-back proved for one pinned structural-static candidate; runtime rigid-attachment and general mesh writing remain unproved",
        "contains_retail_geometry": False,
        "contains_replacement_bytes": False,
        "inputs": pins,
        "recipe_distribution": {
            "checked_in_sample": "four all-zero nonretail authored FLOAT3 positions",
            "retail_or_retail_derived_recipe_coordinates_committed": False,
            "full_proof_recipes": "derived locally from the user-owned source into a temporary directory",
            "local_only_noop_recipe_sha256": noop_manifest["recipe"]["sha256"],
            "local_only_changed_recipe_sha256": changed_manifest["recipe"]["sha256"],
        },
        "target": {
            "outer_table_index": 14,
            "physical_pack": "1A",
            "fixed_outer_allocation_bytes": 12_931_072,
            "inner_file_index": 8,
            "inner_name": "stadium",
            "node_index": 17,
            "node_name": "polySurface19930",
            "vertex_count": 4,
            "serialized_position_type": "FLOAT32x3_BE",
            "stream_stride_bytes": 24,
            "authorized_position_lane_bytes": 48,
        },
        "no_op_witness": {
            "recipe_sha256": noop_manifest["recipe"]["sha256"],
            "manifest_sha256": pins["noop_manifest"]["sha256"],
            "verification_sha256": pins["noop_verification"]["sha256"],
            "source_and_output_1a_sha256": noop_manifest["result"]["output_pack_sha256"],
            "source_and_output_outer_sha256": noop_manifest["result"]["outer_entry_sha256"],
            "complete_1a_byte_identical": True,
            "h7a_recompressed": False,
            "allocation_slack_bytes": noop_manifest["result"]["allocation_slack_after_bytes"],
        },
        "changed_witness": {
            "operation": "add exactly +1 X, +2 Y, +3 Z to all four authored FLOAT3 positions",
            "recipe_sha256": changed_manifest["recipe"]["sha256"],
            "manifest_sha256": pins["changed_manifest"]["sha256"],
            "verification_sha256": pins["changed_verification"]["sha256"],
            "output_1a_sha256": changed_manifest["result"]["output_pack_sha256"],
            "output_outer_sha256": changed_manifest["result"]["outer_entry_sha256"],
            "output_stadium_dram_sha256": changed_manifest["result"]["stadium_dram_sha256"],
            "output_position_payload_sha256": changed_manifest["result"]["position_payload_sha256"],
            "changed_decoded_dram_bytes": changed_manifest["result"]["changed_decoded_dram_byte_count"],
            "authorized_lane_bytes": 48,
            "changed_inner_parts": changed_manifest["result"]["changed_inner_parts"],
            "block0_stored_length_before": changed_manifest["result"]["block0_stored_length_before"],
            "block0_stored_length_after": changed_manifest["result"]["block0_stored_length_after"],
            "file_length_after": changed_manifest["result"]["file_length_after"],
            "allocation_slack_bytes": changed_manifest["result"]["allocation_slack_after_bytes"],
        },
        "preservation_proof": {
            "uv_normal_interleaves_exact": True,
            "matrix_hierarchy_draw_index_declarations_descriptor_exact": True,
            "iff_header_complement_and_all_file_descriptors_exact": True,
            "stadium_vram_exact": True,
            "eleven_sibling_parts_exact": True,
            "twelve_non_target_parts_exact": True,
            "stored_block1_exact": True,
            "footer_and_fixed_outer_tail_exact": True,
            "all_1a_bytes_outside_outer14_exact": True,
            "all_four_source_pack_hashes_rechecked": True,
            "independent_verifier_imports_production_writer_or_parsers": False,
        },
        "refusals_and_publication_safety": {
            "symlinked_game_directory_refused": True,
            "symlinked_recipe_refused": True,
            "symlinked_output_parent_refused": True,
            "existing_destination_refused_without_replace": True,
            "source_output_hardlink_alias_refused": True,
            "noncanonical_duplicate_key_or_oversize_manifest_recipe_refused": True,
            "unexpected_output_directory_child_refused": True,
            "forbidden_iff_header_or_file_descriptor_mutation_refused": True,
            "output_directory_inode_checked_after_mkdir_open_and_before_success": True,
            "output_child_inodes_checked_after_create_and_before_success": True,
            "cleanup_unlinks_only_fstat_pinned_owned_child_inodes": True,
            "copied_1a_reserved_o_excl_o_rdwr_for_readback_hash": True,
            "o_wronly_readback_regression_closed_by_full_noop_whole_pack_hash": True,
            "verification_artifact_requires_separate_absent_path": True,
            "hostile_same_uid_source_or_recipe_swap_restore_excluded": False,
            "residual_threat_boundary": "before/after full hashes and inode checks reject ordinary drift; hostile same-UID swap-and-restore across the complete build is not proved excluded"
        },
        "claims": changed_manifest["claims"],
    }


def render() -> bytes:
    return (json.dumps(build_report(), indent=4, sort_keys=True) + "\n").encode("utf-8")


def validate(path: Path = DEFAULT_REPORT) -> dict[str, Any]:
    expected = render()
    actual = path.read_bytes()
    if actual != expected:
        raise ProofError("roundtrip report differs from deterministic generation")
    report = _load(path)
    return {
        "schema": "apf2k8_scne_same_count_position_roundtrip_validation/v1",
        "report_sha256": hashlib.sha256(actual).hexdigest(),
        "vertices": report["target"]["vertex_count"],
        "witnesses": 2,
        "non_target_parts": 12,
        "runtime": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--generate", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.generate:
            args.generate.parent.mkdir(parents=True, exist_ok=True)
            args.generate.write_bytes(render())
            print(json.dumps({"schema": REPORT_SCHEMA, "sha256": _sha(args.generate)}, sort_keys=True))
        else:
            print(json.dumps(validate(args.report), sort_keys=True))
        return 0
    except (OSError, ProofError, KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
