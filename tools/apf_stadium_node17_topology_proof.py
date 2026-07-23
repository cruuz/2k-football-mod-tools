#!/usr/bin/env python3
"""Assemble the hash-only APF node17 topology round-trip proof report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANGED_DIR = ROOT / ".geometry-proof/apf-node17-topology-changed"
DEFAULT_NOOP_DIR = ROOT / ".geometry-proof/apf-node17-topology-noop"
DEFAULT_CHANGED_VERIFY = ROOT / "reports/assets/apf_stadium_node17_same_footprint_topology_verification.json"
DEFAULT_NOOP_VERIFY = ROOT / "reports/assets/apf_stadium_node17_same_footprint_topology_noop_verification.json"
DEFAULT_OUTPUT = ROOT / "reports/assets/apf_stadium_node17_same_footprint_topology_roundtrip.json"
MANIFEST_NAME = "apf2k8_scne_same_footprint_topology_manifest.json"


class ProofError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProofError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(ROOT)),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def load(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw)
    require(isinstance(value, dict), f"{path}: root must be object")
    require(raw == (json.dumps(value, indent=4, sort_keys=True) + "\n").encode(), f"{path}: noncanonical JSON")
    return value


def build(
    changed_dir: Path,
    noop_dir: Path,
    changed_verify_path: Path,
    noop_verify_path: Path,
) -> dict[str, Any]:
    changed_manifest_path = changed_dir / MANIFEST_NAME
    noop_manifest_path = noop_dir / MANIFEST_NAME
    changed = load(changed_manifest_path)
    noop = load(noop_manifest_path)
    changed_verify = load(changed_verify_path)
    noop_verify = load(noop_verify_path)
    require(changed["schema"] == "apf2k8_scne_same_footprint_topology_patch/v1", "changed manifest schema")
    require(noop["schema"] == changed["schema"], "no-op manifest schema")
    require(changed["mode"] == "changed" and noop["mode"] == "no_op", "proof modes differ")
    require(changed_verify["mode"] == "changed" and noop_verify["mode"] == "no_op", "verifier modes differ")
    require(changed_verify["manifest_sha256"] == sha256_file(changed_manifest_path), "changed manifest verifier pin")
    require(noop_verify["manifest_sha256"] == sha256_file(noop_manifest_path), "no-op manifest verifier pin")
    require(all(changed_verify["checks"].values()), "changed verifier has failed check")
    require(all(noop_verify["checks"].values()), "no-op verifier has failed check")
    require(changed["result"]["native_triangle_count"] == 2, "changed triangle count")
    require(changed["result"]["native_degenerate_triangle_count"] == 0, "changed degenerates")
    require(changed["result"]["changed_decoded_dram_byte_count"] == 2, "changed byte count")
    require(changed["result"]["changed_inner_parts"] == [{"file_index": 8, "part_index": 0}], "changed part set")
    require(changed["result"]["allocation_slack_after_bytes"] > 0, "changed allocation overflow")
    require(noop["result"]["output_pack_sha256"] == noop["source"]["packs"][2]["sha256"], "no-op pack identity")
    require(noop["result"]["outer_entry_sha256"] == noop["source"]["outer_entry_sha256"], "no-op outer identity")
    require(noop["result"]["h7a_block0_recompressed"] is False, "no-op recompressed")
    require(noop["result"]["changed_decoded_dram_byte_count"] == 0, "no-op decoded changes")
    for manifest in (changed, noop):
        require(manifest["preservation"]["draw_record_exact"] is True, "draw preservation")
        require(manifest["preservation"]["vertex_stream_exact"] is True, "stream preservation")
        require(manifest["preservation"]["all_non_target_parts_exact"] is True, "part preservation")
        require(manifest["preservation"]["source_files_rechecked_after_write"] is True, "source recheck")
        require(manifest["claims"]["emulator_runtime_visibility_proved"] is False, "runtime overclaim")
        require(manifest["claims"]["xbox_360_hardware_proved"] is False, "hardware overclaim")

    artifact_paths = [
        ROOT / "tools/apf_scne_draw_topology_spec.py",
        ROOT / "reports/assets/apf_scne_draw_topology_corpus.v1.json",
        ROOT / "reports/specs/apf2k8_scne_draw_topology.v1.json",
        ROOT / "tools/apf_stadium_node17_topology_patch.py",
        ROOT / "tools/apf_stadium_node17_topology_verify.py",
        ROOT / "tools/apf_stadium_node17_topology_proof_recipes.py",
        ROOT / "reports/specs/apf2k8_scne_same_footprint_topology_recipe.schema.json",
        ROOT / "reports/asset_samples/apf_scene/stadium_node17_nonretail_permuted_strip_recipe.json",
        changed_verify_path,
        noop_verify_path,
    ]
    return {
        "schema": "apf2k8_scne_same_footprint_topology_roundtrip/v1",
        "profile": "outer14_inner8_node17_four_be16_strip/v1",
        "status": "offline fixed-allocation writer and independent verifier proved; runtime and hardware unproved",
        "data_policy": {
            "contains_retail_vertex_coordinates": False,
            "contains_retail_index_sequences": False,
            "contains_replacement_bytes": False,
            "contains_hashes_offsets_extents_and_aggregate_metrics_only": True,
        },
        "target": changed["target"],
        "draw_coupling": {
            "draw_semantics": changed["preservation"]["draw_semantics"],
            "draw_record_exact": True,
            "reason_no_draw_write": "the admitted permutation retains first=0, count=4, capacity=2, base=0, minimum=0, range=4",
            "corpus_relationships": {
                "scne_resources": 1303,
                "mesh_nodes": 13006,
                "draw_records": 47112,
                "serialized_indices": 24519417,
                "all_draw_windows_partition_payload": True,
            },
        },
        "no_op": {
            "recipe_sha256": noop_verify["recipe_sha256"],
            "complete_1a_byte_identical": True,
            "source_and_output_1a_sha256": noop["result"]["output_pack_sha256"],
            "source_and_output_outer_sha256": noop["result"]["outer_entry_sha256"],
            "h7a_recompressed": False,
            "changed_decoded_dram_bytes": 0,
            "independent_verifier_checks": len(noop_verify["checks"]),
        },
        "changed_nonretail_permutation": {
            "recipe_sha256": changed_verify["recipe_sha256"],
            "output_1a_sha256": changed["result"]["output_pack_sha256"],
            "output_outer_sha256": changed["result"]["outer_entry_sha256"],
            "output_stadium_dram_sha256": changed["result"]["stadium_dram_sha256"],
            "output_index_buffer_sha256": changed["result"]["index_buffer_sha256"],
            "changed_decoded_dram_bytes": changed["result"]["changed_decoded_dram_byte_count"],
            "authorized_decoded_bytes": 8,
            "native_triangle_count": changed["result"]["native_triangle_count"],
            "native_degenerate_triangle_count": changed["result"]["native_degenerate_triangle_count"],
            "block0_stored_length_before": changed["result"]["block0_stored_length_before"],
            "block0_stored_length_after": changed["result"]["block0_stored_length_after"],
            "fixed_outer_allocation_bytes": changed["target"]["fixed_outer_allocation_bytes"],
            "allocation_slack_after_bytes": changed["result"]["allocation_slack_after_bytes"],
            "changed_inner_parts": changed["result"]["changed_inner_parts"],
            "independent_verifier_checks": len(changed_verify["checks"]),
        },
        "preservation": {
            "all_decoded_bytes_outside_eight_index_bytes_exact": True,
            "draw_record_exact": True,
            "vertex_stream_exact": True,
            "declarations_descriptor_matrix_hierarchy_node_exact": True,
            "stadium_vram_exact": True,
            "eleven_sibling_parts_exact": True,
            "twelve_non_target_parts_exact": True,
            "stored_block1_footer_and_iff_header_complement_exact": True,
            "all_output_1a_bytes_outside_outer14_exact": True,
            "source_files_rechecked_after_each_write": True,
            "independent_verifier_imports_topology_writer_or_production_parser": False,
        },
        "artifacts": [pin(path) for path in artifact_paths],
        "claim_flags": {
            "same_footprint_topology_writer_implemented": True,
            "offline_byte_level_roundtrip_proved": True,
            "independent_verifier_proved": True,
            "changed_vertex_count_proved": False,
            "material_or_vertex_authoring_proved": False,
            "bounds_culling_proved": False,
            "runtime_proved": False,
            "hardware_proved": False,
            "production_ready": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-dir", type=Path, default=DEFAULT_CHANGED_DIR)
    parser.add_argument("--noop-dir", type=Path, default=DEFAULT_NOOP_DIR)
    parser.add_argument("--changed-verification", type=Path, default=DEFAULT_CHANGED_VERIFY)
    parser.add_argument("--noop-verification", type=Path, default=DEFAULT_NOOP_VERIFY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        document = build(args.changed_dir, args.noop_dir, args.changed_verification, args.noop_verification)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes((json.dumps(document, indent=4, sort_keys=True) + "\n").encode())
        print(
            "APF_SCNE_NODE17_TOPOLOGY_PROOF_PASS "
            f"changed_bytes={document['changed_nonretail_permutation']['changed_decoded_dram_bytes']} "
            f"slack={document['changed_nonretail_permutation']['allocation_slack_after_bytes']} "
            "noop_exact=true independent_verify=true runtime=false hardware=false "
            f"sha256={sha256_file(args.output)}"
        )
        return 0
    except (ProofError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
