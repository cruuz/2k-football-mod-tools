#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
header='reports/headers/nfl2k5_xbe_header.json'
inventory='reports/assets/nfl2k5_all_txtr_inventory_v2.json'
menu='reports/assets/menu_state_trace.json'
trace='reports/assets/nfl_formatted_token_ghidra/nfl_formatted_token_trace.txt'
pseudo='reports/assets/nfl_formatted_token_ghidra/nfl_formatted_token_pseudo_c.c'
java='tools/ghidra_scripts/NflFormattedTokenTrace.java'
report='reports/assets/nfl_formatted_token.json'
tokens='reports/assets/nfl_formatted_tokens.tsv'
resources='reports/assets/nfl_formatted_token_resources.tsv'
header_c='include/recovered/nfl2k5/formatted_token.h'
source_c='src/recovered/nfl2k5/formatted_token.c'
test_c='tests/nfl_formatted_token_test.c'
doc='docs/research/nfl_formatted_token.md'
tm_png='assets/intermediate/nfl2k5/textures/outer_0003_8ee9eeed/0047_tm.png'

for required in "$xbe" "$header" "$inventory" "$menu" "$trace" "$pseudo" \
  "$java" "$report" "$tokens" "$resources" "$header_c" "$source_c" \
  "$test_c" "$doc" "$tm_png" tools/nfl_formatted_token.py; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/nfl-formatted-token.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_formatted_token.py tests/nfl_formatted_token_screenshot_test.py

python3 tools/nfl_formatted_token.py \
  --xbe "$xbe" --xbe-header "$header" \
  --texture-inventory "$inventory" --menu-state-report "$menu" \
  --trace "$trace" --pseudo "$pseudo" --ghidra-script "$java" \
  --native-header "$header_c" --native-source "$source_c" \
  --native-test "$test_c" --json "$temporary/report.json" \
  --tokens-tsv "$temporary/tokens.tsv" \
  --resources-tsv "$temporary/resources.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/tokens.tsv" "$tokens"
cmp "$temporary/resources.tsv" "$resources"
test "$(wc -l < "$tokens")" -eq 58
test "$(wc -l < "$resources")" -eq 14

python3 - "$report" "$tokens" "$resources" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys

report_path, token_path, resource_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_formatted_token/v1"
result = report["result"]
assert result == {
    "ascii_case_insensitive_matching_proved": True,
    "loaded_texture_resource_count": 13,
    "main_menu_row_2_label": "The Crib|TM|",
    "main_menu_tm_inline_object_proved": True,
    "native_tm_loose_override_wired": True,
    "original_default_main_menu_draw_claimed": False,
    "recognized_token_consumes_both_pipes": True,
    "serialized_token_count": 57,
    "tm_index": 40,
    "tm_png_proved": True,
    "tm_resource_name": "tm",
    "tm_texture_slot": 9,
}
assert len(report["tokens"]) == 57
assert len(report["texture_resources"]) == 13
tm = report["tokens"][40]
assert (tm["name"], tm["texture_slot"], tm["u0"], tm["v0"],
        tm["u1"], tm["v1"], tm["height_scale"],
        tm["width_over_height"], tm["flags"]) == \
       ("TM", 9, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1)
resource = report["texture_resources"][9]
assert (resource["resource_name"], resource["loader_call"],
        resource["runtime_store"], resource["width"], resource["height"]) == \
       ("tm", "0x000ef67d", "0x00a90828", 32, 32)
assert resource["rgba_sha256"] == \
       "fc7f74747c74eadd345dc8f49adac0bf53c89b0c695dc9765840a71cd9b81b0e"
assert len(report["executable"]["ranges"]) == 11
assert len(report["portme"]) == 3
assert all(value.startswith("// PORTME(") for value in report["portme"])
for value in report["source_pins"].values():
    path = Path(value["path"])
    assert path.stat().st_size == value["size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == value["sha256"]

with token_path.open(encoding="utf-8", newline="") as stream:
    tokens = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(tokens) == 57
assert [int(row["index"]) for row in tokens] == list(range(57))
assert tokens[40]["name"] == "TM" and tokens[40]["texture_slot"] == "9"
with resource_path.open(encoding="utf-8", newline="") as stream:
    resources = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(resources) == 13
assert [int(row["texture_slot"]) for row in resources] == list(range(13))

png = Path(resource["png_path"]).read_bytes()
assert png[:8] == b"\x89PNG\r\n\x1a\n" and png[12:16] == b"IHDR"
assert struct.unpack_from(">II", png, 16) == (32, 32)

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "57 exact records", "case-insensitive", "index 40", "texture slot 9",
    "0047_tm.png", "The Crib|TM|", "cold-boot default menu draw",
    "NFL_FORMATTED_TOKEN_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

for compiler in gcc clang-18; do
  "$compiler" -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror \
    -Iinclude "$source_c" "$test_c" -lm \
    -o "$temporary/token-${compiler}"
  "$temporary/token-${compiler}" "$tokens" | \
    grep -F 'NFL_FORMATTED_TOKEN_NATIVE_PASS tokens=57 tm_index=40 tm_slot=9 tm_extent=25 casefold=ascii'
done

mode=normal
if [[ "${NFL_FORMATTED_TOKEN_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 -process default.xbe \
      -readOnly -noanalysis -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflFormattedTokenTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_formatted_token_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_formatted_token_pseudo_c.c" "$pseudo"
  mode=full
fi

echo "NFL_FORMATTED_TOKEN_VALIDATION_PASS mode=$mode tokens=57 resources=13 tm_index=40 tm_slot=9 compilers=2"
