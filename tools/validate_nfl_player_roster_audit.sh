#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

audit='reports/assets/nfl2k5_player_roster_audit.json'
players='reports/assets/nfl2k5_player_roster_players.tsv'
bindings='reports/assets/nfl2k5_player_rating_ui_bindings.tsv'
source='ESPN NFL 2K5 (USA).xiso.iso'
output='build/nfl2k5-player-roster-workflow-20260712/ESPN-NFL-2K5-Noah-CodexProof-42.xiso.iso'
manifest='build/nfl2k5-player-roster-workflow-20260712/workflow.json'
temporary=$(mktemp -d /tmp/nfl-player-roster-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

verify_mode=()
if [[ ! -e "$output" && ! -L "$output" ]]; then
  verify_mode=(--virtual-output)
fi

python3 -m py_compile \
  tools/nfl_player_roster_audit.py \
  tools/nfl_player_roster_xiso_workflow.py \
  tools/nfl_player_roster_xiso_verify.py
python3 -m unittest -v \
  tests.test_nfl_player_roster_general_workflow \
  tests.mod_editor.test_nfl2k5_face_shield_registry

python3 tools/nfl_player_roster_audit.py \
  --output "$temporary/audit.json" \
  --players-tsv "$temporary/players.tsv" \
  --bindings-tsv "$temporary/bindings.tsv" >/dev/null
cmp "$temporary/audit.json" "$audit"
cmp "$temporary/players.tsv" "$players"
cmp "$temporary/bindings.tsv" "$bindings"

python3 - <<'PY'
import csv
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

assert digest("reports/assets/nfl2k5_player_roster_audit.json") == \
    "795336ad0092e6ba6c806e314bb7515ecc0e11103bd889557229f4f1a92451c2"
assert digest("reports/assets/nfl2k5_player_roster_players.tsv") == \
    "6c15cf812299efe9163769a68339af09d480b06afd443bec4e245269f39f0dd6"
assert digest("reports/assets/nfl2k5_player_rating_ui_bindings.tsv") == \
    "057a4b938efc11672b0e28f2b98bc8116540e981097e31bd999bd5c24fc6b3ae"
assert digest("build/nfl2k5-player-roster-workflow-20260712/workflow.json") == \
    "447bec94f7bc39fc96038620cd9a4c60dafc5dcd12337b62f2c59406b8186605"

report = json.loads(Path("reports/assets/nfl2k5_player_roster_audit.json").read_text())
assert report["schema"] == "nfl2k5_player_roster_audit/v1"
assert report["summary"] == {
    "player_count": 2547,
    "position_count": 17,
    "primary_player_count": 2479,
    "promoted_stable_rating_count": 3,
    "proof_jersey": "3 -> 42",
    "proof_player": "Joey Harrington -> Noah CodexProof",
    "rating_ui_binding_count": 204,
    "secondary_player_count": 68,
    "team_count": 52,
}
assert report["layout"]["primary_players"] == {"count": 2479, "offset": 44968, "stride": 84}
assert report["layout"]["secondary_players"] == {"count": 68, "offset": 253204, "stride": 84}
assert report["membership"]["active_membership_pointer_count"] == 2634
assert report["membership"]["all_active_slots_select_exact_0x54_player_boundaries"] is True
assert report["membership"]["all_unused_slots_null"] is True
assert [row["abbreviation"] for row in report["position_enum"]] == [
    "QB", "K", "P", "WR", "CB", "FS", "SS", "RB", "FB",
    "TE", "OLB", "ILB", "C", "G", "T", "DT", "DE",
]
assert report["stable_rating_fields"] == {
    "aggression": {
        "label": "AGGRESSION", "occurrences": 11, "offset": 81,
        "position_codes": [4, 5, 6, 8, 10, 11, 12, 13, 14, 15, 16],
    },
    "consistency": {
        "label": "CONSISTENCY", "occurrences": 16, "offset": 80,
        "position_codes": [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
    },
    "speed": {
        "label": "SPEED", "occurrences": 16, "offset": 54,
        "position_codes": [0, 1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16],
    },
}
assert len(report["rating_ui_bindings"]) == 204
joey = next(row for row in report["players"]
            if row["pool"] == "primary_players" and row["index"] == 512)
assert (joey["first_name"], joey["last_name"], joey["jersey_number"],
        joey["position"], joey["face_id"], joey["team_indices"]) == \
       ("Joey", "Harrington", 3, "QB", 3593, [18])
assert joey["record_body_offset"] == 0x157A8
assert joey["first_name_known_pointer_reference_count"] == 1
assert joey["last_name_known_pointer_reference_count"] == 1
proof = report["safe_fixed_size_proof"]
assert proof["after"] == {
    "face_id": 3593, "first_name": "Noah", "jersey_number": 42,
    "last_name": "CodexProof", "position": "QB", "team_indices": [18],
}
assert proof["runtime_visibility_proved"] is False
assert report["claims"]["all_28_rating_semantics_proved"] is False
assert report["claims"]["save_container_schema_proved"] is False
assert report["claims"]["originals_modified"] is False

with Path("reports/assets/nfl2k5_player_roster_players.tsv").open(newline="") as stream:
    player_rows = list(csv.DictReader(stream, delimiter="\t"))
with Path("reports/assets/nfl2k5_player_rating_ui_bindings.tsv").open(newline="") as stream:
    binding_rows = list(csv.DictReader(stream, delimiter="\t"))
assert len(player_rows) == 2547 and len(binding_rows) == 204
joey_tsv = next(row for row in player_rows
                if row["pool"] == "primary_players" and row["player_index"] == "512")
assert (joey_tsv["first_name"], joey_tsv["last_name"], joey_tsv["position"],
        joey_tsv["jersey_number"], joey_tsv["face_id"], joey_tsv["team_indices"]) == \
       ("Joey", "Harrington", "QB", "3", "3593", "18")
assert {row["raw_player_byte_offset"] for row in binding_rows if row["label"] == "SPEED"} == {"0x36"}
assert {row["raw_player_byte_offset"] for row in binding_rows if row["label"] == "CONSISTENCY"} == {"0x50"}
assert {row["raw_player_byte_offset"] for row in binding_rows if row["label"] == "AGGRESSION"} == {"0x51"}
PY

python3 tools/nfl_player_roster_xiso_verify.py \
  --source-xiso "$source" \
  --output-xiso "$output" \
  "${verify_mode[@]}" \
  --manifest "$manifest" \
  --audit "$audit"

ln -s "$source" "$temporary/source-link.iso"
if python3 tools/nfl_player_roster_xiso_verify.py \
    --source-xiso "$temporary/source-link.iso" \
    --output-xiso "$output" \
    "${verify_mode[@]}" \
    --manifest "$manifest" \
    --audit "$audit" >"$temporary/source-link.stdout" 2>"$temporary/source-link.stderr"; then
  echo 'symlink source unexpectedly accepted' >&2
  exit 1
fi
grep -q 'symlink refused' "$temporary/source-link.stderr"

ln -s "$(realpath "$manifest")" "$temporary/manifest-link.json"
if python3 tools/nfl_player_roster_xiso_verify.py \
    --source-xiso "$source" \
    --output-xiso "$output" \
    "${verify_mode[@]}" \
    --manifest "$temporary/manifest-link.json" \
    --audit "$audit" >"$temporary/manifest-link.stdout" 2>"$temporary/manifest-link.stderr"; then
  echo 'symlink manifest unexpectedly accepted' >&2
  exit 1
fi
grep -q 'manifest symlink refused' "$temporary/manifest-link.stderr"

ln -s "$(realpath "$audit")" "$temporary/audit-link.json"
if python3 tools/nfl_player_roster_xiso_verify.py \
    --source-xiso "$source" \
    --output-xiso "$output" \
    "${verify_mode[@]}" \
    --manifest "$manifest" \
    --audit "$temporary/audit-link.json" >"$temporary/audit-link.stdout" 2>"$temporary/audit-link.stderr"; then
  echo 'symlink audit unexpectedly accepted' >&2
  exit 1
fi
grep -q 'audit symlink refused' "$temporary/audit-link.stderr"

if python3 tools/nfl_player_roster_xiso_workflow.py \
    --source-xiso "$source" \
    --output-xiso "$temporary/writer-symlink-audit.xiso.iso" \
    --manifest "$temporary/writer-symlink-audit.json" \
    --audit "$temporary/audit-link.json" >"$temporary/writer-link.stdout" 2>"$temporary/writer-link.stderr"; then
  echo 'writer unexpectedly accepted symlink audit' >&2
  exit 1
fi
grep -q 'audit report must not be a symlink' "$temporary/writer-link.stderr"
test ! -e "$temporary/writer-symlink-audit.xiso.iso"
test ! -e "$temporary/writer-symlink-audit.json"

sha256sum -c <(cat <<'HASHES'
73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9  extracted/ESPN NFL 2K5 (USA)/default.xbe
34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d  extracted/ESPN NFL 2K5 (USA)/vc_53450030/0
7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9  ESPN NFL 2K5 (USA).xiso.iso
HASHES
) >/dev/null

echo 'NFL_PLAYER_ROSTER_AUDIT_VALIDATION_PASS players=2547 primary=2479 secondary=68 positions=17 bindings=204 stable_ratings=3 face_shield=none_clear_dark per_player=true per_uniform_tint=false proof_changed=14 xdvdfs_identical=true player=Noah_CodexProof jersey=42 runtime=false originals_unchanged=yes'
