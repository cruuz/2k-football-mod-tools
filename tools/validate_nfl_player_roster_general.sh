#!/usr/bin/env bash
# Validate the generalized NFL 2K5 roster writer end-to-end against the retail
# XISO. Builds a copied XISO in a private temp dir, verifies the planned
# byte-diff (primary name + composed jersey/face shield and secondary jersey), exercises the
# negative guards, then discards the multi-GB output so it is never retained.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

source='ESPN NFL 2K5 (USA).xiso.iso'
audit='reports/assets/nfl2k5_player_roster_audit.json'
temporary=$(mktemp -d /tmp/nfl-player-roster-general-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 -m py_compile tools/nfl_player_roster_general_workflow.py

# --- plan: reproduce the proved Joey fixture + a secondary-pool jersey edit ---
cat >"$temporary/plan.json" <<'PLAN'
{
  "schema": "nfl2k5_player_roster_general_plan/v1",
  "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
  "edits": [
    {"pool": "primary_players", "player_index": 512, "field": "first_name", "value": "Noah"},
    {"pool": "primary_players", "player_index": 512, "field": "last_name", "value": "CodexProof"},
    {"pool": "primary_players", "player_index": 512, "field": "jersey_number", "value": 42},
    {"pool": "primary_players", "player_index": 512, "field": "face_shield", "value": 2},
    {"pool": "secondary_players", "player_index": 0, "field": "jersey_number", "value": 7}
  ]
}
PLAN

python3 tools/nfl_player_roster_general_workflow.py \
  --source-xiso "$source" \
  --output-xiso "$temporary/output.xiso.iso" \
  --plan "$temporary/plan.json" \
  --manifest "$temporary/manifest.json" \
  --audit "$audit" >"$temporary/run.stdout"
grep -q 'NFL_PLAYER_ROSTER_GENERAL_WORKFLOW_OK edits=4 changed=16' "$temporary/run.stdout"

python3 - "$temporary/manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1]))
assert manifest["schema"] == "nfl2k5_player_roster_general_workflow/v1"
claims = manifest["claims"]
assert claims["edit_count"] == 4
assert claims["allowed_changed_byte_count"] == 16
assert claims["all_other_xiso_bytes_identical"] is True
assert claims["layout_identical_copy_only_xiso"] is True
assert claims["roster_membership_changed"] is False
assert claims["position_changed"] is False
assert claims["face_id_changed"] is False
assert claims["face_shield_is_per_player_type_not_uniform_tint"] is True
assert claims["face_shield_authorable_values"] == [0, 1, 2]
assert claims["loaded_save_may_override_disc_seed"] is True
assert claims["original_source_modified"] is False
assert claims["runtime_visibility_proved"] is False
assert manifest["source"]["modified"] is False
edits = {(e["pool"], e["player_index"], e["field"]): e for e in manifest["edits"]}
assert edits[("primary_players", 512, "first_name")]["before"] == "Joey"
assert edits[("primary_players", 512, "first_name")]["after"] == "Noah"
assert edits[("primary_players", 512, "last_name")]["after"] == "CodexProof"
packed = edits[("primary_players", 512, "player_word_20")]
assert packed["packed_fields"] == ["jersey_number", "face_shield"]
assert packed["after"] == {"jersey_number": 42, "face_shield": 2}
sec = edits[("secondary_players", 0, "jersey_number")]
assert sec["before"] == 19 and sec["after"] == 7
print("manifest assertions passed")
PY

# --- negative: secondary-pool NAME edit must be refused (zero-capacity) ---
cat >"$temporary/plan-secondary-name.json" <<'PLAN'
{
  "schema": "nfl2k5_player_roster_general_plan/v1",
  "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
  "edits": [
    {"pool": "secondary_players", "player_index": 0, "field": "first_name", "value": "X"}
  ]
}
PLAN
if python3 tools/nfl_player_roster_general_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg1.xiso.iso" \
    --plan "$temporary/plan-secondary-name.json" --manifest "$temporary/neg1.json" \
    --audit "$audit" >"$temporary/neg1.stdout" 2>"$temporary/neg1.stderr"; then
  echo 'secondary-pool name edit unexpectedly accepted' >&2
  exit 1
fi
grep -q 'zero-capacity' "$temporary/neg1.stderr"
test ! -e "$temporary/neg1.xiso.iso"

# --- negative: name longer than the current decoded span must be refused ---
cat >"$temporary/plan-overflow.json" <<'PLAN'
{
  "schema": "nfl2k5_player_roster_general_plan/v1",
  "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
  "edits": [
    {"pool": "primary_players", "player_index": 512, "field": "first_name", "value": "Christopher"}
  ]
}
PLAN
if python3 tools/nfl_player_roster_general_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg2.xiso.iso" \
    --plan "$temporary/plan-overflow.json" --manifest "$temporary/neg2.json" \
    --audit "$audit" >"$temporary/neg2.stdout" 2>"$temporary/neg2.stderr"; then
  echo 'over-long name unexpectedly accepted' >&2
  exit 1
fi
grep -q 'full-allocation writer' "$temporary/neg2.stderr"
test ! -e "$temporary/neg2.xiso.iso"

# --- negative: wrong source binding must be refused ---
cat >"$temporary/plan-bind.json" <<'PLAN'
{
  "schema": "nfl2k5_player_roster_general_plan/v1",
  "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "edits": [
    {"pool": "primary_players", "player_index": 512, "field": "jersey_number", "value": 42}
  ]
}
PLAN
if python3 tools/nfl_player_roster_general_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg3.xiso.iso" \
    --plan "$temporary/plan-bind.json" --manifest "$temporary/neg3.json" \
    --audit "$audit" >"$temporary/neg3.stdout" 2>"$temporary/neg3.stderr"; then
  echo 'wrong source binding unexpectedly accepted' >&2
  exit 1
fi
grep -q 'not bound to the supported retail source' "$temporary/neg3.stderr"
test ! -e "$temporary/neg3.xiso.iso"

# --- negative: symlink plan must be refused ---
ln -s "$(realpath "$temporary/plan.json")" "$temporary/plan-link.json"
if python3 tools/nfl_player_roster_general_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg4.xiso.iso" \
    --plan "$temporary/plan-link.json" --manifest "$temporary/neg4.json" \
    --audit "$audit" >"$temporary/neg4.stdout" 2>"$temporary/neg4.stderr"; then
  echo 'symlink plan unexpectedly accepted' >&2
  exit 1
fi
grep -q 'plan must not be a symlink' "$temporary/neg4.stderr"
test ! -e "$temporary/neg4.xiso.iso"

python3 -m unittest tests.test_nfl_player_roster_general_workflow

echo 'NFL_PLAYER_ROSTER_GENERAL_VALIDATION_PASS pools=primary+secondary edits=4 changed=16 face_shield=none+clear+dark reserved_3_refused=yes secondary_name_refused=yes overflow_refused=yes binding_refused=yes symlink_refused=yes runtime=false'
