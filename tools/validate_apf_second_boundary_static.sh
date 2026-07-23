#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
REPORT='reports/static_recomp/apf2k8_second_boundary_static.json'
DOC='docs/research/apf_second_boundary_static.md'
ANALYZER='tools/apf_second_boundary_static.py'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'

for path in "$XEX" "$VOLUME" "$REPORT" "$DOC" "$ANALYZER" \
    reports/static_recomp/apf2k8_guarded_first_entry_execution.json \
    reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json \
    reports/static_recomp/apf2k8_boot_leaf_adapters.json \
    reports/static_recomp/apf2k8_opcode_gap_sites.tsv \
    reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv \
    reports/headers/apf2k8_xex_report.json \
    research/functions/apf2k8/ledger/apf2k8_functions_19456_19967.jsonl \
    research/functions/apf2k8/ledger/apf2k8_functions_19968_20479.jsonl \
    src/static_runtime/apf_boot_leaf_adapters.c; do
    test -f "$path"
    test ! -L "$path"
done
test -d build-static-recomp-apf/ppc-opcode-switch-budget-instrumented
test ! -L build-static-recomp-apf/ppc-opcode-switch-budget-instrumented
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

mkdir -p /media/noah/Storage/.codex-tmp
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-second-boundary-static-XXXXXX)
cleanup() {
    rm -rf "$TMP"
}
trap cleanup EXIT

python3 -m py_compile "$ANALYZER"

# The analyzer may parse generated text, but it may not invoke a translated
# title function or delegate execution to another process.
python3 - "$ANALYZER" <<'PY'
import ast
from pathlib import Path
import re
import sys

tree = ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    name = None
    if isinstance(node.func, ast.Name):
        name = node.func.id
    elif isinstance(node.func, ast.Attribute):
        name = node.func.attr
    assert name not in {"_xstart", "system", "popen", "run", "call", "Popen"}
    assert name is None or re.fullmatch(r"sub_[0-9A-Fa-f]+", name) is None
PY

clang++-18 -std=c++20 -O2 tools/xex_extract_pe.cpp \
    -Itools/vendor/XenonRecomp/XenonUtils \
    -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
    -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
    tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
    -o "$TMP/xex_extract_pe"
"$TMP/xex_extract_pe" "$XEX" "$TMP/apf-decoded.pe" > "$TMP/extract.txt"
test "$(stat -c %s "$TMP/apf-decoded.pe")" = 54001664
test "$(sha256sum "$TMP/apf-decoded.pe" | awk '{print $1}')" = \
    "$EXPECTED_DECODED"

python3 "$ANALYZER" \
    --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report.json" > "$TMP/analyzer.txt"
cmp -s "$TMP/report.json" "$REPORT"
grep -Fq 'APF_SECOND_BOUNDARY_STATIC_REPORT start=0x84BF188C r3=0 next=NtAllocateVirtualMemory call=0x84BED7B8 return=0x84BED7BC thunk=0x84D0863C continuation_instructions=226 cumulative=264 executed=0 native_boot=0' \
    "$TMP/analyzer.txt"

python3 - "$REPORT" "$DOC" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
doc = doc_path.read_text(encoding="utf-8")

assert report["schema"] == "apf2k8_second_boundary_static/v1"
scope = report["scope"]
assert scope == {
    "entry_called": False,
    "main_menu_proved": False,
    "method": "nonexecuting path-specific static continuation",
    "native_boot_proved": False,
    "translated_title_functions_called": False,
}
start = report["start_state"]
assert (start["pc"], start["r1"], start["r3"], start["r30"]) == (
    "0x84BF188C", "0x7001FD10", "0x00000000", "0x00100000")
trace = report["static_trace"]
assert trace["continuation_instruction_count_through_next_call"] == 226
assert trace["cumulative_instruction_count_through_next_call"] == 264
assert trace["unique_pc_count"] == 181
assert trace["first_pc"] == "0x84BF188C"
assert trace["last_pc"] == "0x84BED7B8"
assert trace["ordered_pc_sha256"] == (
    "764c6c72387763e12d8338d9d437b2b815e64f29f88c10cedd761aa334bf31ec")
assert trace["unresolved_indirect_before_boundary"] is False
assert trace["opcode_candidate_before_boundary"] is False
assert trace["switch_tail_residue_before_boundary"] is False
assert trace["direct_call_chain"] == [
    "sub_84BF1850", "sub_84BED488", "__savegprlr_21",
    "sub_84BD8410", "sub_84BD6E60"]

boundary = report["next_boundary"]
assert boundary["classification"] == "typed_import"
assert boundary["name"] == "NtAllocateVirtualMemory"
assert boundary["ordinal"] == 204
assert boundary["thunk"] == "0x84D0863C"
assert boundary["call_pc"] == "0x84BED7B8"
assert boundary["return_pc"] == "0x84BED7BC"
assert boundary["typed_leaf_adapter_exact_site_supported"] is True
assert boundary["adapter_invoked_by_this_analysis"] is False
assert boundary["arguments"] == {
    "base_value_be_u32": "0x00000000",
    "r3_base_pointer": "0x7001FC50",
    "r4_size_pointer": "0x7001FD34",
    "r5_allocation_type": "0x60002000",
    "r6_protection": "0x00000004",
    "r7_debug_memory": "0x00000000",
    "size_value_be_u32": "0x00100000",
}
assert [row["order"] for row in report["ordered_prerequisites"]] == [1, 2, 3]
assert len(report["portme"]) == 2
assert all(line.startswith("// PORTME at 0x84BED7")
           for line in report["portme"])

assert doc.count("APF_SECOND_BOUNDARY_STATIC_VALIDATION_PASS") == 1
assert "Those 226 instructions were **not executed**" in doc
assert "This result does not prove allocation success" in doc
assert doc.count("// PORTME at 0x84BED7") == 2

# The report pins evidence, never embeds a decoded image or an execution dump.
serialized = report_path.read_text(encoding="utf-8")
for forbidden in ('"decoded_bytes"', '"raw_image_bytes"',
                  '"translated_title_execution"'):
    assert forbidden not in serialized
for item in report["inputs"]["ghidra_ledgers"]:
    path = Path(item["path"])
    data = path.read_bytes()
    assert len(data) == item["size"]
    assert hashlib.sha256(data).hexdigest() == item["sha256"]
PY

# Fail closed when one exact initialized-data prerequisite is changed.
cp --reflink=auto "$TMP/apf-decoded.pe" "$TMP/forged-decoded.pe"
printf '\x01' | dd of="$TMP/forged-decoded.pe" bs=1 \
    seek=$((0x852D64A0 - 0x82000000 + 3)) conv=notrunc status=none
if python3 "$ANALYZER" --decoded "$TMP/forged-decoded.pe" \
    --json "$TMP/forged.json" > "$TMP/forged.txt" 2>&1; then
    echo 'static continuation accepted a changed decoded image' >&2
    exit 1
fi
test ! -e "$TMP/forged.json"

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

echo 'APF_SECOND_BOUNDARY_STATIC_VALIDATION_PASS start=0x84BF188C r3=0 next=NtAllocateVirtualMemory call=0x84BED7B8 return=0x84BED7BC thunk=0x84D0863C continuation_instructions=226 cumulative=264 indirect=0 opcode=0 switch=0 title_executed=0 native_boot=0 originals_unchanged=yes'

