#!/usr/bin/env bash
# Validate the NFL 2K5 coach name writer end-to-end against the retail XISO.
# Builds a copied XISO in a private temp dir, verifies a same-name round trip
# (zero changed bytes) plus a shorter-alias edit, restores the alias and
# requires the image to become byte-identical to retail again, exercises the
# negative guards, then discards the multi-GB output so it is never retained.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

source="${1:-ESPN NFL 2K5 (USA).xiso.iso}"
temporary=$(mktemp -d /tmp/nfl-coach-roster-name-validate.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 -m py_compile tools/nfl_coach_roster_name_workflow.py

# --- plan: same-name round trip on Dennis + shorter alias on Erickson ---
cat >"$temporary/plan.json" <<'PLAN'
{
  "schema": "nfl2k5_coach_roster_name_plan/v1",
  "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
  "edits": [
    {"coach_index": 0, "field": "first_name", "value": "Dennis"},
    {"coach_index": 0, "field": "last_name", "value": "Eri"}
  ]
}
PLAN

python3 tools/nfl_coach_roster_name_workflow.py \
  --source-xiso "$source" \
  --output-xiso "$temporary/output.xiso.iso" \
  --plan "$temporary/plan.json" \
  --manifest "$temporary/manifest.json" >"$temporary/run.stdout"
grep -q 'NFL_COACH_ROSTER_NAME_WORKFLOW_OK edits=2 changed=5' "$temporary/run.stdout"

python3 - "$temporary/manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1]))
assert manifest["schema"] == "nfl2k5_coach_roster_name_workflow/v1"
claims = manifest["claims"]
assert claims["edit_count"] == 2
assert claims["allowed_changed_byte_count"] == 5
assert claims["all_other_xiso_bytes_identical"] is True
assert claims["layout_identical_copy_only_xiso"] is True
assert claims["coach_membership_changed"] is False
assert claims["serialized_pointer_modified"] is False
assert claims["original_source_modified"] is False
assert claims["runtime_visibility_proved"] is False
assert manifest["source"]["modified"] is False
assert manifest["coach_table"] == {"offset": 0x2AD0, "count": 35, "stride": 0xA8}
edits = {(e["coach_index"], e["field"]): e for e in manifest["edits"]}
identity = edits[(0, "first_name")]
assert identity["before"] == "Dennis" and identity["after"] == "Dennis"
assert identity["before_hex"] == identity["after_hex"]
assert identity["changed_relative_bytes"] == []
assert identity["known_pointer_reference_count"] == 1
assert identity["team_indices"] == [0]
alias = edits[(0, "last_name")]
assert alias["before"] == "Erickson" and alias["after"] == "Eri"
assert alias["known_pointer_reference_count"] == 1
assert alias["allocation_bytes"] == len(bytes.fromhex(alias["before_hex"]))
assert len(bytes.fromhex(alias["after_hex"])) == alias["allocation_bytes"]
assert len(alias["changed_relative_bytes"]) == 5
print("manifest assertions passed")
PY

# --- restore: write the original span bytes back and require retail again ---
python3 - "$temporary/output.xiso.iso" "$temporary/manifest.json" <<'PY'
import hashlib
import json
import os
import sys

sys.path.insert(0, "tools")
import nfl_coach_roster_name_workflow as coach  # noqa: E402
import nfl_team_identity_xiso_workflow as common  # noqa: E402

output, manifest_path = sys.argv[1], sys.argv[2]
manifest = json.load(open(manifest_path))
alias = next(e for e in manifest["edits"] if e["field"] == "last_name")
original = bytes.fromhex(alias["before_hex"])
fd = os.open(output, os.O_RDWR)
try:
    entries, _directory = common.parse_xdvdfs(fd, coach.IMAGE_SIZE)
    pack = entries["vc_53450030/0"]
    body_offset = pack.offset + coach.ROST_BODY
    body = common.pread_exact(fd, body_offset, coach.ROST_BODY_SIZE)
    truncated = coach.read_utf16z_span(body, alias["body_string_offset"], "alias")
    assert truncated.decode("utf-16le").rstrip("\0") == "Eri", "alias not applied"
    common.pwrite_exact(fd, body_offset + alias["body_string_offset"], original)
    os.fsync(fd)
finally:
    os.close(fd)
sha = hashlib.sha256()
with open(output, "rb") as stream:
    while chunk := stream.read(16 * 1024 * 1024):
        sha.update(chunk)
assert sha.hexdigest() == coach.SOURCE_SHA256, "restore did not reproduce retail"
print("restore reproduced the retail image byte-for-byte")
PY

# --- negative: name longer than the current decoded span must be refused ---
cat >"$temporary/plan-overflow.json" <<'PLAN'
{
  "schema": "nfl2k5_coach_roster_name_plan/v1",
  "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
  "edits": [
    {"coach_index": 0, "field": "first_name", "value": "Dennison"}
  ]
}
PLAN
if python3 tools/nfl_coach_roster_name_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg1.xiso.iso" \
    --plan "$temporary/plan-overflow.json" --manifest "$temporary/neg1.json" \
    >"$temporary/neg1.stdout" 2>"$temporary/neg1.stderr"; then
  echo 'over-long coach name unexpectedly accepted' >&2
  exit 1
fi
grep -q 'full-allocation writer' "$temporary/neg1.stderr"
test ! -e "$temporary/neg1.xiso.iso"

# --- negative: description fields are outside the name writer ---
cat >"$temporary/plan-field.json" <<'PLAN'
{
  "schema": "nfl2k5_coach_roster_name_plan/v1",
  "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
  "edits": [
    {"coach_index": 0, "field": "description_1", "value": "X"}
  ]
}
PLAN
if python3 tools/nfl_coach_roster_name_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg2.xiso.iso" \
    --plan "$temporary/plan-field.json" --manifest "$temporary/neg2.json" \
    >"$temporary/neg2.stdout" 2>"$temporary/neg2.stderr"; then
  echo 'description field unexpectedly accepted' >&2
  exit 1
fi
grep -q 'unsupported field' "$temporary/neg2.stderr"
test ! -e "$temporary/neg2.xiso.iso"

# --- negative: out-of-range coach index must be refused ---
cat >"$temporary/plan-range.json" <<'PLAN'
{
  "schema": "nfl2k5_coach_roster_name_plan/v1",
  "source_sha256": "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9",
  "edits": [
    {"coach_index": 35, "field": "first_name", "value": "X"}
  ]
}
PLAN
if python3 tools/nfl_coach_roster_name_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg3.xiso.iso" \
    --plan "$temporary/plan-range.json" --manifest "$temporary/neg3.json" \
    >"$temporary/neg3.stdout" 2>"$temporary/neg3.stderr"; then
  echo 'out-of-range coach unexpectedly accepted' >&2
  exit 1
fi
grep -q 'outside the main roster coach table' "$temporary/neg3.stderr"
test ! -e "$temporary/neg3.xiso.iso"

# --- negative: wrong source binding must be refused ---
cat >"$temporary/plan-bind.json" <<'PLAN'
{
  "schema": "nfl2k5_coach_roster_name_plan/v1",
  "source_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "edits": [
    {"coach_index": 0, "field": "first_name", "value": "D"}
  ]
}
PLAN
if python3 tools/nfl_coach_roster_name_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg4.xiso.iso" \
    --plan "$temporary/plan-bind.json" --manifest "$temporary/neg4.json" \
    >"$temporary/neg4.stdout" 2>"$temporary/neg4.stderr"; then
  echo 'wrong source binding unexpectedly accepted' >&2
  exit 1
fi
grep -q 'not bound to the supported retail source' "$temporary/neg4.stderr"
test ! -e "$temporary/neg4.xiso.iso"

# --- negative: symlink plan must be refused ---
ln -s "$(realpath "$temporary/plan.json")" "$temporary/plan-link.json"
if python3 tools/nfl_coach_roster_name_workflow.py \
    --source-xiso "$source" --output-xiso "$temporary/neg5.xiso.iso" \
    --plan "$temporary/plan-link.json" --manifest "$temporary/neg5.json" \
    >"$temporary/neg5.stdout" 2>"$temporary/neg5.stderr"; then
  echo 'symlink plan unexpectedly accepted' >&2
  exit 1
fi
grep -q 'plan must not be a symlink' "$temporary/neg5.stderr"
test ! -e "$temporary/neg5.xiso.iso"

python3 -m unittest tests.test_nfl_coach_roster_name_workflow

echo 'NFL_COACH_ROSTER_NAME_VALIDATION_PASS coaches=35 ownership=unique_reference_only round_trip=byte_identical alias_restored=retail_hash overflow_refused=yes field_refused=yes range_refused=yes binding_refused=yes symlink_refused=yes runtime=false'
