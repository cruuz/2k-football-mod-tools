#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
PRIOR='reports/static_recomp/apf2k8_guarded_third_boundary_execution.json'
REPORT='reports/static_recomp/apf2k8_post_commit_static.json'
DOC='docs/research/apf_post_commit_static.md'
ANALYZER='tools/apf_post_commit_static.py'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'
EXPECTED_PRIOR='cf16bb85f8065812d3987216abcfae45aee775e758354e152294f5cfb4708c17'

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
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-post-commit-static-XXXXXX)
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
grep -Fq 'APF_POST_COMMIT_STATIC_REPORT start=0x84BED80C prior=283 next=KeGetCurrentProcessType call=0x84BED908 return=0x84BED90C continuation=82 cumulative=365 indirect=0 opcode=0 switch=0 executed=0' \
    "$TMP/one.txt"

python3 - "$REPORT" "$DOC" <<'PY'
import json
from pathlib import Path
import sys
report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
doc = Path(sys.argv[2]).read_text(encoding="utf-8")
assert report["schema"] == "apf2k8_post_commit_static/v1"
assert report["scope"] == {
    "leaf_adapter_invoked": False,
    "main_menu_proved": False,
    "method": "nonexecuting path-specific static continuation",
    "native_boot_proved": False,
    "subprocess_invoked": False,
    "translated_title_functions_called": False,
}
start = report["start_checkpoint"]
assert (start["pc"], start["lr"], start["r3_ntstatus"]) == (
    "0x84BED80C", "0x84BED80C", "0x00000000")
assert start["prior_executed_guest_instructions"] == 283
assert start["retail_global_flags"]["be_u32"] == "0x00000000"
trace = report["static_trace"]
assert trace["continuation_instruction_count_through_next_call"] == 82
assert trace["cumulative_instruction_count_through_next_call"] == 365
assert trace["ordered_pc_sha256"] == (
    "0220f64faaaff52e8629f9a7c6d0d4d33e9d1c9c49054add334f75f926ebc967")
assert len(trace["ordered_guest_pcs"]) == 82
assert trace["ordered_guest_pcs"][0] == "0x84BED80C"
assert trace["ordered_guest_pcs"][-1] == "0x84BED908"
assert trace["unresolved_indirect_before_boundary"] is False
assert trace["opcode_candidate_intersection_count"] == 0
assert trace["switch_tail_residue_intersection_count"] == 0
page = report["deterministic_page_initialization"]
assert page["list_iteration_count"] == 8
assert page["nonzero_byte_count"] == 34
assert page["page_sha256_before_process_type_call"] == (
    "f0072c49de8cb307781499a69e189990e2b0837652d8afb232227f1a18da5d85")
assert page["allocation_fnv1a64_before_process_type_call"] == (
    "0x233B6EC7DF8372AE")
boundary = report["next_boundary"]
assert boundary == {
    "adapter_invoked_by_this_analysis": False,
    "arguments": {},
    "call_pc": "0x84BED908",
    "classification": "typed_import",
    "configured_result_r3": "0x00000001",
    "library": "xboxkrnl.exe",
    "name": "KeGetCurrentProcessType",
    "ordinal": 102,
    "return_pc": "0x84BED90C",
    "thunk": "0x84D0868C",
    "typed_leaf_adapter_exact_site_supported": True,
}
assert len(report["portme"]) == 3
for marker in ("82 guest instructions", "0x84BED908", "0x84BED90C",
               "eight", "34", "0x233B6EC7DF8372AE",
               "neither native boot nor the main menu"):
    assert marker in doc
PY

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
printf '%s\n' \
    'APF_POST_COMMIT_STATIC_VALIDATION_PASS start=0x84BED80C next=0x84BED908 instructions=82 cumulative=365 executed=no originals_unchanged=yes'
