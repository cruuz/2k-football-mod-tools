#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
REPORT='reports/static_recomp/apf2k8_guarded_fifth_boundary_execution.json'
TRANSCRIPT='reports/static_recomp/apf2k8_guarded_fifth_boundary_execution.txt'
DOC='docs/research/apf_guarded_fifth_boundary_execution.md'
DRIVER='tools/apf_guarded_fifth_boundary_execute.py'
PRIOR='reports/static_recomp/apf2k8_guarded_fourth_boundary_execution.json'
STATIC='reports/static_recomp/apf2k8_post_process_type_static.json'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'
EXPECTED_PRIOR='98403d883c3e20c69e2655482f67353ff30f68e24bd1815e7366de731c529b08'
EXPECTED_STATIC='1ad608809fd15e44c50c3ef7601683a0d90a6a658f4e86636ec3d3c0b39f08c3'

for path in "$XEX" "$VOLUME" "$REPORT" "$TRANSCRIPT" "$DOC" \
    "$DRIVER" "$PRIOR" "$STATIC" tools/apf_post_process_type_static.py \
    tools/apf_guarded_fourth_boundary_execute.py \
    reports/static_recomp/apf2k8_boot_leaf_adapters.json \
    reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json \
    reports/static_recomp/apf2k8_guest_instruction_budget_instrumentation.json \
    reports/headers/apf2k8_xex_report.json \
    src/static_runtime/apf_first_entry_gate.c \
    src/static_runtime/apf_first_entry_xenon_bridge.cpp \
    src/static_runtime/apf_guest_instruction_budget.cpp \
    src/static_runtime/apf_imported_data_bootstrap.c \
    src/static_runtime/apf_boot_leaf_adapters.c; do
    test -f "$path"
    test ! -L "$path"
done
test -d build-static-recomp-apf/ppc-opcode-switch-composed
test -d build-static-recomp-apf/ppc-opcode-switch-budget-instrumented
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
test "$(sha256sum "$PRIOR" | awk '{print $1}')" = "$EXPECTED_PRIOR"
test "$(sha256sum "$STATIC" | awk '{print $1}')" = "$EXPECTED_STATIC"

mkdir -p /media/noah/Storage/.codex-tmp
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-fifth-validation-XXXXXX)
trap 'rm -rf "$TMP"' EXIT
python3 -m py_compile "$DRIVER"

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

tools/validate_apf_post_process_type_static.sh > "$TMP/static.txt"
grep -Fq 'APF_POST_PROCESS_TYPE_STATIC_VALIDATION_PASS' "$TMP/static.txt"

python3 "$DRIVER" \
    --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report.json" \
    --transcript "$TMP/transcript.txt" \
    --temp-root "$TMP" \
    --jobs "${APF_GUARDED_FIFTH_BOUNDARY_JOBS:-12}" \
    > "$TMP/driver.txt"
cmp -s "$TMP/report.json" "$REPORT"
cmp -s "$TMP/transcript.txt" "$TRANSCRIPT"
grep -Fq 'outcome=expected_fifth_boundary signal=0 entry_authorized=1 entry_called=1' \
    "$TRANSCRIPT"
grep -Fq 'instructions=1019 function_dispatches=5 last_pc=0x84BED954 lr=0x84BED958 r3=0x40000610' \
    "$TRANSCRIPT"
grep -Fq 'fifth_instructions=1019 fifth_thunk=0x84D07FBC fifth_lr=0x84BED958 fifth_r3_in=0x40000610 fifth_r3_out=0x40000610 fifth_r21=0x40000610 fifth_r29=0x40000610' \
    "$TRANSCRIPT"
grep -Fq 'fifth_ledger=1 fifth_page=1 fifth_global=0x00000000 fifth_fnv_before=0xF663B4BBF571B2AD fifth_cs_exact=1 fifth_fnv_after=0xD0D16B728ECA1764' \
    "$TRANSCRIPT"
grep -Fq 'vm_pages=4096 vm_allocations=1 reserved_pages=15 committed_pages=1 ledger_exact=1 initialized_page_exact=1 remaining_pattern_exact=1' \
    "$TRANSCRIPT"
grep -Fq 'containment_normal=1 containment_signal=1 containment_timeout=1' \
    "$TRANSCRIPT"
grep -Fq 'temporary_outputs_deleted=1' "$TMP/driver.txt"

python3 - "$REPORT" "$DOC" "$DRIVER" <<'PY'
import ast
import hashlib
import json
from pathlib import Path
import sys
report_path, doc_path, driver_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
doc = doc_path.read_text(encoding="utf-8")
driver = driver_path.read_text(encoding="utf-8")
assert report["schema"] == "apf2k8_guarded_fifth_boundary_execution/v1"
result = report["result"]
assert result["child_outcome"] == "expected_fifth_boundary"
assert result["continued_past_fourth_typed_boundary"] is True
assert result["expected_fifth_typed_boundary_reached"] is True
assert result["fifth_typed_adapter_completed"] is True
assert result["continued_past_fifth_typed_boundary"] is False
assert result["native_boot_proved"] is False
assert result["main_menu_proved"] is False
gates = report["authorization_gates"]
assert gates["instruction_limit"] == 4096
assert gates["function_dispatch_limit"] == 64
assert gates["timeout_milliseconds"] == 5000
assert gates["instruction_hook_count"] == 1808124
assert gates["mapping_count"] == 60731
assert gates["typed_import_count"] == 30
execution = report["generated_execution"]
assert execution["executed_guest_instruction_count"] == 1019
assert execution["function_dispatch_count"] == 5
assert execution["last_executed_guest_pc"] == "0x84BED954"
assert execution["full_ordered_pc_sha256"] == (
    "bbe4ce2c3a5a9a00c2a69593ce79e14aae66be1ed882edabccf25215e99331d4")
assert execution["post_process_type_ordered_pc_sha256"] == (
    "8bb54714bb3065e9ca2af5c03795b0978e8a5d86246549f88f49d8a25900529d")
pcs = execution["ordered_guest_pcs"]
assert len(pcs) == 1019
assert pcs[364:366] == ["0x84BED908", "0x84BED90C"]
assert pcs[-1] == "0x84BED954"
fifth = execution["fifth_boundary"]
assert fifth["import"] == "RtlInitializeCriticalSection"
assert fifth["call_pc"] == "0x84BED954"
assert fifth["return_pc"] == "0x84BED958"
assert fifth["thunk"] == "0x84D07FBC"
assert fifth["arguments"] == {"r3_critical_section": "0x40000610"}
assert fifth["critical_section_initialized_exact"] is True
assert fifth["generated_return_instruction_executed"] is False
state = report["virtual_memory_and_initialization"]
assert state["allocator_list_head_count"] == 128
assert state["pre_adapter_nonzero_byte_count"] == 799
assert state["pre_adapter_page_sha256"] == (
    "8174339c35c7a8d0f68fcce0ed9c10697dad9fe6a7a0237e0d6738a35edfda07")
assert state["post_adapter_nonzero_byte_count"] == 811
assert state["post_adapter_page_sha256"] == (
    "87438b39f9268a5dd7e49711573bd66cab9b0bb378579b0ddd962b884506f1f3")
assert state["post_adapter_allocation_fnv1a64"] == "0xD0D16B728ECA1764"
assert report["isolation"]["normal_host_shell_linked"] is False
assert report["isolation"]["normal_host_shell_modified"] is False
assert report["isolation"]["retail_inputs_modified"] is False
assert len(report["portme"]) == 3
assert report["portme"][0].startswith("// PORTME at 0x84BED958")
for item in report["inputs"]["local_files"]:
    path = Path(item["path"])
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == item["size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
values = {}
for node in ast.parse(driver).body:
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
       isinstance(node.targets[0], ast.Name):
        try:
            values[node.targets[0].id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            pass
assert values["EXPECTED_FIFTH_CALL"] == 0x84BED954
assert values["EXPECTED_FIFTH_RETURN"] == 0x84BED958
assert values["EXPECTED_CONTINUATION_INSTRUCTIONS"] == 654
assert values["EXPECTED_CUMULATIVE_INSTRUCTIONS"] == 1019
for marker in ("1,019", "0x84BED954", "0x84BED958", "0x40000610",
               "811 nonzero", "0xD0D16B728ECA1764", "4,096-instruction",
               "64-dispatch", "five-second", "does not prove",
               "// PORTME at 0x84BED958"):
    assert marker in doc
PY

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
printf '%s\n' \
    'APF_GUARDED_FIFTH_BOUNDARY_EXECUTION_VALIDATION_PASS instructions=1019 dispatches=5 critical_section=0x40000610 stop=0x84BED958 native_boot=no originals_unchanged=yes'
