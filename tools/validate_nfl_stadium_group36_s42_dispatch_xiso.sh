#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

RETAIL_SOURCE='ESPN NFL 2K5 (USA).xiso.iso'
INDEX='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
RETAIL_PACK9='extracted/ESPN NFL 2K5 (USA)/vc_53450030/9'

BUILD='build/nfl2k5-stadium-group36-geometry-xiso-20260713'
CONTROL_OUTPUT="$BUILD/ESPN-NFL-2K5-s42-dispatch-control.xiso.iso"
CONTROL_MANIFEST="$BUILD/s42-dispatch-control-workflow.json"
EXPANDED_SOURCE="$BUILD/ESPN-NFL-2K5-group36-expanded-wall.xiso.iso"
EXPANDED_SOURCE_MANIFEST="$BUILD/expanded-wall-workflow.json"
EXPANDED_OUTPUT="$BUILD/ESPN-NFL-2K5-group36-expanded-wall-s42-dispatch.xiso.iso"
EXPANDED_MANIFEST="$BUILD/expanded-wall-s42-dispatch-workflow.json"

RECIPE='.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/expanded_local_wall_recipe.json'
GEOMETRY_DIR='.geometry-proof/expanded-wall-output'
GEOMETRY_PACK9="$GEOMETRY_DIR/9"
GEOMETRY_MANIFEST="$GEOMETRY_DIR/manifest.json"

WRITER='tools/nfl_stadium_group36_s42_dispatch_xiso_patch.py'
VERIFIER='tools/nfl_stadium_group36_s42_dispatch_xiso_verify.py'
TEST='tests/test_nfl_stadium_group36_s42_dispatch_xiso.py'
SPEC='reports/specs/nfl2k5_group36_s42_runtime_dispatch_shim.v1.json'
DOC='docs/research/nfl_group36_s42_runtime_dispatch_shim.md'

check_pin() {
  local path="$1" size="$2" digest="$3"
  test -f "$path"
  test ! -L "$path"
  test "$(stat -c %s "$path")" = "$size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$digest"
}

python3 -m py_compile "$WRITER" "$VERIFIER" "$TEST"
PYTHONPATH=tools python3 -m unittest tests.test_nfl_stadium_group36_s42_dispatch_xiso >/dev/null

# Immutable inputs and the two already-created diagnostic images.
check_pin "$RETAIL_SOURCE" 6300499968 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_pin "$INDEX" 193710080 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
check_pin "$RETAIL_PACK9" 634941440 779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a
check_pin "$CONTROL_OUTPUT" 6300499968 32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5
check_pin "$CONTROL_MANIFEST" 3659 e619cf3fa5eae3eea4a09e97f681db96df968041c6746dda68a013dd6ddbef89

check_pin "$EXPANDED_SOURCE" 6300499968 a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c
check_pin "$EXPANDED_SOURCE_MANIFEST" 3062 80a5361c8b514f7215683d7ae7afdf91a365f4ac64d1736ba76ba349c9d69f95
check_pin "$RECIPE" 1824 3ee45f7b36fae28e51814e7695dc9bbd20d3ea4ac3a722ca53e9bf1264639625
check_pin "$GEOMETRY_PACK9" 634941440 c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad
check_pin "$GEOMETRY_MANIFEST" 4319 8d5454101129b8fc626cb42ac238ca49c6b39a4c0bdd52649fb1eba0a62d6417
check_pin "$EXPANDED_OUTPUT" 6300499968 3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16
check_pin "$EXPANDED_MANIFEST" 4577 4fd1d53323c39cef94d7b5ac2a17a4c7d8669abff126f83a5eeda8a451b3e5c0

check_pin "$WRITER" 22473 2e50a6274980531890450a1f7548574a6e4e15049d2befbe9981866024e8e19a
check_pin "$VERIFIER" 22063 23441278a6809ecb857755a1b38a5a96abff3abf25c38036400c8a022d3b85fa
check_pin "$TEST" 3148 e7911ff50f18ac3858b8799d48ab2651f5e00aee0747844854e0680e7a3d3ffc
check_pin "$SPEC" 5425 b3d0aba1d98188d4e5350ddf9893952feed9bc75eb0fbb4baf1fda7fb79e1ff7
check_pin "$DOC" 5491 57ac6812b672ff990c464d1958002da7af79e720292e2ddeb6b8dd0b69d9c484

python3 - "$SPEC" "$CONTROL_MANIFEST" "$EXPANDED_MANIFEST" "$VERIFIER" <<'PY'
from __future__ import annotations

import ast
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
control = canonical(Path(sys.argv[2]))
expanded = canonical(Path(sys.argv[3]))
verifier_path = Path(sys.argv[4])

assert spec["schema"] == "nfl2k5_group36_s42_runtime_dispatch_shim/v1"
assert spec["claims"] == {
    "diagnostic_only": True,
    "offline_two_byte_dispatch_shim_proved": True,
    "original_xbox_hardware_proved": False,
    "production_ready": False,
    "public_editor_exposed": False,
    "xemu_geometry_visibility_proved": False,
    "xemu_target_outer_loaded_proved": False,
}
assert spec["dispatch_edit"] == {
    "after_utf16le_hex": "7300340032000000",
    "allowed_xiso_changed_byte_offsets_decimal": [1635418436, 1635418438],
    "allowed_xiso_changed_byte_offsets_hex": ["0x617a8144", "0x617a8146"],
    "before_utf16le_hex": "7300310038000000",
    "changed_relative_bytes": [2, 4],
    "replacement": "s18 -> s42",
    "written_allocation_bytes": 8,
}
assert spec["format"]["relative_pointer"]["formula"] == (
    "target = field_offset + signed_i32_stored_value - 1"
)
assert spec["format"]["stadium_18"]["asset_code_target_aligned_relative_pointer_fields"] == [
    "0x9bc"
]
assert spec["loader_ownership"] == {
    "active_stadium_accessor": "0x00077460",
    "asset_code_load": "0x00062c76 MOV EDX,[EAX+0x0c]",
    "filename_format": "%s%c%c.iff",
    "filename_format_address": "0x00e610a0",
    "filename_format_callsite": "0x00062c82",
    "night_clear_result": "s42nd.iff",
    "read_only_trace": ".codex-tmp/s42_runtime_dispatch/out/trace.txt",
}

expected_claims = {
    "diagnostic_only": True,
    "layout_identical_copy_only_xiso": True,
    "offline_two_byte_dispatch_shim_proved": True,
    "original_xbox_hardware_proved": False,
    "production_ready": False,
    "public_editor_exposed": False,
    "source_geometry_volume9_preserved": True,
    "xemu_geometry_visibility_proved": False,
    "xemu_target_outer_loaded_proved": False,
}
for manifest, profile, source_sha, output_sha in (
    (
        control,
        "retail_control",
        "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
        "32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5",
    ),
    (
        expanded,
        "expanded_wall",
        "a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c",
        "3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16",
    ),
):
    assert manifest["schema"] == "nfl2k5_group36_s42_dispatch_xiso_patch/v1"
    assert manifest["source_profile"] == profile
    assert manifest["source"]["sha256_before"] == source_sha
    assert manifest["source"]["sha256_after"] == source_sha
    assert manifest["output"]["sha256"] == output_sha
    assert manifest["patch"]["actual_changed_byte_count"] == 2
    assert manifest["patch"]["actual_changed_byte_offsets"] == [1635418436, 1635418438]
    assert manifest["patch"]["allowed_changed_byte_offsets"] == [1635418436, 1635418438]
    assert manifest["patch"]["all_other_xiso_bytes_identical"] is True
    assert manifest["xdvdfs"]["tree_identical_after_patch"] is True
    assert manifest["xdvdfs"]["all_sector_extents_preserved"] is True
    assert manifest["claims"] == expected_claims

# Independence is a source property as well as a unit-test assertion.
tree = ast.parse(verifier_path.read_text(encoding="utf-8"), filename=str(verifier_path))
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports.update(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imports.add(node.module)
assert "nfl_stadium_group36_s42_dispatch_xiso_patch" not in imports
assert "nfl_roster_write" not in imports
PY

control_verification="$(PYTHONPATH=tools python3 "$VERIFIER" \
  --source-profile retail_control \
  --source-xiso "$RETAIL_SOURCE" \
  --output-xiso "$CONTROL_OUTPUT" \
  --manifest "$CONTROL_MANIFEST")"

expanded_verification="$(PYTHONPATH=tools python3 "$VERIFIER" \
  --source-profile expanded_wall \
  --source-xiso "$EXPANDED_SOURCE" \
  --source-geometry-manifest "$EXPANDED_SOURCE_MANIFEST" \
  --retail-xiso "$RETAIL_SOURCE" \
  --index "$INDEX" \
  --recipe "$RECIPE" \
  --geometry-output-dir "$GEOMETRY_DIR" \
  --output-xiso "$EXPANDED_OUTPUT" \
  --manifest "$EXPANDED_MANIFEST")"

CONTROL_JSON="$control_verification" EXPANDED_JSON="$expanded_verification" python3 - <<'PY'
from __future__ import annotations

import json
import os


common = {
    "changed_byte_count": 2,
    "changed_byte_offsets": [1635418436, 1635418438],
    "default_xbe_exact": True,
    "hardware_proved": False,
    "output_pack0_sha256": "57d5ea1703e952cfca9b0f5175b5c9f9bc0bda3eb6676db9f8b6b0e074bddae9",
    "production_ready": False,
    "roster_pointer_and_allocation_exact": True,
    "schema": "nfl2k5_group36_s42_dispatch_xiso_verify/v1",
    "source_pack0_sha256": "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d",
    "source_unchanged": True,
    "xdvdfs_tree_exact": True,
    "xemu_geometry_visibility_proved": False,
    "xemu_target_outer_loaded_proved": False,
}

expected = {
    "retail_control": {
        **common,
        "manifest_sha256": "e619cf3fa5eae3eea4a09e97f681db96df968041c6746dda68a013dd6ddbef89",
        "output_xiso_sha256": "32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5",
        "source_profile": "retail_control",
        "source_profile_volume9_sha256": "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
        "source_xiso_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
    },
    "expanded_wall": {
        **common,
        "manifest_sha256": "4fd1d53323c39cef94d7b5ac2a17a4c7d8669abff126f83a5eeda8a451b3e5c0",
        "output_xiso_sha256": "3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16",
        "source_profile": "expanded_wall",
        "source_profile_volume9_sha256": "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad",
        "source_xiso_sha256": "a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c",
    },
}

assert json.loads(os.environ["CONTROL_JSON"]) == expected["retail_control"]
assert json.loads(os.environ["EXPANDED_JSON"]) == expected["expanded_wall"]
PY

# Re-pin all immutable inputs after both full-image verifiers complete.
check_pin "$RETAIL_SOURCE" 6300499968 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_pin "$INDEX" 193710080 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
check_pin "$RETAIL_PACK9" 634941440 779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a
check_pin "$EXPANDED_SOURCE" 6300499968 a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c
check_pin "$EXPANDED_SOURCE_MANIFEST" 3062 80a5361c8b514f7215683d7ae7afdf91a365f4ac64d1736ba76ba349c9d69f95
check_pin "$RECIPE" 1824 3ee45f7b36fae28e51814e7695dc9bbd20d3ea4ac3a722ca53e9bf1264639625
check_pin "$GEOMETRY_PACK9" 634941440 c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad
check_pin "$GEOMETRY_MANIFEST" 4319 8d5454101129b8fc626cb42ac238ca49c6b39a4c0bdd52649fb1eba0a62d6417

echo 'NFL_GROUP36_S42_DISPATCH_XISO_VALIDATION_PASS profiles=2 changed=2 offsets=0x617a8144,0x617a8146 xdvdfs_exact=true default_xbe_exact=true source_unchanged=true unit_tests=4 offline_dispatch=true target=s42nd.iff xemu_loaded=false geometry_visibility=false hardware=false production=false'
