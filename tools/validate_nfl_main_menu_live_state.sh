#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
header='reports/headers/nfl2k5_xbe_header.json'
ghidra_dir='reports/assets/nfl_main_menu_live_state_ghidra'
trace="$ghidra_dir/nfl_main_menu_live_state_trace.txt"
pseudo="$ghidra_dir/nfl_main_menu_live_state_pseudo_c.c"
java='tools/ghidra_scripts/NflMainMenuLiveStateTrace.java'
menu_state='reports/assets/menu_state_trace.json'
row_layout='reports/assets/nfl_main_menu_row_layout.json'
font_report='reports/assets/nfl_main_menu_font.json'
report='reports/assets/nfl_main_menu_live_state.json'
table='reports/assets/nfl_main_menu_live_state.tsv'
portme='reports/assets/nfl_main_menu_live_state_portme.c'
doc='docs/research/nfl_main_menu_live_state.md'
generator='tools/nfl_main_menu_live_state.py'

for required in "$xbe" "$header" "$trace" "$pseudo" "$java" \
  "$menu_state" "$row_layout" "$font_report" "$report" "$table" \
  "$portme" "$doc" "$generator"; do
  test -f "$required"
done

python3 -m py_compile "$generator"
bash -n "$0"
temporary=$(mktemp -d /tmp/nfl-main-menu-live-state.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 "$generator" \
  --xbe "$xbe" --xbe-header "$header" --trace "$trace" --pseudo "$pseudo" \
  --ghidra-script "$java" --menu-state-report "$menu_state" \
  --row-layout-report "$row_layout" --font-report "$font_report" \
  --json "$temporary/report.json" --tsv "$temporary/state.tsv" \
  --portme "$temporary/portme.c"
cmp "$temporary/report.json" "$report"
cmp "$temporary/state.tsv" "$table"
cmp "$temporary/portme.c" "$portme"
test "$(wc -l < "$table")" -eq 8

common=(-std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror)
gcc "${common[@]}" -c "$portme" -o "$temporary/portme-gcc.o"
clang-18 "${common[@]}" -c "$portme" -o "$temporary/portme-clang.o"

python3 - "$report" "$table" "$portme" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, table_path, portme_path, trace_path, pseudo_path, doc_path = (
    map(Path, sys.argv[1:]))
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_main_menu_live_state/v1"
assert report["result"] == {
    "construction_mode": 0,
    "cpu_direct_text_vertex_coordinates_proved": True,
    "cpu_logical_canvas": [640, 480],
    "default_background_render_category": 2,
    "default_direct_font_row_draw": False,
    "default_layout_draw_call_if_loaded": True,
    "first_successful_gpu_primitive_proved": False,
    "initial_selectable_rows": 7,
    "initial_selected_label": "Quick Game",
    "initial_selected_raw_row": 0,
    "original_boot_proved": False,
    "physical_framebuffer_mapping_proved": False,
}
assert len(report["executable"]["ranges"]) == 25
assert report["mode_ownership"]["menu_cluster_writer_count"] == 1
assert [item["value"] for item in
        report["mode_ownership"]["known_direct_callers"]] == [0, 0]
assert report["draw_order"]["event_7_calls"] == [
    "0x000f2810", "0x000f2f70", "0x00150260"]
assert report["draw_order"]["direct_row_stage"][
    "default_mode_executes_font_renderer"] is False
assert report["draw_order"]["menu_layout_stage"]["resource"] == (
    "main_menu_sub")
assert report["draw_order"]["menu_layout_stage"]["child_resource"] == (
    "main_navi")
assert report["coordinate_chain"]["default_mode_uses_this_chain"] is False
assert report["coordinate_chain"]["logical_canvas"] == {
    "context_fields": ["+0x6E", "+0x72"], "height": 480, "width": 640}
assert report["upstream_joins"]["row_layout"]["resolved_live_mode"] == 0
assert report["upstream_joins"]["font"] == {
    "default_mode_reaches_font": False,
    "name": "font7",
    "path": "reports/assets/nfl_main_menu_font.json",
    "schema": "nfl2k5_main_menu_font/v1",
    "slot": 6,
}
assert len(report["portme"]) == 9
assert all(value.startswith("// PORTME(") for value in report["portme"])

with table_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 7
assert [row["label"] for row in rows] == [
    "Quick Game", "Game Modes", "The Crib|TM|", "Features", "Options",
    "Xbox Live", "Extras"]
assert [row["initial_selected"] for row in rows] == [
    "True", "False", "False", "False", "False", "False", "False"]
assert rows[0]["previous_label_if_initial_set"] == "Extras"
assert rows[6]["next_label_if_initial_set"] == "Quick Game"

source = portme_path.read_text(encoding="utf-8")
assert source.count("// PORTME(") == 9
for item in report["portme"]:
    assert item in source
for item in report["source_pins"].values():
    path = Path(item["path"])
    assert path.stat().st_size == item["size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for phrase in (
        "0x000F3CD9 33 D2 XOR EDX,EDX",
        "0x0014FCD8 89 B0 7C 0A 00 00 MOV dword ptr [EAX + 0xa7c],ESI",
        "0x0014FF70 33 D2 XOR EDX,EDX",
        "0x0014FC58 89 70 04 MOV dword ptr [EAX + 0x4],ESI",
        "0x00150281 E9 CA 86 17 00 JMP 0x002c8950",
        "0x002C8950 C3 RET",
        "0x000F3F12 E8 F9 E8 FF FF CALL 0x000f2810",
        "0x000F3F19 E8 52 F0 FF FF CALL 0x000f2f70",
        "0x000F3F20 E8 3B C3 05 00 CALL 0x00150260",
        "0x0004699B 66 C7 40 6E 80 02",
        "0x000469A5 66 C7 40 72 E0 01"):
    assert phrase in trace
assert "*(undefined4 *)(iVar1 + 0xa7c) = param_2;" in pseudo
assert "FUN_00143a00(&DAT_004ff250,0,param_2);" in pseudo

doc = doc_path.read_text(encoding="utf-8")
for phrase in ("mode `0`", "Quick Game", "main_menu_sub", "main_navi",
               "font7", "default path skips", "640 x 480",
               "What worked", "What failed", "What is still blocking",
               "does not prove original boot"):
    assert phrase in doc
PY

gate=normal
if [[ "${NFL_MAIN_MENU_LIVE_STATE_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
      XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
      JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflMainMenuLiveStateTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_main_menu_live_state_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_main_menu_live_state_pseudo_c.c" "$pseudo"
  gate=full
fi

echo "NFL_MAIN_MENU_LIVE_STATE_VALIDATION_PASS gate=$gate live_mode=0 initial_row=0 selectable=7 direct_font_default=0 canvas=640x480 compilers=2 portme=9"
