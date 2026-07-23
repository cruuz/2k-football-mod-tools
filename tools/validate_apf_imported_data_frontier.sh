#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

XEX="extracted/All-Pro Football 2K8 (USA)/default.xex"
ARCHIVE="extracted/All-Pro Football 2K8 (USA)/0A"
REPORT="reports/static_recomp/apf2k8_imported_data_frontier.json"
SUMMARY="reports/static_recomp/apf2k8_imported_data_frontier.tsv"
XREFS="reports/static_recomp/apf2k8_imported_data_xrefs.tsv"
DOC="docs/research/apf_imported_data_frontier.md"
EXPECTED_XEX="981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
EXPECTED_ARCHIVE="dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_XREFS="dffdd96da2e95a9025e6025d79d0c78ce46421da6233f2f2ad11d6061c7f1ad6"
EXPECTED_DECODED="cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
TMP_ROOT="${TMPDIR:-/tmp}"
TMP="$(mktemp -d "$TMP_ROOT/apf-imported-data-frontier.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$ARCHIVE" | awk '{print $1}')" = "$EXPECTED_ARCHIVE"
test "$(sha256sum "$XREFS" | awk '{print $1}')" = "$EXPECTED_XREFS"

python3 tools/apf_imported_data_frontier.py \
  --report-output "$TMP/report.json" \
  --tsv-output "$TMP/summary.tsv"
cmp -s "$TMP/report.json" "$REPORT"
cmp -s "$TMP/summary.tsv" "$SUMMARY"
grep -Fq 'wrong: X_LDR_DATA_TABLE_ENTRY + 0x58 = 0x82000000' "$DOC"
grep -Fq 'The other 11 ordinal words remain byte-exact.' "$DOC"
grep -Fq '// PORTME at 0x84BF198C:' "$DOC"
grep -Fq 'APF_IMPORTED_DATA_FRONTIER_VALIDATION_PASS' "$DOC"

python3 - "$REPORT" "$SUMMARY" <<'PY'
import csv
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "apf2k8_imported_data_frontier/v1"
result = report["result"]
assert result["imported_data_slots_analyzed"] == 13
assert result["direct_read_xrefs"] == 46
assert result["augmented_frontier_nodes"] == 458
assert result["frontier_needed_slots"] == 2
assert result["frontier_consumer_xrefs"] == 2
assert result["slots_seeded_by_isolated_bootstrap"] == 2
assert result["ordinal_slots_preserved"] == 11
assert result["raw_xex_prefix_copied_to_separate_guest_storage"] is True
assert result["default_heap_size_key_present"] is False
assert result["debug_monitor_callback_dispatch_possible"] is False
assert result["bootstrap_transactional"] is True
assert result["title_entry_called"] is False
assert result["translated_title_code_executed"] is False
assert result["emulator_launched"] is False
assert result["all_thirteen_imported_data_slots_resolved"] is False
model = report["corrected_address_model"]
assert model["decoded_pe_image"]["guest_base"] == "0x82000000"
assert model["decoded_pe_image"]["magic"] == "MZ"
assert model["decoded_pe_image"]["is_raw_xex_header_view"] is False
assert model["raw_xex_header"]["magic"] == "XEX2"
assert model["raw_xex_header"]["guest_address"] == "loader arena + 0x100"
assert "rejected" in model["rejected_initial_assumption"]
assert report["consumer_evidence"]["sub_84BF1850"][
    "bounded_leaf_adapter_result"] == "r3 = NULL"
debug = report["consumer_evidence"]["sub_84BF1950"]
assert debug["debugger_disabled_export_cell_value"] == 0
assert debug["callback_field_read"] is False
assert debug["callback_dispatch_possible"] is False
with open(sys.argv[2], encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, delimiter="\t"))
assert len(rows) == 13
seeded = [row for row in rows if row["bootstrap_state"] ==
          "seeded_frontier_needed"]
assert [(row["name"], row["frontier_consumers"]) for row in seeded] == [
    ("XexExecutableModuleHandle", "sub_84BF1850"),
    ("KeDebugMonitorData", "sub_84BF1950"),
]
assert sum(int(row["xref_count"]) for row in rows) == 46
assert sum(int(row["frontier_xref_count"]) for row in rows) == 2
PY

CLANGXX="/usr/bin/clang++-18"
test -x "$CLANGXX"
test -f tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a
"$CLANGXX" -std=c++20 -O2 tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$TMP/xex_extract_pe"

EXTRACT_TRANSCRIPT="$($TMP/xex_extract_pe "$XEX" "$TMP/apf-decoded.pe")"
test "$EXTRACT_TRANSCRIPT" = \
  "blocks=642 chunks=1648 lzx_bytes=37717546 image_bytes=54001664 window_size=32768"
test "$(stat -c %s "$TMP/apf-decoded.pe")" = "54001664"
test "$(sha256sum "$TMP/apf-decoded.pe" | awk '{print $1}')" = "$EXPECTED_DECODED"
test "$(xxd -p -l 2 "$TMP/apf-decoded.pe")" = "4d5a"
test "$(xxd -p -l 4 "$XEX")" = "58455832"

COMMON_SOURCES=(
  src/static_runtime/apf_imported_data_bootstrap.c
  src/static_runtime/apf_boot_leaf_adapters.c
  tests/apf_imported_data_bootstrap_test.c
)
cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Werror -Iinclude \
  "${COMMON_SOURCES[@]}" -o "$TMP/bootstrap_test"
if nm "$TMP/bootstrap_test" | grep -q '_xstart'; then
  echo "validator linked title entry unexpectedly" >&2
  exit 1
fi
TEST_TRANSCRIPT="$($TMP/bootstrap_test "$TMP/apf-decoded.pe" "$XEX")"
test "$TEST_TRANSCRIPT" = \
  "APF_IMPORTED_DATA_BOOTSTRAP_PASS frontier_slots=2 preserved_ordinals=11 xex_prefix=144 header_query=yes default_heap_absent=yes debug_dispatch=no transactional=yes title_entry_called=no"

cc -std=c11 -O1 -g -Wall -Wextra -Wpedantic -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer -Iinclude \
  "${COMMON_SOURCES[@]}" -o "$TMP/bootstrap_test_sanitize"
SANITIZER_TRANSCRIPT="$(ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
  "$TMP/bootstrap_test_sanitize" "$TMP/apf-decoded.pe" "$XEX")"
test "$SANITIZER_TRANSCRIPT" = "$TEST_TRANSCRIPT"

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$ARCHIVE" | awk '{print $1}')" = "$EXPECTED_ARCHIVE"

echo "APF_IMPORTED_DATA_FRONTIER_VALIDATION_PASS slots=13 xrefs=46 frontier=458 seeded=2 preserved=11 xex_header=separate default_heap=absent debug_dispatch=no transactional=yes sanitized=yes title_executed=false emulator=false originals_unchanged=true"
