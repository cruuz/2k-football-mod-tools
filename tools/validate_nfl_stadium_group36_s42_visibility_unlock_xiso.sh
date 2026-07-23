#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

RETAIL='ESPN NFL 2K5 (USA).xiso.iso'
INDEX='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
RETAIL_PACK9='extracted/ESPN NFL 2K5 (USA)/vc_53450030/9'
BUILD='build/nfl2k5-stadium-group36-geometry-xiso-20260713'

CONTROL_BASE="$RETAIL"
CONTROL_SOURCE="$BUILD/ESPN-NFL-2K5-s42-dispatch-control.xiso.iso"
CONTROL_SOURCE_MANIFEST="$BUILD/s42-dispatch-control-workflow.json"
CONTROL_OUTPUT="$BUILD/ESPN-NFL-2K5-s42-visible-control.xiso.iso"
CONTROL_MANIFEST="$BUILD/s42-visible-control-workflow.json"

EXPANDED_BASE="$BUILD/ESPN-NFL-2K5-group36-expanded-wall.xiso.iso"
EXPANDED_SOURCE_MANIFEST="$BUILD/expanded-wall-workflow.json"
EXPANDED_SOURCE="$BUILD/ESPN-NFL-2K5-group36-expanded-wall-s42-dispatch.xiso.iso"
EXPANDED_DISPATCH_MANIFEST="$BUILD/expanded-wall-s42-dispatch-workflow.json"
EXPANDED_OUTPUT="$BUILD/ESPN-NFL-2K5-group36-expanded-wall-s42-visible.xiso.iso"
EXPANDED_MANIFEST="$BUILD/expanded-wall-s42-visible-workflow.json"

RECIPE='.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/expanded_local_wall_recipe.json'
GEOMETRY_DIR='.geometry-proof/expanded-wall-output'
GEOMETRY_PACK9="$GEOMETRY_DIR/9"
GEOMETRY_MANIFEST="$GEOMETRY_DIR/manifest.json"

WRITER='tools/nfl_stadium_group36_s42_visibility_unlock_xiso_patch.py'
VERIFIER='tools/nfl_stadium_group36_s42_visibility_unlock_xiso_verify.py'
TEST='tests/test_nfl_stadium_group36_s42_visibility_unlock_xiso.py'
SPEC='reports/specs/nfl2k5_stadium_quick_game_visibility_and_s42_unlock_diagnostic.v1.json'
DOC='docs/research/nfl_stadium_quick_game_visibility_s42.md'

check_pin() {
  local path="$1" size="$2" digest="$3"
  test -f "$path"
  test ! -L "$path"
  test "$(stat -c %s "$path")" = "$size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$digest"
}

python3 -m py_compile "$WRITER" "$VERIFIER" "$TEST"
PYTHONPATH=tools python3 -m unittest \
  tests.test_nfl_stadium_group36_s42_visibility_unlock_xiso >/dev/null

check_pin "$RETAIL" 6300499968 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_pin "$INDEX" 193710080 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
check_pin "$RETAIL_PACK9" 634941440 779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a
check_pin "$CONTROL_SOURCE" 6300499968 32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5
check_pin "$CONTROL_SOURCE_MANIFEST" 3659 e619cf3fa5eae3eea4a09e97f681db96df968041c6746dda68a013dd6ddbef89
check_pin "$CONTROL_OUTPUT" 6300499968 9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40
check_pin "$CONTROL_MANIFEST" 6701 88b4e1e0a5911ba7c2fa6b92d61eaf5b7b47605d9a61d4208cffbbcb1eefbdbe

check_pin "$EXPANDED_BASE" 6300499968 a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c
check_pin "$EXPANDED_SOURCE_MANIFEST" 3062 80a5361c8b514f7215683d7ae7afdf91a365f4ac64d1736ba76ba349c9d69f95
check_pin "$EXPANDED_SOURCE" 6300499968 3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16
check_pin "$EXPANDED_DISPATCH_MANIFEST" 4577 4fd1d53323c39cef94d7b5ac2a17a4c7d8669abff126f83a5eeda8a451b3e5c0
check_pin "$EXPANDED_OUTPUT" 6300499968 f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6
check_pin "$EXPANDED_MANIFEST" 6808 166ba6a28318e289446f0814edd9bcddb28360bd4ad16b13dfa22f82634429b7
check_pin "$RECIPE" 1824 3ee45f7b36fae28e51814e7695dc9bbd20d3ea4ac3a722ca53e9bf1264639625
check_pin "$GEOMETRY_PACK9" 634941440 c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad
check_pin "$GEOMETRY_MANIFEST" 4319 8d5454101129b8fc626cb42ac238ca49c6b39a4c0bdd52649fb1eba0a62d6417

check_pin "$WRITER" 26923 019d37fd50c344d3e6ee833e50d7f9aac064051042882d095a0791b91ae35f66
check_pin "$VERIFIER" 24068 23a714a776286dd1db02547cc7ea03d2d7533a7d67987ff0ae819a2dc6a4cb17
check_pin "$TEST" 6045 b8bda89b5db9cdba117c1ab94f863a1dfb5e592f51f340b422b3f81c501669fb
check_pin "$SPEC" 9888 7078157b445a745328a5057a5ec74135c8e69b06afda982c49ee20fc3a7d8478
check_pin "$DOC" 6059 6af25f1410bf3ad36e9b7fba58c0aeb23d927c5f58b783264f8f5f2c2a70fba5

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

assert spec["schema"] == (
    "nfl2k5_stadium_quick_game_visibility_and_s42_unlock_diagnostic/v1"
)
assert spec["quick_game_visibility"]["exact_condition"] == (
    "skip = (availability(asset_code) == 0) || "
    "(asset_code == s32 && mode not in {0,1,2})"
)
assert spec["quick_game_visibility"]["availability_lookup"]["table_values"][4] == {
    "asset_code": "s42",
    "asset_code_virtual_address": "0x00e70d28",
    "row": 4,
    "unlock_id": "0x0000014b",
}
assert spec["quick_game_visibility"]["unlock_test"]["zero_id_result"] == 1
assert spec["diagnostic_patch"]["actual_changed_byte_count"] == 22
assert spec["diagnostic_patch"]["changed_xiso_offsets_decimal"] == (
    list(range(0x24966c, 0x249680)) + [0xcd58bc, 0xcd58bd]
)
assert spec["diagnostic_patch"]["unlock_word"] == {
    "after_hex": "00000000",
    "before_hex": "4b010000",
    "changed_data_byte_count": 2,
    "file_offset": "0x00a8c8bc",
    "row_index": 4,
    "virtual_address": "0x00a9723c",
    "xiso_absolute_offset": "0x00cd58bc",
}
assert spec["claims"] == {
    "diagnostic_only": True,
    "distribution_ready": False,
    "offline_exact_visibility_condition_proved": True,
    "offline_zero_unlock_id_path_proved": True,
    "original_xbox_hardware_proved": False,
    "production_ready": False,
    "retail_signed_executable_chain_preserved": False,
    "xemu_boot_acceptance_proved": False,
    "xemu_geometry_visibility_proved": False,
    "xemu_stadium_selectability_proved": False,
    "xemu_target_outer_loaded_proved": False,
}

false_claims = {
    "retail_signed_executable_chain_preserved",
    "xemu_boot_acceptance_proved",
    "xemu_stadium_selectability_proved",
    "xemu_target_outer_loaded_proved",
    "xemu_geometry_visibility_proved",
    "original_xbox_hardware_proved",
    "production_ready",
    "distribution_ready",
    "public_editor_exposed",
}
for manifest, profile, output_sha, pack9_sha in (
    (
        control,
        "s42_control",
        "9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40",
        "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    ),
    (
        expanded,
        "s42_expanded_wall",
        "f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6",
        "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad",
    ),
):
    assert manifest["schema"] == (
        "nfl2k5_group36_s42_visibility_unlock_xiso_patch/v1"
    )
    assert manifest["source_profile"] == profile
    assert manifest["output"]["sha256"] == output_sha
    assert manifest["xdvdfs"]["pack0_sha256"] == (
        "57d5ea1703e952cfca9b0f5175b5c9f9bc0bda3eb6676db9f8b6b0e074bddae9"
    )
    assert manifest["xdvdfs"]["pack9_sha256"] == pack9_sha
    assert manifest["patch"]["actual_changed_byte_count"] == 22
    assert manifest["patch"]["actual_changed_byte_offsets"] == (
        list(range(0x24966c, 0x249680)) + [0xcd58bc, 0xcd58bd]
    )
    assert manifest["patch"]["all_other_xiso_bytes_identical"] is True
    assert manifest["xbe"]["output"]["s42_unlock_id"] == 0
    assert manifest["xbe"]["output"]["xbe_sha256"] == (
        "955ddffebbefe9f53d915d7728daf4e6224f946935b3549a1976615cff73dd6b"
    )
    for claim in false_claims:
        assert manifest["claims"][claim] is False

tree = ast.parse(verifier_path.read_text(encoding="utf-8"), filename=str(verifier_path))
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports.update(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imports.add(node.module)
assert "nfl_stadium_group36_s42_visibility_unlock_xiso_patch" not in imports
PY

control_verification="$(PYTHONPATH=tools python3 "$VERIFIER" \
  --source-profile s42_control \
  --source-xiso "$CONTROL_SOURCE" \
  --source-dispatch-manifest "$CONTROL_SOURCE_MANIFEST" \
  --dispatch-base-xiso "$CONTROL_BASE" \
  --output-xiso "$CONTROL_OUTPUT" \
  --manifest "$CONTROL_MANIFEST")"

expanded_verification="$(PYTHONPATH=tools python3 "$VERIFIER" \
  --source-profile s42_expanded_wall \
  --source-xiso "$EXPANDED_SOURCE" \
  --source-dispatch-manifest "$EXPANDED_DISPATCH_MANIFEST" \
  --dispatch-base-xiso "$EXPANDED_BASE" \
  --source-geometry-manifest "$EXPANDED_SOURCE_MANIFEST" \
  --retail-xiso "$RETAIL" \
  --index "$INDEX" \
  --recipe "$RECIPE" \
  --geometry-output-dir "$GEOMETRY_DIR" \
  --output-xiso "$EXPANDED_OUTPUT" \
  --manifest "$EXPANDED_MANIFEST")"

CONTROL_JSON="$control_verification" EXPANDED_JSON="$expanded_verification" python3 - <<'PY'
from __future__ import annotations

import json
import os


control = json.loads(os.environ["CONTROL_JSON"])
expanded = json.loads(os.environ["EXPANDED_JSON"])
for value, profile, source_sha, output_sha, manifest_sha, pack9_sha in (
    (
        control,
        "s42_control",
        "32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5",
        "9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40",
        "88b4e1e0a5911ba7c2fa6b92d61eaf5b7b47605d9a61d4208cffbbcb1eefbdbe",
        "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    ),
    (
        expanded,
        "s42_expanded_wall",
        "3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16",
        "f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6",
        "166ba6a28318e289446f0814edd9bcddb28360bd4ad16b13dfa22f82634429b7",
        "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad",
    ),
):
    assert value["schema"] == (
        "nfl2k5_group36_s42_visibility_unlock_xiso_verify/v1"
    )
    assert value["source_profile"] == profile
    assert value["source_xiso_sha256"] == source_sha
    assert value["output_xiso_sha256"] == output_sha
    assert value["manifest_sha256"] == manifest_sha
    assert value["changed_byte_count"] == 22
    assert value["changed_byte_offsets"] == (
        list(range(0x24966c, 0x249680)) + [0xcd58bc, 0xcd58bd]
    )
    assert value["source_pack0_sha256"] == value["output_pack0_sha256"] == (
        "57d5ea1703e952cfca9b0f5175b5c9f9bc0bda3eb6676db9f8b6b0e074bddae9"
    )
    assert value["source_pack9_sha256"] == value["output_pack9_sha256"] == pack9_sha
    assert value["default_xbe_output_sha256"] == (
        "955ddffebbefe9f53d915d7728daf4e6224f946935b3549a1976615cff73dd6b"
    )
    assert value["xemu_boot_acceptance_proved"] is False
    assert value["xemu_stadium_selectability_proved"] is False
    assert value["xemu_target_outer_loaded_proved"] is False
    assert value["xemu_geometry_visibility_proved"] is False
    assert value["hardware_proved"] is False
    assert value["production_ready"] is False
PY

# Re-pin every large source/output after independent verification.
check_pin "$RETAIL" 6300499968 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_pin "$CONTROL_SOURCE" 6300499968 32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5
check_pin "$CONTROL_OUTPUT" 6300499968 9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40
check_pin "$EXPANDED_BASE" 6300499968 a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c
check_pin "$EXPANDED_SOURCE" 6300499968 3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16
check_pin "$EXPANDED_OUTPUT" 6300499968 f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6

echo 'NFL_GROUP36_S42_VISIBILITY_UNLOCK_XISO_VALIDATION_PASS profiles=2 changed=22 data=2 digest=20 xdvdfs_exact=true assets_exact=true xemu_boot=false selector=false loaded=false geometry=false hardware=false production=false'
