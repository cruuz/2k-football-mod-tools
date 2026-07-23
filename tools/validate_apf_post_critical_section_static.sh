#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
REPORT='reports/static_recomp/apf2k8_post_critical_section_static.json'
DOC='docs/research/apf_post_critical_section_static.md'
ANALYZER='tools/apf_post_critical_section_static.py'
PRIOR='reports/static_recomp/apf2k8_guarded_fifth_boundary_execution.json'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_PRIOR='d12897cd8c5575c1f770a7f5429f02777c1028574014fb7e59def40dade9478d'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'

for path in "$XEX" "$VOLUME" "$REPORT" "$DOC" "$ANALYZER" "$PRIOR" \
    reports/static_recomp/apf2k8_boot_leaf_adapters.json \
    src/static_runtime/apf_boot_leaf_adapters.c \
    build-static-recomp-apf/ppc-opcode-switch-budget-instrumented/ppc_recomp.217.cpp \
    build-static-recomp-apf/ppc-opcode-switch-budget-instrumented/ppc_recomp.212.cpp \
    reports/static_recomp/apf2k8_opcode_gap_sites.tsv \
    reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv; do
    test -f "$path"
    test ! -L "$path"
done
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
test "$(sha256sum "$PRIOR" | awk '{print $1}')" = "$EXPECTED_PRIOR"

mkdir -p .codex-tmp
TMP=$(mktemp -d .codex-tmp/apf-post-critical-validation-XXXXXX)
trap 'rm -rf "$TMP"' EXIT
python3 -m py_compile "$ANALYZER"

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
    --json "$TMP/report.json" > "$TMP/analyzer.txt"
cmp -s "$TMP/report.json" "$REPORT"
grep -Fq 'APF_POST_CRITICAL_SECTION_STATIC_REPORT start=0x84BED958 prior=1019 next=NtAllocateVirtualMemory operation=overlap_commit call=0x84BECE14 return=0x84BECE18 continuation=60 cumulative=1079 indirect=0 opcode=0 switch=0 executed=0' \
    "$TMP/analyzer.txt"

python3 - "$REPORT" "$DOC" "$ANALYZER" <<'PY'
import ast
import hashlib
import json
from pathlib import Path
import sys
report_path, doc_path, analyzer_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
doc = doc_path.read_text(encoding="utf-8")
analyzer = analyzer_path.read_text(encoding="utf-8")
assert report["schema"] == "apf2k8_post_critical_section_static/v1"
scope = report["scope"]
assert scope["translated_title_functions_called"] is False
assert scope["leaf_adapter_invoked"] is False
assert scope["native_boot_proved"] is False
assert scope["main_menu_proved"] is False
start = report["start_checkpoint"]
assert start["pc"] == "0x84BED958"
assert start["prior_executed_guest_instructions"] == 1019
trace = report["static_trace"]
assert trace["continuation_instruction_count_through_next_call"] == 60
assert trace["cumulative_instruction_count_through_next_call"] == 1079
assert trace["unique_pc_count"] == 60
assert trace["ordered_pc_sha256"] == (
    "275d0d13762e1e8d32d29b05ae0a83c831205e185b40090be95097fde891d398")
assert trace["ordered_guest_pcs"][0] == "0x84BED958"
assert trace["ordered_guest_pcs"][-1] == "0x84BECE14"
assert trace["unresolved_indirect_before_boundary"] is False
assert trace["opcode_candidate_intersection_count"] == 0
assert trace["switch_tail_residue_intersection_count"] == 0
state = report["deterministic_state_before_boundary"]
assert state["committed_page"]["nonzero_byte_count"] == 814
assert state["committed_page"]["sha256"] == (
    "d3123ade0ce122f0daab9b571be7d07de8f6e1e700ed4a575a34614d776cbaf9")
assert state["allocation_fnv1a64"] == "0xA2F6E3132B6EE02A"
assert state["base_cell"]["address"] == "0x7001FC3C"
assert state["size_cell"]["be_u32"] == "0x00010060"
boundary = report["next_boundary"]
assert boundary["name"] == "NtAllocateVirtualMemory"
assert boundary["operation"].startswith("overlapping commit")
assert boundary["call_pc"] == "0x84BECE14"
assert boundary["return_pc"] == "0x84BECE18"
assert boundary["thunk"] == "0x84D0863C"
assert boundary["arguments"]["r5_allocation_type"] == "0x60001000"
assert boundary["typed_leaf_adapter_exact_site_supported"] is True
assert boundary["adapter_invoked_by_this_analysis"] is False
assert report["authorization"]["generated_return_0x84BECE18_executed"] is False
assert len(report["portme"]) == 3
assert report["portme"][0].startswith("// PORTME at 0x84BED958")
for item in report["inputs"].values():
    if "path" not in item:
        continue
    path = Path(item["path"])
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == item["size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
tree = ast.parse(analyzer)
values = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
       isinstance(node.targets[0], ast.Name):
        try:
            values[node.targets[0].id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            pass
assert values["SCHEMA"] == "apf2k8_post_critical_section_static/v1"
for marker in ("60 unique guest instructions", "1,079", "0x84BECE14",
               "0x84BECE18", "0x7001FC3C", "0x00010060", "814 nonzero",
               "0xA2F6E3132B6EE02A", "proves neither native boot",
               "// PORTME at 0x84BED958"):
    assert marker in doc
PY

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
printf '%s\n' \
    'APF_POST_CRITICAL_SECTION_STATIC_VALIDATION_PASS start=0x84BED958 next=0x84BECE14 instructions=60 cumulative=1079 executed=no originals_unchanged=yes'
