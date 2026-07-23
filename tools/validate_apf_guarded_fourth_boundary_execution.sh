#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
REPORT='reports/static_recomp/apf2k8_guarded_fourth_boundary_execution.json'
TRANSCRIPT='reports/static_recomp/apf2k8_guarded_fourth_boundary_execution.txt'
DOC='docs/research/apf_guarded_fourth_boundary_execution.md'
DRIVER='tools/apf_guarded_fourth_boundary_execute.py'
PRIOR='reports/static_recomp/apf2k8_guarded_third_boundary_execution.json'
STATIC='reports/static_recomp/apf2k8_post_commit_static.json'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'
EXPECTED_PRIOR='cf16bb85f8065812d3987216abcfae45aee775e758354e152294f5cfb4708c17'
EXPECTED_STATIC='5831b87d8ccc75c1b418e9b3ebe2bd1da35b621214bdde094c1e65fbb9cf6148'

for path in "$XEX" "$VOLUME" "$REPORT" "$TRANSCRIPT" "$DOC" \
    "$DRIVER" "$PRIOR" "$STATIC" tools/apf_post_commit_static.py \
    tools/apf_guarded_third_boundary_execute.py \
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
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-fourth-boundary-validation-XXXXXX)
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

# Revalidate the immediate dynamic and static prerequisites independently.
tools/validate_apf_guarded_third_boundary_execution.sh > "$TMP/third.txt"
grep -Fq 'APF_GUARDED_THIRD_BOUNDARY_EXECUTION_VALIDATION_PASS' \
    "$TMP/third.txt"
tools/validate_apf_post_commit_static.sh > "$TMP/static.txt"
grep -Fq 'APF_POST_COMMIT_STATIC_VALIDATION_PASS' "$TMP/static.txt"

python3 "$DRIVER" \
    --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report.json" \
    --transcript "$TMP/transcript.txt" \
    --temp-root "$TMP" \
    --jobs "${APF_GUARDED_FOURTH_BOUNDARY_JOBS:-12}" \
    > "$TMP/driver.txt"
cmp -s "$TMP/report.json" "$REPORT"
cmp -s "$TMP/transcript.txt" "$TRANSCRIPT"
grep -Fq 'outcome=expected_fourth_boundary signal=0 entry_authorized=1 entry_called=1' \
    "$TRANSCRIPT"
grep -Fq 'instructions=365 function_dispatches=4 last_pc=0x84BED908 lr=0x84BED90C r3=0x00000001' \
    "$TRANSCRIPT"
grep -Fq 'post_commit_ledger=1 post_commit_backing=1 post_commit_global=0x00000000 post_commit_fnv=0x8179632E8A902325' \
    "$TRANSCRIPT"
grep -Fq 'fourth_instructions=365 fourth_thunk=0x84D0868C fourth_lr=0x84BED90C fourth_r3_in=0x00000000 fourth_r3_out=0x00000001 fourth_ledger=1 fourth_backing=1 fourth_global=0x00000000 fourth_fnv=0x233B6EC7DF8372AE' \
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
assert report["schema"] == "apf2k8_guarded_fourth_boundary_execution/v1"
assert report["result"] == {
    "child_outcome": "expected_fourth_boundary",
    "continued_past_fourth_typed_boundary": False,
    "continued_past_third_typed_boundary": True,
    "expected_fourth_typed_boundary_reached": True,
    "fourth_typed_adapter_completed": True,
    "guarded_third_boundary_execution_revalidated": True,
    "main_menu_proved": False,
    "native_boot_proved": False,
    "post_commit_static_proof_revalidated": True,
    "signal_number": 0,
    "translated_title_code_executed": True,
}
gates = report["authorization_gates"]
assert gates["instruction_limit"] == 4096
assert gates["function_dispatch_limit"] == 64
assert gates["timeout_milliseconds"] == 5000
assert gates["instruction_hook_count"] == 1808124
assert gates["mapping_count"] == 60731
assert gates["typed_import_count"] == 30
assert gates["post_commit_vm_ledger_exact_before_continuation"] is True
assert gates["post_commit_backing_exact_before_continuation"] is True
assert gates["post_commit_global_flags_exact_before_continuation"] is True
execution = report["generated_execution"]
assert execution["executed_guest_instruction_count"] == 365
assert execution["function_dispatch_count"] == 4
assert execution["last_executed_guest_pc"] == "0x84BED908"
assert execution["full_ordered_pc_sha256"] == (
    "8465e1bf0be2ed4bcf8a350294a864acb10589e49879b5b3a12909e0529c6b32")
assert execution["post_commit_ordered_pc_sha256"] == (
    "0220f64faaaff52e8629f9a7c6d0d4d33e9d1c9c49054add334f75f926ebc967")
pcs = execution["ordered_guest_pcs"]
assert len(pcs) == 365
assert pcs[282:284] == ["0x84BED808", "0x84BED80C"]
assert pcs[-1] == "0x84BED908"
fourth = execution["fourth_boundary"]
assert fourth == {
    "adapter_status": "ok",
    "arguments": {},
    "call_pc": "0x84BED908",
    "generated_return_instruction_executed": False,
    "import": "KeGetCurrentProcessType",
    "instruction_count_at_call": 365,
    "r3_before_adapter": "0x00000000",
    "r3_process_type_result": "0x00000001",
    "return_pc": "0x84BED90C",
    "terminal_semantics": (
        "existing typed process-type adapter completed; bridge threw before "
        "generated instruction 0x84BED90C"),
    "thunk": "0x84D0868C",
}
state = report["virtual_memory_and_initialization"]
assert state == {
    "active_allocation_count": 1,
    "allocation_fnv1a64_after_initialization": "0x233B6EC7DF8372AE",
    "allocation_page_count": 16,
    "committed_page_count": 1,
    "global_flags_be_u32": "0x00000000",
    "initialized_committed_page_exact": True,
    "initialized_committed_page_sha256": (
        "f0072c49de8cb307781499a69e189990e2b0837652d8afb232227f1a18da5d85"),
    "initialized_nonzero_byte_count": 34,
    "remaining_15_page_pattern_exact": True,
    "remaining_reserved_page_count": 15,
    "vm_ledger_exact": True,
}
assert report["isolation"]["normal_host_shell_linked"] is False
assert report["isolation"]["normal_host_shell_modified"] is False
assert report["isolation"]["retail_inputs_modified"] is False
assert report["isolation"]["temporary_generated_objects_deleted"] is True
assert len(report["portme"]) == 3
assert report["portme"][0].startswith("// PORTME at 0x84BED90C")
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
assert values["EXPECTED_FOURTH_CALL"] == 0x84BED908
assert values["EXPECTED_FOURTH_RETURN"] == 0x84BED90C
assert values["EXPECTED_POST_COMMIT_INSTRUCTIONS"] == 82
assert values["EXPECTED_CUMULATIVE_INSTRUCTIONS"] == 365
for marker in ("365 guest", "0x84BED908", "0x84BED90C", "process type 1",
               "34 nonzero bytes", "0x233B6EC7DF8372AE",
               "4096-instruction", "64-dispatch", "five-second",
               "does not prove native boot or the main menu",
               "// PORTME at 0x84BED90C"):
    assert marker in doc
PY

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
printf '%s\n' \
    'APF_GUARDED_FOURTH_BOUNDARY_EXECUTION_VALIDATION_PASS instructions=365 dispatches=4 process_type=1 stop=0x84BED90C native_boot=no originals_unchanged=yes'
