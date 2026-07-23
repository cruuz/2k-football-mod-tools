#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
header='reports/headers/nfl2k5_xbe_header.json'
trace='reports/assets/nfl_main_menu_row_layout_ghidra/nfl_main_menu_row_layout_trace.txt'
pseudo='reports/assets/nfl_main_menu_row_layout_ghidra/nfl_main_menu_row_layout_pseudo_c.c'
java='tools/ghidra_scripts/NflMainMenuRowLayoutTrace.java'
menu_state='reports/assets/menu_state_trace.json'
font_report='reports/assets/nfl_main_menu_font.json'
native_header='include/recovered/nfl2k5/main_menu_row_layout.h'
native_source='src/recovered/nfl2k5/main_menu_row_layout.c'
native_test='tests/nfl_main_menu_row_layout_test.c'
report='reports/assets/nfl_main_menu_row_layout.json'
table='reports/assets/nfl_main_menu_row_layout.tsv'
doc='docs/research/nfl_main_menu_row_layout.md'

for required in "$xbe" "$header" "$trace" "$pseudo" "$java" \
  "$menu_state" "$font_report" \
  "$native_header" "$native_source" "$native_test" "$report" "$table" \
  "$doc" tools/nfl_main_menu_row_layout.py; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_main_menu_row_layout.py
temporary=$(mktemp -d /tmp/nfl-main-menu-row-layout.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_main_menu_row_layout.py \
  --xbe "$xbe" --xbe-header "$header" --trace "$trace" --pseudo "$pseudo" \
  --ghidra-script "$java" --menu-state-report "$menu_state" \
  --font-report "$font_report" --native-header "$native_header" \
  --native-source "$native_source" --native-test "$native_test" \
  --json "$temporary/report.json" --tsv "$temporary/layout.tsv"
cmp "$temporary/report.json" "$report"
cmp "$temporary/layout.tsv" "$table"
test "$(wc -l < "$table")" -eq 22

common=(-std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
        -Iinclude "$native_test" "$native_source")
gcc "${common[@]}" -o "$temporary/gcc-test"
"$temporary/gcc-test" | tee "$temporary/gcc.log"
grep -qx 'NFL_MAIN_MENU_ROW_LAYOUT_NATIVE_PASS modes=3 cases=10' \
  "$temporary/gcc.log"
clang-18 "${common[@]}" -o "$temporary/clang-test"
"$temporary/clang-test" | tee "$temporary/clang.log"
grep -qx 'NFL_MAIN_MENU_ROW_LAYOUT_NATIVE_PASS modes=3 cases=10' \
  "$temporary/clang.log"

python3 - "$report" "$table" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, table_path, trace_path, pseudo_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_main_menu_row_layout/v1"
assert report["result"] == {
    "all_first_seven_rows_before_wrap": True,
    "concrete_live_mode_proved": False,
    "emitted_mode_row_pairs": 21,
    "framebuffer_pixel_mapping_proved": False,
    "portable_native_implementation": "src/recovered/nfl2k5/main_menu_row_layout.c",
    "recovered_main_menu_rows": 7,
    "serialized_modes": 3,
}
assert len(report["executable"]["ranges"]) == 7
assert len(report["modes"]) == 3
assert report["upstream_joins"]["navigation_rows"]["count"] == 7
assert report["upstream_joins"]["navigation_rows"]["indices"] == list(range(7))
assert report["upstream_joins"]["font"]["slot"] == 6
assert report["upstream_joins"]["font"]["name"] == "font7"
expected = [(0.0, 0.0, 10, 38.0), (0.0, 0.0, 10, 38.0),
            (144.0, 86.0, 11, 30.0)]
for index, (base_x, base_y, wrap_rows, row_step) in enumerate(expected):
    mode = report["modes"][index]
    assert (mode["mode"], mode["base_x"], mode["base_y"],
            mode["wrap_rows"], mode["row_step"]) == (
                index, base_x, base_y, wrap_rows, row_step)
    assert len(mode["first_seven_rows"]) == 7
    assert all(row["wrapped_columns"] == 0
               for row in mode["first_seven_rows"])
    assert mode["first_wrap"]["x"] == base_x + 200.0
    assert mode["first_wrap"]["y"] == base_y

with table_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 21
mode0_row6 = [row for row in rows if row["mode"] == "0" and row["row"] == "6"]
assert len(mode0_row6) == 1
assert (mode0_row6[0]["x"], mode0_row6[0]["y"],
        mode0_row6[0]["text_x"], mode0_row6[0]["text_y"]) == (
            "0.0", "228.0", "8.0", "224.0")
mode2_row6 = [row for row in rows if row["mode"] == "2" and row["row"] == "6"]
assert len(mode2_row6) == 1
assert (mode2_row6[0]["x"], mode2_row6[0]["y"],
        mode2_row6[0]["text_x"], mode2_row6[0]["text_y"]) == (
            "144.0", "266.0", "152.0", "262.0")

assert len(report["portme"]) == 3
assert all(value.startswith("// PORTME(") for value in report["portme"])
for source in report["source_pins"].values():
    path = Path(source["path"])
    assert path.stat().st_size == source["size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for phrase in ("0x0014FB7A MOV ECX,dword ptr [EAX + 0xa7c]",
               "0x0014FBD2 FADD float ptr [0x004e6c6c]",
               "0x0014FE4A CALL 0x0014fb70",
               "0x0014FF18 FADD float ptr [0x004e6c50]",
               "0x0014FF21 CALL 0x00046a70"):
    assert phrase in trace
assert "unaff_ESI[2] = 20.0;" in pseudo

doc = doc_path.read_text(encoding="utf-8")
for phrase in ("three exact modes", "`+0xA7C`", "title-space",
               "What worked", "What failed", "What is still blocking",
               "not framebuffer pixels"):
    assert phrase in doc
PY

mode=normal
if [[ "${NFL_MAIN_MENU_ROW_LAYOUT_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
      XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
      JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflMainMenuRowLayoutTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_main_menu_row_layout_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_main_menu_row_layout_pseudo_c.c" "$pseudo"
  mode=full
fi

echo "NFL_MAIN_MENU_ROW_LAYOUT_VALIDATION_PASS mode=$mode compilers=2 modes=3 rows=7 pairs=21"
