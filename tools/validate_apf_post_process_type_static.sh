#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
PRIOR='reports/static_recomp/apf2k8_guarded_fourth_boundary_execution.json'
REPORT='reports/static_recomp/apf2k8_post_process_type_static.json'
DOC='docs/research/apf_post_process_type_static.md'
ANALYZER='tools/apf_post_process_type_static.py'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'
EXPECTED_PRIOR='98403d883c3e20c69e2655482f67353ff30f68e24bd1815e7366de731c529b08'

for path in "$XEX" "$VOLUME" "$PRIOR" "$REPORT" "$DOC" "$ANALYZER" \
    reports/static_recomp/apf2k8_boot_leaf_adapters.json \
    build-static-recomp-apf/ppc-opcode-switch-budget-instrumented/ppc_recomp.217.cpp \
    reports/static_recomp/apf2k8_opcode_gap_sites.tsv \
    reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv \
    src/static_runtime/apf_boot_leaf_adapters.c; do
    test -f "$path"
    test ! -L "$path"
done
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
test "$(sha256sum "$PRIOR" | awk '{print $1}')" = "$EXPECTED_PRIOR"

mkdir -p /media/noah/Storage/.codex-tmp
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-post-process-static-XXXXXX)
trap 'rm -rf "$TMP"' EXIT

python3 -m py_compile "$ANALYZER"
python3 - "$ANALYZER" <<'PY'
import ast
from pathlib import Path
import sys
tree = ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        assert not ({item.name for item in node.names} & {"os", "subprocess"})
    if isinstance(node, ast.Call):
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        assert name not in {"exec", "eval", "system", "popen", "run", "Popen"}
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

python3 "$ANALYZER" --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report-one.json" > "$TMP/one.txt"
python3 "$ANALYZER" --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report-two.json" > "$TMP/two.txt"
cmp -s "$TMP/report-one.json" "$TMP/report-two.json"
cmp -s "$TMP/report-one.json" "$REPORT"
grep -Fq 'APF_POST_PROCESS_TYPE_STATIC_REPORT start=0x84BED90C prior=365 next=RtlInitializeCriticalSection call=0x84BED954 return=0x84BED958 continuation=654 cumulative=1019 indirect=0 opcode=0 switch=0 executed=0' \
    "$TMP/one.txt"

python3 - "$REPORT" "$DOC" <<'PY'
import json
from pathlib import Path
import sys
report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
doc = Path(sys.argv[2]).read_text(encoding="utf-8")
assert report["schema"] == "apf2k8_post_process_type_static/v1"
assert report["scope"]["translated_title_functions_called"] is False
assert report["scope"]["leaf_adapter_invoked"] is False
assert report["scope"]["native_boot_proved"] is False
start = report["start_checkpoint"]
assert (start["pc"], start["lr"], start["r3_process_type"]) == (
    "0x84BED90C", "0x84BED90C", "0x00000001")
assert start["prior_executed_guest_instructions"] == 365
trace = report["static_trace"]
assert trace["continuation_instruction_count_through_next_call"] == 654
assert trace["cumulative_instruction_count_through_next_call"] == 1019
assert trace["ordered_pc_sha256"] == (
    "8bb54714bb3065e9ca2af5c03795b0978e8a5d86246549f88f49d8a25900529d")
assert len(trace["ordered_guest_pcs"]) == 654
assert trace["ordered_guest_pcs"][0] == "0x84BED90C"
assert trace["ordered_guest_pcs"][-1] == "0x84BED954"
assert trace["ordered_guest_pcs"].count("0x84BED920") == 128
assert trace["unresolved_indirect_before_boundary"] is False
assert trace["opcode_candidate_intersection_count"] == 0
assert trace["switch_tail_residue_intersection_count"] == 0
page = report["deterministic_page_before_boundary"]
assert page["allocator_list_head_count"] == 128
assert page["critical_section_address"] == "0x40000610"
assert page["nonzero_byte_count"] == 799
assert page["page_sha256"] == (
    "8174339c35c7a8d0f68fcce0ed9c10697dad9fe6a7a0237e0d6738a35edfda07")
assert page["allocation_fnv1a64"] == "0xF663B4BBF571B2AD"
boundary = report["next_boundary"]
assert boundary["name"] == "RtlInitializeCriticalSection"
assert boundary["call_pc"] == "0x84BED954"
assert boundary["return_pc"] == "0x84BED958"
assert boundary["thunk"] == "0x84D07FBC"
assert boundary["arguments"] == {"r3_critical_section": "0x40000610"}
assert boundary["adapter_invoked_by_this_analysis"] is False
assert len(report["portme"]) == 3
for marker in ("654 deterministic guest instructions", "0x84BED954",
               "0x84BED958", "128", "799", "0xF663B4BBF571B2AD",
               "proves neither native"):
    assert marker in doc
PY

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
printf '%s\n' \
    'APF_POST_PROCESS_TYPE_STATIC_VALIDATION_PASS start=0x84BED90C next=0x84BED954 instructions=654 cumulative=1019 executed=no originals_unchanged=yes'
