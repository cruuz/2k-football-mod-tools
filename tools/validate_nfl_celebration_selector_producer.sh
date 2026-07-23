#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
header='reports/headers/nfl2k5_xbe_header.json'
report='reports/assets/nfl_celebration_selector_producer.json'
dispatch='reports/assets/nfl_celebration_selector_dispatch.tsv'
mode_tsv='reports/assets/nfl_celebration_playback_modes.tsv'
path_tsv='reports/assets/nfl_celebration_selector_path.tsv'
trace='reports/assets/nfl_celebration_selector_producer_ghidra/nfl_celebration_selector_producer_trace.txt'
pseudo='reports/assets/nfl_celebration_selector_producer_ghidra/nfl_celebration_selector_producer_pseudo_c.c'
java='tools/ghidra_scripts/NflCelebrationSelectorProducerTrace.java'
doc='docs/research/nfl_celebration_selector_producer.md'

for required in "$xbe" "$header" "$report" "$dispatch" "$mode_tsv" "$path_tsv" \
  "$trace" "$pseudo" "$java" "$doc" \
  tools/nfl_celebration_selector_producer.py; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_celebration_selector_producer.py
temporary=$(mktemp -d /tmp/nfl-celebration-selector.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 tools/nfl_celebration_selector_producer.py "$xbe" \
  --xbe-header "$header" \
  --trace "$trace" \
  --pseudo "$pseudo" \
  --ghidra-script "$java" \
  --json "$temporary/report.json" \
  --dispatch-tsv "$temporary/dispatch.tsv" \
  --mode-tsv "$temporary/modes.tsv" \
  --path-tsv "$temporary/path.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/dispatch.tsv" "$dispatch"
cmp "$temporary/modes.tsv" "$mode_tsv"
cmp "$temporary/path.tsv" "$path_tsv"
test "$(wc -l < "$dispatch")" -eq 6
test "$(wc -l < "$mode_tsv")" -eq 6
test "$(wc -l < "$path_tsv")" -eq 11

python3 - "$report" "$dispatch" "$mode_tsv" "$path_tsv" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, dispatch_path, mode_path, path_path, trace_path, pseudo_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_celebration_selector_producer/v1"
result = report["result"]
assert result["selector_index_2_default_producer_proved"] is True
assert result["dispatch_state_word"] == "0x00000034"
assert result["selector_slot_argument"] == result["default_slot_value"] == result["selected_row"] == 2
assert result["selected_name"] == "ANM_CELEBRATE_USER_34"
assert result["unconditional_for_all_saved_profiles"] is False

event = report["event_dispatch"]
assert event["state_callback_table_base_va"] == "0x00aabef8"
assert event["state_callback_table_size_bytes"] == 0x274
assert event["state_callback_table_index_formula"] == "base + state_word * 4"
callback_entries = event["state_callback_table_entries"]
assert [row["state_word"] for row in callback_entries] == [
    "0x00000033", "0x00000034", "0x0000008e"]
assert [row["entry_va"] for row in callback_entries] == [
    "0x00aabfc4", "0x00aabfc8", "0x00aac130"]
assert all(row["callback_va"] == "0x0018d6d0" for row in callback_entries)

profile = report["profile_selection"]
assert profile["profile_pointer_stride_bytes"] == 28
assert profile["profile_record_stride_bytes"] == 0x1278
assert profile["selector_profile_stride_words"] == 0x0f9e
assert profile["selector_profile_stride_bytes"] == 0x3e78
assert report["default_initializer"]["slot_values"] == [0, 1, 2, 3, 4]
assert report["default_initializer"]["slot_2_is_selector_index_2"] is True
assert report["default_initializer"]["immutability_claimed"] is False

row = report["selector_row_2"]
assert row["va"] == "0x0050cfe0" and row["left_pointer"] == 0
assert row["right_pointer"] == "0x00e8480c"
assert row["right_name"] == "ANM_CELEBRATE_USER_34"
assert row["opaque_s32"] == 21 and row["forced_right_because_left_is_null"] is True

constructor = report["state_constructor_followup"]
assert constructor["state_plus_a0_source"].startswith("first stack argument from EBX")
assert constructor["concrete_argument_for_state_word_0x34_proved"] is False
producer = report["playback_mode_producer"]
assert producer["registration_input_event_code"] == 6
assert producer["registered_callback_va"] == "0x001abf30"
assert producer["direct_constructor_callsite_va"] == "0x002de900"
assert producer["indirect_caller_recovered"] is True
assert producer["mode_one_record_types"] == [1, 5]
assert producer["concrete_record_type_for_state_word_0x34_proved"] is False
assert len(report["portme"]) == 2
assert all(item.startswith("// PORTME(") for item in report["portme"])
assert len(report["executable"]["ranges"]) == 17
callback_range = [row for row in report["executable"]["ranges"]
                  if row["name"] == "state_callback_table"]
assert len(callback_range) == 1
assert callback_range[0]["size"] == 0x274
assert callback_range[0]["sha256"] == "c2d49816fbc3d7bd80b5f63c873eb18a20f6255c971547e2e268280aa64978d1"

for pin in report["source_pins"].values():
    pinned = Path(pin["path"])
    assert hashlib.sha256(pinned.read_bytes()).hexdigest() == pin["sha256"]

with dispatch_path.open(encoding="utf-8", newline="") as stream:
    dispatch = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(dispatch) == 5
slot2 = [row for row in dispatch if row["selector_slot"] == "2"]
assert len(slot2) == 1 and slot2[0]["input"] == "0x00000034"
assert slot2[0]["callsite"] == "0x0018d80b"
assert sorted(int(row["selector_slot"]) for row in dispatch) == [0, 1, 2, 3, 4]

with mode_path.open(encoding="utf-8", newline="") as stream:
    modes = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(modes) == 5
assert [int(row["record_type"]) for row in modes] == [1, 2, 3, 4, 5]
assert [int(row["playback_mode"]) for row in modes] == [1, 14, 2, 2, 1]
assert all(row["record_owner"] == "current actor" for row in modes)
assert all(row["reaches_constructor_0x002de300"] == "True" for row in modes)

with path_path.open(encoding="utf-8", newline="") as stream:
    paths = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(paths) == 10 and [int(row["step"]) for row in paths] == list(range(1, 11))
assert paths[1]["source"] == "state word 0x34" and paths[1]["target"] == "selector slot 2"
assert paths[7]["target"] == "ANM_CELEBRATE_USER_34"
assert paths[-1]["target"] == "state+0xa0 playback mode"

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for phrase in (
    "0x0018D804 MOV EDX,0x2",
    "0x0018D80B CALL 0x002de9c0",
    "0x0013F83F MOV dword ptr [EAX + 0xbc8ad8],0x2",
    "0x00191E19 CALL 0x0013f770",
    "0x002DE35C MOV dword ptr [ESI + 0xa0],ECX",
    "0x00212C1B MOV ECX,0x1abf30",
    "0x001ABFBC CALL 0x002de800",
    "0x002DE8FF PUSH EBX",
    "0x002DE900 CALL 0x002de300",
    "0x00AABEF8 length=628 bytes=",
):
    assert phrase in trace
assert "puVar4[0x28] = param_1;" in pseudo
assert "*(undefined4 *)(&DAT_00bc8ad8 + param_1) = 2;" in pseudo

doc = doc_path.read_text(encoding="utf-8")
for phrase in ("previously unknown default producer", "`actor_state+0x1C == 0x34`", "0x002DE35C", "not a claim", "actor-owned", "caller itself is no", "`0x00AABEF8`"):
    assert phrase in doc
PY

mode=normal
if [[ "${NFL_CELEBRATION_SELECTOR_PRODUCER_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflCelebrationSelectorProducerTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_celebration_selector_producer_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_celebration_selector_producer_pseudo_c.c" "$pseudo"
  mode=full
fi

echo "NFL_CELEBRATION_SELECTOR_PRODUCER_VALIDATION_PASS mode=$mode state=0x34 slot=2 default_index=2 dispatch_rows=5 playback_modes=5 path_steps=10"
