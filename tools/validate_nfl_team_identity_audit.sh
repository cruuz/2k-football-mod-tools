#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

audit='reports/assets/nfl2k5_team_identity_audit.json'
teams='reports/assets/nfl2k5_team_identity_teams.tsv'
codes='reports/assets/nfl2k5_team_identity_asset_codes.tsv'
source='ESPN NFL 2K5 (USA).xiso.iso'
output='build/nfl2k5-team-identity-workflow-20260712/ESPN-NFL-2K5-Codexia-Codex-identity.xiso.iso'
manifest='build/nfl2k5-team-identity-workflow-20260712/workflow.json'
temporary=$(mktemp -d /tmp/nfl-team-identity-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 -m py_compile \
  tools/nfl_team_identity_audit.py \
  tools/nfl_team_identity_xiso_workflow.py \
  tools/nfl_team_identity_xiso_verify.py

python3 tools/nfl_team_identity_audit.py \
  --output "$temporary/audit.json" \
  --teams-tsv "$temporary/teams.tsv" \
  --codes-tsv "$temporary/codes.tsv" >/dev/null
cmp "$temporary/audit.json" "$audit"
cmp "$temporary/teams.tsv" "$teams"
cmp "$temporary/codes.tsv" "$codes"

python3 - <<'PY'
import csv
import hashlib
import json
from pathlib import Path

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

assert digest("reports/assets/nfl2k5_team_identity_audit.json") == \
    "9ddae13f0234b628e28fa10d6935b73e1447362eb41701dc9c45f9dc0a188d7d"
assert digest("reports/assets/nfl2k5_team_identity_teams.tsv") == \
    "f79e595d0bd5120fbc6e801633410ba0137fc309dbb4cf5b1e1dea5aa767208b"
assert digest("reports/assets/nfl2k5_team_identity_asset_codes.tsv") == \
    "6eec9eff11c76883bda303eb63a244a0ecd7e8a0331e692bfca160c228c94add"
assert digest("build/nfl2k5-team-identity-workflow-20260712/workflow.json") == \
    "66eacc7083d52df1488dfbf8b0dc2eb04b9b6a9eeeeea241c1ecc5a995eb399a"

report = json.loads(Path("reports/assets/nfl2k5_team_identity_audit.json").read_text())
assert report["schema"] == "nfl2k5_team_identity_audit/v1"
assert report["summary"] == {
    "compiled_color_record_count": 80,
    "created_team_field_art_code_count": 42,
    "created_team_field_art_package_count": 126,
    "empty_user_slot_seed_count": 2,
    "field_art_codes_without_retail_stadium_secondary_label": ["33", "50", "72"],
    "main_team_count": 52,
    "retail_stadium_field_art_label_count": 39,
    "stock_nfl_team_count": 32,
    "uniform_and_team_select_asset_code_count": 85,
}
assert len(report["teams"]) == 52
assert len(report["asset_codes"]) == 85
assert len(report["compiled_color_records"]) == 80
detroit = report["teams"][18]
assert (detroit["city"], detroit["nickname"], detroit["abbreviation"],
        detroit["asset_code"], detroit["roster_size"], detroit["stadium_index"]) == \
       ("Detroit", "Lions", "DET", "09", 53, 9)
assert all(detroit["fields"][name]["known_decoded_pointer_reference_count"] == 1
           for name in ("city", "nickname", "abbreviation", "city_abbreviation"))
user = report["teams"][32:34]
assert all(row["classification"] == "empty_user_slot_seed" and row["roster_size"] == 0
           for row in user)
missing_colors = [row["asset_code"] for row in report["asset_codes"]
                  if not row["compiled_color_record_present"]]
assert missing_colors == ["95", "96", "97", "98", "99"]
assert all(row["compiled_color_fallback"] == {
    "primary_accessor_0x00068D70": "0xff0065e6",
    "secondary_accessor_0x00068DC0": "0xff00a0ff",
} for row in report["asset_codes"] if row["asset_code"] in missing_colors)
assert report["claims"] == {
    "compiled_color_table_proved": True,
    "created_team_field_join_proved": True,
    "general_roster_writer_emitted": False,
    "new_team_added": False,
    "originals_modified": False,
    "runtime_visibility_proved_by_this_audit": False,
    "save_container_schema_proved": False,
    "team_identity_disc_schema_proved": True,
    "uniform_and_team_select_join_proved": True,
}

with Path("reports/assets/nfl2k5_team_identity_teams.tsv").open(newline="") as stream:
    team_rows = list(csv.DictReader(stream, delimiter="\t"))
with Path("reports/assets/nfl2k5_team_identity_asset_codes.tsv").open(newline="") as stream:
    code_rows = list(csv.DictReader(stream, delimiter="\t"))
assert len(team_rows) == 52 and len(code_rows) == 85
assert team_rows[18]["city"] == "Detroit" and team_rows[18]["asset_code"] == "09"
assert next(row for row in code_rows if row["asset_code"] == "09")["uniform_pair_count"] == "10"
assert next(row for row in code_rows if row["asset_code"] == "67")["created_team_field_art_package_count"] == "3"
PY

python3 tools/nfl_team_identity_xiso_verify.py \
  --source-xiso "$source" \
  --output-xiso "$output" \
  --manifest "$manifest" \
  --audit "$audit"

ln -s "$source" "$temporary/source-link.iso"
if python3 tools/nfl_team_identity_xiso_verify.py \
    --source-xiso "$temporary/source-link.iso" \
    --output-xiso "$output" \
    --manifest "$manifest" \
    --audit "$audit" >"$temporary/symlink.stdout" 2>"$temporary/symlink.stderr"; then
  echo 'symlink source unexpectedly accepted' >&2
  exit 1
fi
grep -q 'symlink refused' "$temporary/symlink.stderr"

ln -s "$(realpath "$manifest")" "$temporary/manifest-link.json"
if python3 tools/nfl_team_identity_xiso_verify.py \
    --source-xiso "$source" \
    --output-xiso "$output" \
    --manifest "$temporary/manifest-link.json" \
    --audit "$audit" >"$temporary/manifest-link.stdout" 2>"$temporary/manifest-link.stderr"; then
  echo 'symlink manifest unexpectedly accepted' >&2
  exit 1
fi
grep -q 'manifest symlink refused' "$temporary/manifest-link.stderr"

ln -s "$(realpath "$audit")" "$temporary/audit-link.json"
if python3 tools/nfl_team_identity_xiso_verify.py \
    --source-xiso "$source" \
    --output-xiso "$output" \
    --manifest "$manifest" \
    --audit "$temporary/audit-link.json" >"$temporary/audit-link.stdout" 2>"$temporary/audit-link.stderr"; then
  echo 'symlink audit unexpectedly accepted' >&2
  exit 1
fi
grep -q 'audit symlink refused' "$temporary/audit-link.stderr"

if python3 tools/nfl_team_identity_xiso_workflow.py \
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
daae27a6e51d4ed126b4bc14c800c1c6090dc32efa00d18283e65c07d7660e45  build/nfl2k5-team-identity-workflow-20260712/ESPN-NFL-2K5-Codexia-Codex-identity.xiso.iso
HASHES
) >/dev/null

echo 'NFL_TEAM_IDENTITY_AUDIT_VALIDATION_PASS teams=52 stock=32 user_seeds=2 asset_codes=85 colors=80 field_codes=42 proof_changed=17 xdvdfs_identical=true asset_code=09 runtime=false originals_unchanged=yes'
