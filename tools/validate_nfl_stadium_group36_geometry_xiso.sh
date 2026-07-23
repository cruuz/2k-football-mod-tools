#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SOURCE='ESPN NFL 2K5 (USA).xiso.iso'
INDEX='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
PACK='extracted/ESPN NFL 2K5 (USA)/vc_53450030/9'
RECIPE='reports/asset_samples/nfl_scne/stadium_group36_zero_positions_permuted_quad_recipe.json'
GEOMETRY_DIR='.geometry-proof/changed-output'
CHANGED="$GEOMETRY_DIR/9"
CHANGED_MANIFEST="$GEOMETRY_DIR/manifest.json"
OUTPUT='build/nfl2k5-stadium-group36-geometry-xiso-20260713/ESPN-NFL-2K5-group36-geometry-v2.xiso.iso'
WORKFLOW='build/nfl2k5-stadium-group36-geometry-xiso-20260713/workflow-v2.json'
WRITER='tools/nfl_stadium_group36_geometry_xiso_patch.py'
VERIFIER='tools/nfl_stadium_group36_geometry_xiso_verify.py'
TEST='tests/test_nfl_stadium_group36_geometry_xiso.py'
SPEC='reports/specs/nfl2k5_group36_geometry_xiso_transport.v1.json'
DOC='docs/research/nfl_group36_geometry_xiso_transport.md'

check_pin() {
  local path="$1" size="$2" digest="$3"
  test -f "$path"
  test ! -L "$path"
  test "$(stat -c %s "$path")" = "$size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$digest"
}

python3 -m unittest tests.test_nfl_stadium_group36_geometry_xiso >/dev/null

check_pin "$SOURCE" 6300499968 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_pin "$INDEX" 193710080 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
check_pin "$PACK" 634941440 779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a
check_pin "$RECIPE" 1786 e940739abb9f901607ce2b3c35a629b2cf3ccbda0ba11c4d8963fccadad078fe
check_pin "$CHANGED" 634941440 6bc202ee8a01caaa02885c58810fe9add2dae7afd862793a6a479622d63770e4
check_pin "$CHANGED_MANIFEST" 4321 c8033acaf39f032d69d05e0a3f4a2ea235f35867dd40b7450547df49fa7c7917
check_pin "$OUTPUT" 6300499968 67910ea934a891c32de6bf5ddc00eae4c7c696589763773fd3453c6f7bf65c0e
check_pin "$WORKFLOW" 3060 e0ef2d1cd9b82a7377200436deb4f982c6e76d90f86b4618fc6cbe7d7a008db1
check_pin "$WRITER" 16433 a2474d9f9f4f87e86e5612fd69509090d9ccdcce30a0c68024fe526749631ac0
check_pin "$VERIFIER" 15054 34b5931c86d82f5016870e3e766280417e4a298875d0c790fedb5927726d8fa0
check_pin "$TEST" 9719 a91673dc7c950dd2e92ac36de947e9e6b585b5c6653c3c85e5d515359ad89d57
check_pin "$SPEC" 8829 6efca1ef5fe3ac0e3ea8f6585fed6521cf2039f98c88d4bc6719289457d381aa
check_pin "$DOC" 7824 5a39d3de1a628e5c13cb53e3d3046a9cc9e192e57457d2a182c11e9d2140b7da

python3 - "$SPEC" "$WORKFLOW" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys


def canonical(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    value = json.loads(raw)
    expected = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    assert raw == expected, f"noncanonical JSON: {path}"
    assert isinstance(value, dict)
    return value


spec = canonical(Path(sys.argv[1]))
workflow = canonical(Path(sys.argv[2]))

assert spec["schema"] == "nfl2k5_group36_geometry_xiso_transport/v1"
assert spec["version"] == 1
assert spec["claims"] == {
    "changed_count_mesh_writeback_proved": False,
    "layout_identical_copy_only_xiso": True,
    "offline_native_geometry_transport_proved": True,
    "original_xbox_hardware_proved": False,
    "production_ready": False,
    "target_group36_loaded_at_runtime": False,
    "xemu_boot_acceptance_observed_after_transport_manifest": True,
    "xemu_geometry_visibility_proved": False,
}
patch = spec["format"]["authorized_patch"]
assert patch["absolute_span_offset"] == 205566528
assert patch["absolute_end_exclusive"] == 206475440
assert patch["pack_relative_span_offset"] == 132799040
assert patch["pack_relative_end_exclusive"] == 133707952
assert patch["span_size"] == 908912
assert patch["absolute_end_exclusive"] - patch["absolute_span_offset"] == patch["span_size"]
assert patch["pack_relative_end_exclusive"] - patch["pack_relative_span_offset"] == patch["span_size"]
assert spec["difference_ledger"]["actual_witness"]["changed_byte_count"] == 857950
assert spec["difference_ledger"]["actual_witness"]["changed_run_count"] == 24046
assert spec["data_policy"] == {
    "contains_replacement_bytes": False,
    "contains_retail_geometry_values": False,
    "contains_retail_payload_bytes": False,
    "hashes_sizes_offsets_and_structure_only": True,
    "public_recipe_contains_only_authored_nonretail_values": True,
}
assert spec["independent_verification"]["transport_verifier_imports_native_geometry_writer"] is False
assert spec["independent_verification"]["transport_verifier_imports_transport_writer"] is False

assert workflow["schema"] == "nfl2k5_group36_geometry_xiso_patch/v1"
assert workflow["source"]["sha256_before"] == workflow["source"]["sha256_after"] == (
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
)
assert workflow["native_geometry_proof"]["changed_volume_sha256"] == (
    "6bc202ee8a01caaa02885c58810fe9add2dae7afd862793a6a479622d63770e4"
)
assert workflow["output"]["sha256"] == (
    "67910ea934a891c32de6bf5ddc00eae4c7c696589763773fd3453c6f7bf65c0e"
)
assert workflow["patch"]["absolute_span_offset"] == 205566528
assert workflow["patch"]["span_size"] == 908912
assert workflow["patch"]["changed_byte_count"] == 857950
assert workflow["patch"]["changed_run_count"] == 24046
assert workflow["patch"]["all_xiso_bytes_outside_span_bit_exact"] is True
assert workflow["xdvdfs"]["tree_identical_after_patch"] is True
assert workflow["xdvdfs"]["all_sector_extents_preserved"] is True
assert workflow["claims"] == {
    "layout_identical_copy_only_xiso": True,
    "offline_native_geometry_transport_proved": True,
    "original_xbox_hardware_proved": False,
    "production_ready": False,
    "xemu_boot_proved": False,
    "xemu_geometry_visibility_proved": False,
}
PY

verification="$(PYTHONPATH=tools python3 "$VERIFIER" \
  --source-xiso "$SOURCE" \
  --index "$INDEX" \
  --recipe "$RECIPE" \
  --geometry-output-dir "$GEOMETRY_DIR" \
  --output-xiso "$OUTPUT" \
  --manifest "$WORKFLOW")"

VERIFY_JSON="$verification" python3 - <<'PY'
from __future__ import annotations

import json
import os


value = json.loads(os.environ["VERIFY_JSON"])
assert value == {
    "absolute_span_offset": 205566528,
    "changed_byte_count": 857950,
    "changed_run_count": 24046,
    "changed_volume_sha256": "6bc202ee8a01caaa02885c58810fe9add2dae7afd862793a6a479622d63770e4",
    "default_xbe_exact": True,
    "hardware_proved": False,
    "outside_authorized_span_exact": True,
    "output_xiso_sha256": "67910ea934a891c32de6bf5ddc00eae4c7c696589763773fd3453c6f7bf65c0e",
    "production_ready": False,
    "schema": "nfl2k5_group36_geometry_xiso_verify/v1",
    "source_unchanged": True,
    "span_size": 908912,
    "xdvdfs_tree_exact": True,
    "xemu_boot_proved": False,
    "xemu_geometry_visibility_proved": False,
}
PY

# Re-pin the immutable retail inputs after independent verification. The
# verifier also hashes the source XISO twice through the same open descriptor.
check_pin "$SOURCE" 6300499968 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_pin "$INDEX" 193710080 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
check_pin "$PACK" 634941440 779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a
check_pin "$RECIPE" 1786 e940739abb9f901607ce2b3c35a629b2cf3ccbda0ba11c4d8963fccadad078fe

echo 'NFL_GROUP36_GEOMETRY_XISO_VALIDATION_PASS output_sha=67910ea934a891c32de6bf5ddc00eae4c7c696589763773fd3453c6f7bf65c0e changed=857950 runs=24046 absolute=205566528 span=908912 xdvdfs_exact=true outside_exact=true default_xbe_exact=true source_unchanged=true unit_tests=9 offline_transport=true xemu_boot_observed_separately=true geometry_visibility=false hardware=false production=false'
