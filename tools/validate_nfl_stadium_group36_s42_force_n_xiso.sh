#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

BUILD='build/nfl2k5-stadium-group36-geometry-xiso-20260713'
RETAIL='ESPN NFL 2K5 (USA).xiso.iso'
INDEX='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
RETAIL_XBE='extracted/ESPN NFL 2K5 (USA)/default.xbe'

CONTROL_SOURCE="$BUILD/ESPN-NFL-2K5-s42-visible-control.xiso.iso"
CONTROL_SOURCE_MANIFEST="$BUILD/s42-visible-control-workflow.json"
CONTROL_VISIBILITY_BASE="$BUILD/ESPN-NFL-2K5-s42-dispatch-control.xiso.iso"
CONTROL_DISPATCH_MANIFEST="$BUILD/s42-dispatch-control-workflow.json"
CONTROL_OUTPUT="$BUILD/ESPN-NFL-2K5-s42-visible-night-control.xiso.iso"
CONTROL_MANIFEST="$BUILD/s42-visible-night-control-workflow.json"

EXPANDED_SOURCE="$BUILD/ESPN-NFL-2K5-group36-expanded-wall-s42-visible.xiso.iso"
EXPANDED_SOURCE_MANIFEST="$BUILD/expanded-wall-s42-visible-workflow.json"
EXPANDED_VISIBILITY_BASE="$BUILD/ESPN-NFL-2K5-group36-expanded-wall-s42-dispatch.xiso.iso"
EXPANDED_DISPATCH_MANIFEST="$BUILD/expanded-wall-s42-dispatch-workflow.json"
EXPANDED_DISPATCH_BASE="$BUILD/ESPN-NFL-2K5-group36-expanded-wall.xiso.iso"
EXPANDED_GEOMETRY_MANIFEST="$BUILD/expanded-wall-workflow.json"
EXPANDED_OUTPUT="$BUILD/ESPN-NFL-2K5-group36-expanded-wall-s42-visible-night.xiso.iso"
EXPANDED_MANIFEST="$BUILD/expanded-wall-s42-visible-night-workflow.json"

RECIPE='.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/expanded_local_wall_recipe.json'
GEOMETRY_DIR='.geometry-proof/expanded-wall-output'
GEOMETRY_PACK9="$GEOMETRY_DIR/9"
GEOMETRY_MANIFEST="$GEOMETRY_DIR/manifest.json"

WRITER='tools/nfl_stadium_group36_s42_force_n_xiso_patch.py'
VERIFIER='tools/nfl_stadium_group36_s42_force_n_xiso_verify.py'
UPSTREAM_VERIFIER='tools/nfl_stadium_group36_s42_visibility_unlock_xiso_verify.py'
TEST='tests/test_nfl_stadium_group36_s42_force_n_xiso.py'
SPEC='reports/specs/nfl2k5_group36_s42_force_n_runtime_shim.v1.json'
DOC='docs/research/nfl_group36_s42_force_n_runtime_shim.md'

check_pin() {
  local path="$1" size="$2" digest="$3"
  test -f "$path"
  test ! -L "$path"
  test "$(stat -c %s "$path")" = "$size"
  test "$(sha256sum "$path" | cut -d' ' -f1)" = "$digest"
}

python3 -m py_compile "$WRITER" "$VERIFIER" "$TEST"
PYTHONPATH=tools python3 -m unittest tests.test_nfl_stadium_group36_s42_force_n_xiso >/dev/null

check_pin "$RETAIL" 6300499968 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_pin "$INDEX" 193710080 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
check_pin "$RETAIL_XBE" 11948032 73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9

check_pin "$CONTROL_SOURCE" 6300499968 9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40
check_pin "$CONTROL_SOURCE_MANIFEST" 6701 88b4e1e0a5911ba7c2fa6b92d61eaf5b7b47605d9a61d4208cffbbcb1eefbdbe
check_pin "$CONTROL_VISIBILITY_BASE" 6300499968 32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5
check_pin "$CONTROL_DISPATCH_MANIFEST" 3659 e619cf3fa5eae3eea4a09e97f681db96df968041c6746dda68a013dd6ddbef89
check_pin "$CONTROL_OUTPUT" 6300499968 863ba00df855efdf54b85d568516b1ed0f7bbd33ddb77096ce3e16da4e702383
check_pin "$CONTROL_MANIFEST" 7227 cb503cc117909eb78048dc96f68a1b1ccd12c6223781eba6742e6a0c12cff5db

check_pin "$EXPANDED_SOURCE" 6300499968 f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6
check_pin "$EXPANDED_SOURCE_MANIFEST" 6808 166ba6a28318e289446f0814edd9bcddb28360bd4ad16b13dfa22f82634429b7
check_pin "$EXPANDED_VISIBILITY_BASE" 6300499968 3c2917114ec7005e21c24c7fdf971adfdd54c051e89ecf2c4f93beb64a73dc16
check_pin "$EXPANDED_DISPATCH_MANIFEST" 4577 4fd1d53323c39cef94d7b5ac2a17a4c7d8669abff126f83a5eeda8a451b3e5c0
check_pin "$EXPANDED_DISPATCH_BASE" 6300499968 a17ce0bd1f37d3c361245334586346a5f43b5a9374ffe05fe5e41b101a10137c
check_pin "$EXPANDED_GEOMETRY_MANIFEST" 3062 80a5361c8b514f7215683d7ae7afdf91a365f4ac64d1736ba76ba349c9d69f95
check_pin "$EXPANDED_OUTPUT" 6300499968 d41c44882919a00282c184fcc85b4ec139e17b48ee7681960808cc14947bab72
check_pin "$EXPANDED_MANIFEST" 7287 a003d7f04e23c291e28c577923d332080f74bca8a749881972325a82f285a97b
check_pin "$RECIPE" 1824 3ee45f7b36fae28e51814e7695dc9bbd20d3ea4ac3a722ca53e9bf1264639625
check_pin "$GEOMETRY_PACK9" 634941440 c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad
check_pin "$GEOMETRY_MANIFEST" 4319 8d5454101129b8fc626cb42ac238ca49c6b39a4c0bdd52649fb1eba0a62d6417

check_pin "$WRITER" 29616 ab22199039bd6b3b525f2ccdeadc4d58aeb4027c1c35a3dde45e4fd287215015
check_pin "$VERIFIER" 28657 837031a2f7170ac2ebc9aa5d930205a56cddb8c89036ccd5b3707210dee6efa1
check_pin "$UPSTREAM_VERIFIER" 24068 23a714a776286dd1db02547cc7ea03d2d7533a7d67987ff0ae819a2dc6a4cb17
check_pin "$TEST" 6283 4b501ae2ac00a5ea973bf41a206d99f2fe88467e5271ea798b383d16e3b14193
check_pin "$SPEC" 7792 92f7dcc820cc4b6d4e8049737a2aa4a9d4b228e09531f22e34d48cd5c7576048
check_pin "$DOC" 5410 6cf0a53974e6cbb56a73bc3bd610bf662ae04331b16bfc8082f193379612ac73

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

assert spec["schema"] == "nfl2k5_group36_s42_force_n_runtime_shim/v1"
assert spec["instruction_patch"]["changed_byte"] == {
    "after_hex": "00",
    "before_hex": "05",
    "default_xbe_file_offset": "0x00052c61",
    "guest_virtual_address": "0x00062c61",
    "xiso_absolute_offset": "0x0029bc61",
}
assert spec["xdvdfs_transport"]["allowed_changed_byte_offsets_decimal"] == [
    *range(0x249394, 0x2493A8), 0x29BC61,
]
assert spec["claims"]["offline_force_n_dataflow_proved"] is True
for key in (
    "original_xbox_hardware_proved", "production_ready", "public_editor_exposed",
    "retail_signed_executable_chain_preserved", "xemu_boot_acceptance_proved",
    "xemu_geometry_visibility_proved", "xemu_stadium_selectability_proved",
    "xemu_target_outer_loaded_proved",
):
    assert spec["claims"][key] is False

for manifest, profile, source_sha, output_sha, visibility_manifest_sha in (
    (
        control,
        "s42_control",
        "9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40",
        "863ba00df855efdf54b85d568516b1ed0f7bbd33ddb77096ce3e16da4e702383",
        "88b4e1e0a5911ba7c2fa6b92d61eaf5b7b47605d9a61d4208cffbbcb1eefbdbe",
    ),
    (
        expanded,
        "s42_expanded_wall",
        "f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6",
        "d41c44882919a00282c184fcc85b4ec139e17b48ee7681960808cc14947bab72",
        "166ba6a28318e289446f0814edd9bcddb28360bd4ad16b13dfa22f82634429b7",
    ),
):
    assert manifest["schema"] == "nfl2k5_group36_s42_force_n_xiso_patch/v1"
    assert manifest["source_profile"] == profile
    assert manifest["source"]["sha256_before"] == source_sha
    assert manifest["source"]["sha256_after"] == source_sha
    assert manifest["source_proof"]["source_visibility_manifest_sha256"] == visibility_manifest_sha
    assert manifest["source_proof"]["source_visibility_changed_byte_count"] == 22
    assert manifest["output"]["sha256"] == output_sha
    assert manifest["patch"]["actual_changed_byte_count"] == 21
    assert manifest["patch"]["actual_changed_byte_offsets"] == [
        *range(0x249394, 0x2493A8), 0x29BC61,
    ]
    assert manifest["patch"]["semantic_code_byte_count"] == 1
    assert manifest["patch"]["required_section_digest_byte_count"] == 20
    assert manifest["patch"]["all_other_xiso_bytes_identical"] is True
    assert manifest["xbe"]["source"]["xbe_sha256"] == (
        "955ddffebbefe9f53d915d7728daf4e6224f946935b3549a1976615cff73dd6b"
    )
    assert manifest["xbe"]["output"]["xbe_sha256"] == (
        "c6abdd77be89594ee19dbfd8dbfa300b592a5a2ed1af2276e5e132678e50cc27"
    )
    assert manifest["xbe"]["output"]["visibility_unlock_bytes"] == "00000000"
    assert manifest["claims"]["s42_visibility_unlock_preserved"] is True
    assert manifest["claims"]["weather_suffix_instruction_and_value_preserved"] is True
    assert manifest["claims"]["retail_signed_executable_chain_preserved"] is False
    assert manifest["claims"]["xemu_target_outer_loaded_proved"] is False
    assert manifest["claims"]["xemu_geometry_visibility_proved"] is False

tree = ast.parse(verifier_path.read_text(encoding="utf-8"), filename=str(verifier_path))
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports.update(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imports.add(node.module)
assert "nfl_stadium_group36_s42_force_n_xiso_patch" not in imports
PY

control_verification="$(PYTHONPATH=tools python3 "$VERIFIER" \
  --source-profile s42_control \
  --source-xiso "$CONTROL_SOURCE" \
  --source-visibility-manifest "$CONTROL_SOURCE_MANIFEST" \
  --visibility-base-xiso "$CONTROL_VISIBILITY_BASE" \
  --source-dispatch-manifest "$CONTROL_DISPATCH_MANIFEST" \
  --dispatch-base-xiso "$RETAIL" \
  --output-xiso "$CONTROL_OUTPUT" \
  --manifest "$CONTROL_MANIFEST")"

expanded_verification="$(PYTHONPATH=tools python3 "$VERIFIER" \
  --source-profile s42_expanded_wall \
  --source-xiso "$EXPANDED_SOURCE" \
  --source-visibility-manifest "$EXPANDED_SOURCE_MANIFEST" \
  --visibility-base-xiso "$EXPANDED_VISIBILITY_BASE" \
  --source-dispatch-manifest "$EXPANDED_DISPATCH_MANIFEST" \
  --dispatch-base-xiso "$EXPANDED_DISPATCH_BASE" \
  --source-geometry-manifest "$EXPANDED_GEOMETRY_MANIFEST" \
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
for result, profile, source_sha, output_sha, manifest_sha, pack9 in (
    (
        control,
        "s42_control",
        "9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40",
        "863ba00df855efdf54b85d568516b1ed0f7bbd33ddb77096ce3e16da4e702383",
        "cb503cc117909eb78048dc96f68a1b1ccd12c6223781eba6742e6a0c12cff5db",
        "779b37455fc44cd7eb60674b926d7ccaf9cd6bd9d894157a1d68119281790c7a",
    ),
    (
        expanded,
        "s42_expanded_wall",
        "f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6",
        "d41c44882919a00282c184fcc85b4ec139e17b48ee7681960808cc14947bab72",
        "a003d7f04e23c291e28c577923d332080f74bca8a749881972325a82f285a97b",
        "c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad",
    ),
):
    assert result["schema"] == "nfl2k5_group36_s42_force_n_xiso_verify/v1"
    assert result["source_profile"] == profile
    assert result["source_xiso_sha256"] == source_sha
    assert result["output_xiso_sha256"] == output_sha
    assert result["manifest_sha256"] == manifest_sha
    assert result["source_profile_volume9_sha256"] == pack9
    assert result["changed_byte_offsets"] == [*range(0x249394, 0x2493A8), 0x29BC61]
    assert result["changed_byte_count"] == 21
    assert result["source_default_xbe_sha256"] == "955ddffebbefe9f53d915d7728daf4e6224f946935b3549a1976615cff73dd6b"
    assert result["output_default_xbe_sha256"] == "c6abdd77be89594ee19dbfd8dbfa300b592a5a2ed1af2276e5e132678e50cc27"
    assert result["text_section_digest_exact"] is True
    assert result["weather_dataflow_preserved"] is True
    assert result["xdvdfs_tree_exact"] is True
    assert result["source_unchanged"] is True
    assert result["rsa_signed_header_chain_preserved"] is False
    assert result["xemu_boot_acceptance_proved"] is False
    assert result["xemu_target_outer_loaded_proved"] is False
    assert result["xemu_geometry_visibility_proved"] is False
    assert result["hardware_proved"] is False
    assert result["production_ready"] is False
PY

check_pin "$RETAIL" 6300499968 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_pin "$INDEX" 193710080 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
check_pin "$CONTROL_SOURCE" 6300499968 9070f267b585758c1a274c03baf6c925872b061c9f6a47e2ddfba3f5176fab40
check_pin "$EXPANDED_SOURCE" 6300499968 f098af98efd2c545f4eea15bdb8cddac0668bd53eb77ab2077b592d465646ea6
check_pin "$RECIPE" 1824 3ee45f7b36fae28e51814e7695dc9bbd20d3ea4ac3a722ca53e9bf1264639625
check_pin "$GEOMETRY_PACK9" 634941440 c4ad271186e47389d00bd4131866548c8eec2320770bfeb5ce9f9ae44f3d5bad
check_pin "$GEOMETRY_MANIFEST" 4319 8d5454101129b8fc626cb42ac238ca49c6b39a4c0bdd52649fb1eba0a62d6417

echo 'NFL_GROUP36_S42_FORCE_N_XISO_VALIDATION_PASS profiles=2 source_visibility_proved=true semantic_code_bytes=1 digest_bytes=20 total_changed=21 code_offset=0x29bc61 weather_preserved=true target_clear=s42nd.iff xdvdfs_exact=true source_unchanged=true unit_tests=8 xemu_boot=false target_loaded=false geometry_visibility=false hardware=false production=false'
