#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

OLD_PROJECT=.codex-tmp/unified-six-smoke-project.json
OLD_OUTPUT=.codex-tmp/nfl2k5-unified-six-proof-20260712.xiso.iso
OLD_MANIFEST=.codex-tmp/nfl2k5-unified-six-proof-20260712.manifest.json
OLD_ARTIFACTS=.codex-tmp/nfl2k5-unified-six-proof-20260712-artifacts
PROJECT=.codex-tmp/unified-nine-family-proof-project.json
OUTPUT=.codex-tmp/nfl2k5-unified-nine-family-proof-20260712.xiso.iso
MANIFEST=.codex-tmp/nfl2k5-unified-nine-family-proof-20260712.manifest.json
ARTIFACTS=.codex-tmp/nfl2k5-unified-nine-family-proof-20260712-artifacts
NEW_PROJECT=.codex-tmp/unified-eleven-family-proof-project.json
NEW_OUTPUT=.codex-tmp/nfl2k5-unified-eleven-family-proof-20260712.xiso.iso
NEW_MANIFEST=.codex-tmp/nfl2k5-unified-eleven-family-proof-20260712.manifest.json
NEW_ARTIFACTS=.codex-tmp/nfl2k5-unified-eleven-family-proof-20260712-artifacts

verify_mode() {
  local output=$1
  if [[ ! -e "$output" && ! -L "$output" ]]; then
    printf '%s\n' --virtual-output
  fi
}

python3 tools/test_nfl2k5_visual_mod_project.py
python3 tools/nfl2k5_visual_mod_project.py validate --project "$OLD_PROJECT" >/dev/null
python3 tools/nfl2k5_visual_mod_project.py validate --project "$PROJECT" >/dev/null
python3 tools/nfl2k5_visual_mod_project.py validate --project "$NEW_PROJECT" >/dev/null
mapfile -t OLD_VERIFY_MODE < <(verify_mode "$OLD_OUTPUT")
mapfile -t VERIFY_MODE < <(verify_mode "$OUTPUT")
mapfile -t NEW_VERIFY_MODE < <(verify_mode "$NEW_OUTPUT")
python3 tools/nfl2k5_visual_mod_project.py verify \
  --project "$OLD_PROJECT" \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso "$OLD_OUTPUT" \
  --manifest "$OLD_MANIFEST" \
  --artifact-dir "$OLD_ARTIFACTS" \
  "${OLD_VERIFY_MODE[@]}"
python3 tools/nfl2k5_visual_mod_project.py verify \
  --project "$PROJECT" \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso "$OUTPUT" \
  --manifest "$MANIFEST" \
  --artifact-dir "$ARTIFACTS" \
  "${VERIFY_MODE[@]}"
python3 tools/nfl2k5_visual_mod_project.py verify \
  --project "$NEW_PROJECT" \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso "$NEW_OUTPUT" \
  --manifest "$NEW_MANIFEST" \
  --artifact-dir "$NEW_ARTIFACTS" \
  "${NEW_VERIFY_MODE[@]}"

python3 - "$OLD_MANIFEST" "$MANIFEST" "$NEW_MANIFEST" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

old_path, manifest_path, new_manifest_path = map(Path, sys.argv[1:])
old_payload = old_path.read_bytes()
old = json.loads(old_payload)
assert old_payload == (json.dumps(old, indent=2, sort_keys=True) + "\n").encode()
assert old["schema"] == "nfl2k5_visual_mod_build/v1"
assert old["project"]["edit_count"] == old["patch"]["span_count"] == 6
assert old["patch"]["changed_byte_count"] == 275880
assert old["output"]["xiso_sha256"] == (
    "6ee1db02af9c82f891d21e8ef13d9ac1f8e030925c511e6c442e5d58e6eac995"
)
assert hashlib.sha256(old_payload).hexdigest() == (
    "fa63a372d8265f949a88a3d12a51f04c9843e3432d07c40276386580d76a2a8a"
)

payload = manifest_path.read_bytes()
value = json.loads(payload)
assert payload == (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
assert value["schema"] == "nfl2k5_visual_mod_build/v1"
assert value["project"]["edit_count"] == 11
assert value["patch"]["span_count"] == 14
assert len({edit["kind"] for edit in value["edits"]}) == 9
assert value["patch"]["selected_span_bytes"] == 427612
assert value["patch"]["changed_byte_count"] == 411101
assert value["patch"]["changed_offsets_u64le_sha256"] == (
    "3e9e2e47b6cd1b881ab5815e760b1818658bec7140f1f29347f43966d24b2aa2"
)
assert value["patch"]["all_bytes_outside_selected_spans_identical"] is True
assert value["patch"]["all_selected_spans_equal_validated_replacements"] is True
assert value["output"]["xiso_sha256"] == (
    "c46f4036bbd3629a8932c2078b4f62ec501f8ef013acb279514212c332f446f1"
)
assert value["output"]["artifact_file_count"] == 69
assert value["xdvdfs"]["tree_identical_after_patch"] is True
assert value["xdvdfs"]["default_xbe_sha256"] == (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
assert value["claims"]["no_intermediate_xiso_copies"] is True
assert value["claims"]["live_face_shape_geometry_modified"] is False
assert value["claims"]["create_team_field_art_is_static_live_field_resource"] is True
assert value["claims"]["create_team_menu_or_team_select_imagery_modified"] is False
assert value["claims"]["team_identity_fixed_size_strings_only"] is True
assert value["claims"]["team_identity_art_code_modified"] is False
assert value["claims"]["team_identity_roster_pointer_or_membership_modified"] is False
assert value["claims"]["team_identity_stadium_modified"] is False
assert value["claims"]["team_identity_xbe_color_modified"] is False
assert value["claims"]["team_identity_relocation_or_allocation_modified"] is False
assert value["claims"]["runtime_visibility_proved"] is False
assert value["canonical_inputs"]["compatibility_reports"]["live_face"]["sha256"] == (
    "3929bbab1240e9d53c5ba836e189226ccbe84cbe02c565dc86bc0bf019bf4a0e"
)
assert value["canonical_inputs"]["compatibility_reports"][
    "create_team_field_art"]["sha256"] == (
    "15535bad354b8f7d58c9ce77fc5d91f609256719759c69e85980241e3578e238"
)
assert value["canonical_inputs"]["compatibility_reports"][
    "team_identity"]["sha256"] == (
    "9ddae13f0234b628e28fa10d6935b73e1447362eb41701dc9c45f9dc0a188d7d"
)
identity = [edit for edit in value["edits"] if edit["kind"] == "team_identity"]
assert len(identity) == 4
assert {edit["selector"] for edit in identity} == {
    "team:18:nickname", "team:18:abbreviation",
    "team:18:city", "team:18:city_abbreviation",
}
assert sum(edit["replacement"]["relative_changed_byte_count"]
           for edit in identity) == 17
assert hashlib.sha256(payload).hexdigest() == (
    "49060e984bb93782beb82a9e62fdcb0b5485f13e7185ac481ae4e43f4c03182e"
)

new_payload = new_manifest_path.read_bytes()
new = json.loads(new_payload)
assert new_payload == (json.dumps(new, indent=2, sort_keys=True) + "\n").encode()
assert new["schema"] == "nfl2k5_visual_mod_build/v1"
assert new["project"]["edit_count"] == 13
assert new["project"]["sha256"] == (
    "6ee360a669cc11f45f50486de5835c7e94f14539a28b3b942e0155ad61d77d5b"
)
assert new["patch"]["span_count"] == 19
assert len({edit["kind"] for edit in new["edits"]}) == 11
assert new["patch"]["selected_span_bytes"] == 445216
assert new["patch"]["changed_byte_count"] == 428469
assert new["patch"]["changed_offsets_u64le_sha256"] == (
    "f6721110040adee505d99f6b862f61a16459bab9452b695f68b485057c0fa82c"
)
assert new["patch"]["all_bytes_outside_selected_spans_identical"] is True
assert new["patch"]["all_selected_spans_equal_validated_replacements"] is True
assert new["patch"]["selected_spans_non_overlapping"] is True
assert new["output"]["xiso_sha256"] == (
    "67b7d52d8fc7fa84eb3cdd86f53a0e6009175d5c34cfbd5782354de478342376"
)
assert new["output"]["artifact_file_count"] == 75
assert new["canonical_inputs"]["compatibility_reports"]["player_roster"][
    "sha256"] == (
        "795336ad0092e6ba6c806e314bb7515ecc0e11103bd889557229f4f1a92451c2"
    )
assert new["canonical_inputs"]["compatibility_reports"]["player_portrait"][
    "sha256"] == (
        "f1eee623e5d9d026f5d85b6a6b6fb75287a655ccc034626477dadcf19b74e7bc"
    )
roster = [edit for edit in new["edits"] if edit["kind"] == "player_roster"]
assert len(roster) == 3
assert {edit["selector"] for edit in roster} == {
    "primary-player:512:first_name",
    "primary-player:512:last_name",
    "primary-player:512:jersey_number",
}
assert sum(edit["replacement"]["relative_changed_byte_count"]
           for edit in roster) == 14
portrait = [edit for edit in new["edits"] if edit["kind"] == "player_portrait"]
assert len(portrait) == 2
assert [edit["selector"] for edit in portrait] == [
    "portrait:4070:segment:1-of-2", "portrait:4070:segment:2-of-2",
]
assert [edit["target"]["pack_path"] for edit in portrait] == [
    "vc_53450030/3", "vc_53450030/4",
]
assert sum(edit["replacement"]["span_size"] for edit in portrait) == 17568
assert sum(edit["replacement"]["relative_changed_byte_count"]
           for edit in portrait) == 17354
assert new["claims"]["player_roster_fixed_size_identity_and_jersey_only"] is True
assert new["claims"]["player_roster_team_membership_modified"] is False
assert new["claims"]["player_roster_team_count_modified"] is False
assert new["claims"]["player_roster_serialized_pointer_modified"] is False
assert new["claims"]["player_roster_position_modified"] is False
assert new["claims"]["player_roster_face_id_modified"] is False
assert new["claims"]["player_roster_ratings_modified"] is False
assert new["claims"]["player_roster_all_other_bits_modified"] is False
assert new["claims"]["player_portrait_cross_pack_segments_proved"] is True
assert new["claims"]["player_portrait_action_photo_family_modified"] is False
assert new["claims"]["player_portrait_live_3d_face_family_modified"] is False
assert new["claims"]["public_project_schema_exposes_raw_offsets"] is False
assert new["claims"]["speculative_executable_or_gameplay_patch_applied"] is False
assert new["claims"]["runtime_visibility_proved"] is False
assert new["xdvdfs"]["tree_identical_after_patch"] is True
assert new["xdvdfs"]["default_xbe_sha256"] == (
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
)
assert hashlib.sha256(new_payload).hexdigest() == (
    "408e4106f328ca5476d4b49c6c54c2fb1ce20d49138f1fe3d7218d516e0f8e15"
)
PY

printf '%s\n' \
  'NFL2K5_VISUAL_MOD_PROJECT_VALIDATION_PASS schema=v1 families=11 project_edits=13 spans=19 changed=428469 old_v1_compatible=true nine_family_compatible=true shap_read_only=true team_identity_fixed_size=true player_roster_fixed_size=true player_portrait_cross_pack=true executable_patches=false xdvdfs_identical=true default_xbe_unchanged=true source_unchanged=true absent_outputs_virtualized=true no_intermediate_xisos=true runtime=false'
