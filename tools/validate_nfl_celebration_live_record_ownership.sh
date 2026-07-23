#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
header='reports/headers/nfl2k5_xbe_header.json'
selector='reports/assets/nfl_celebration_selector_producer.json'
report='reports/assets/nfl_celebration_live_record_ownership.json'
path_tsv='reports/assets/nfl_celebration_live_record_path.tsv'
type_tsv='reports/assets/nfl_celebration_live_record_types.tsv'
profile_tsv='reports/assets/nfl_celebration_profile_setter.tsv'
trace='reports/assets/nfl_celebration_live_record_ownership_ghidra/nfl_celebration_live_record_ownership_trace.txt'
pseudo='reports/assets/nfl_celebration_live_record_ownership_ghidra/nfl_celebration_live_record_ownership_pseudo_c.c'
java='tools/ghidra_scripts/NflCelebrationLiveRecordOwnershipTrace.java'
doc='docs/research/nfl_celebration_live_record_ownership.md'
generator='tools/nfl_celebration_live_record_ownership.py'

for required in "$xbe" "$header" "$selector" "$report" "$path_tsv" \
  "$type_tsv" "$profile_tsv" "$trace" "$pseudo" "$java" "$doc" \
  "$generator"; do
  test -f "$required"
done

python3 -m py_compile "$generator"
tools/validate_nfl_celebration_selector_producer.sh >/dev/null

temporary=$(mktemp -d /tmp/nfl-celebration-live-record.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 "$generator" "$xbe" \
  --xbe-header "$header" \
  --selector-report "$selector" \
  --trace "$trace" \
  --pseudo "$pseudo" \
  --ghidra-script "$java" \
  --json "$temporary/report.json" \
  --path-tsv "$temporary/path.tsv" \
  --type-tsv "$temporary/types.tsv" \
  --profile-tsv "$temporary/profile.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/path.tsv" "$path_tsv"
cmp "$temporary/types.tsv" "$type_tsv"
cmp "$temporary/profile.tsv" "$profile_tsv"
test "$(wc -l < "$path_tsv")" -eq 15
test "$(wc -l < "$type_tsv")" -eq 6
test "$(wc -l < "$profile_tsv")" -eq 6

python3 - "$report" "$path_tsv" "$type_tsv" "$profile_tsv" \
  "$trace" "$pseudo" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, path_path, type_path, profile_path, trace_path, pseudo_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_celebration_live_record_ownership/v1"
result = report["result"]
assert result["successful_state_0x34_dispatch_actor_owned_record_proved"] is True
assert result["record_tag"] == 2 and result["record_domain"] == "scoring result"
assert result["record_type_domain"] == [1, 2, 3, 4, 5]
assert result["concrete_record_type_for_state_0x34_proved"] is False
assert result["mode_one_record_types"] == [1, 5]
assert result["playback_mode_one_for_state_0x34_proved"] is False
assert result["full_previous_portme_closed"] is False

record = report["tag2_record"]
assert record["ring_capacity"] == 4 and record["record_stride"] == 0x30
assert record["writer_is_only_tag2_ring_insertion_callsite"] is True
assert record["layout"] == {
    "0x00": "tag = 2", "0x10": "owner actor",
    "0x14": "companion/side object", "0x18": "scoring result type"}

closure = report["ownership_closure"]
assert closure["state_0x34_selector_slot"] == 2
assert closure["selector_dispatch_accepted_callbacks"] == ["0x002de170", "0x002ddb10"]
assert closure["owner_equality_guard_va"] == "0x002de8ec"
assert [row["state_word"] for row in closure["entries"]] == [
    "0x00000033", "0x00000034", "0x0000008e"]
assert all(row["callback_va"] == "0x0018d6d0" for row in closure["entries"])

boundary = report["type_and_mode_boundary"]
assert boundary["spatial_gate_table_values_by_classifier_index"] == [1, 0, 2, 0, 1]
assert boundary["gate_2_for_state_0x34_proved"] is False
assert boundary["handler_0x0018d6d0_reads_record_type"] is False
assert boundary["handler_0x0018d6d0_reads_state_plus_a0"] is False
assert boundary["direct_immediate_state_0x34_write_matches_in_saved_listing"] == 0

profile = report["profile_selector_mutation"]
assert profile["setter_va"] == "0x00142390"
assert profile["direct_callsite_va"] == "0x00369afa"
assert profile["label_count"] == 37 and len(profile["labels"]) == 37
assert profile["row_2_display_label"] == "Chest Pound"
assert profile["row_2_resource_name"] == "ANM_CELEBRATE_USER_34"
assert profile["default_row_2_immutable"] is False

assert len(report["blocking"]) == 3
assert all(item.startswith("// PORTME(") for item in report["blocking"])
assert len(report["failed_trails"]) == 2
assert len(report["executable"]["ranges"]) == 37
for pin in report["source_pins"].values():
    path = Path(pin["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"]

with path_path.open(encoding="utf-8", newline="") as stream:
    paths = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(paths) == 14 and [int(row["step"]) for row in paths] == list(range(1, 15))
assert paths[12]["target"] == "record owner"
assert paths[13]["target"] == "record type/playback mode"

with type_path.open(encoding="utf-8", newline="") as stream:
    types = list(csv.DictReader(stream, dialect="excel-tab"))
assert [int(row["record_type"]) for row in types] == [1, 2, 3, 4, 5]
assert [int(row["score_points"]) for row in types] == [6, 2, 3, 1, 2]
assert [int(row["actor_owned_playback_mode"]) for row in types] == [1, 14, 2, 2, 1]
assert [row["selected_name_mode"] for row in types] == ["True", "False", "False", "False", "True"]

with profile_path.open(encoding="utf-8", newline="") as stream:
    profile_rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(profile_rows) == 5
assert profile_rows[3]["instruction"].startswith("0x00369af9")

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for phrase in (
    "STATE_WORD_0X34_DIRECT_WRITE_SCAN\nmatches=0",
    "0x002DE8EC CMP dword ptr [EBP],EDI",
    "0x002DE31D MOV dword ptr [ESI],0x2de170",
    "0x002DE1DA MOV dword ptr [EDI],0x2ddb10",
    "0x0018D804 MOV EDX,0x2",
    "0x00369AFA CALL 0x00142390",
    "0x00706B38 length=4 bytes=ffffffff",
):
    assert phrase in trace
assert "*puVar4 = &LAB_002de170;" in pseudo
assert "// PORTME: no saved Ghidra function boundary at 0x002DE800" in pseudo

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "ownership half", "unique reverse callback chain", "**not** statically fixed",
    "0x00369AFA  CALL", "`Chest Pound`", "zero motion events",
    "PORTME(0x002DDDB0)", "PORTME(0x0018C9C0/0x0018D6D0)",
):
    assert phrase in doc
PY

mode=normal
if [[ "${NFL_CELEBRATION_LIVE_RECORD_OWNERSHIP_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflCelebrationLiveRecordOwnershipTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_celebration_live_record_ownership_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_celebration_live_record_ownership_pseudo_c.c" "$pseudo"
  mode=full
fi

echo "NFL_CELEBRATION_LIVE_RECORD_OWNERSHIP_VALIDATION_PASS mode=$mode ownership=exact type=partial modes=5 paths=14 profile_steps=5"
