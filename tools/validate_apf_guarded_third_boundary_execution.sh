#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
REPORT='reports/static_recomp/apf2k8_guarded_third_boundary_execution.json'
TRANSCRIPT='reports/static_recomp/apf2k8_guarded_third_boundary_execution.txt'
DOC='docs/research/apf_guarded_third_boundary_execution.md'
DRIVER='tools/apf_guarded_third_boundary_execute.py'
SECOND='reports/static_recomp/apf2k8_guarded_second_boundary_execution.json'
POST_RESERVE='reports/static_recomp/apf2k8_post_reserve_static.json'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'
EXPECTED_SECOND='d60c0116a5445624453d867c8600c0466b06a0fb64f3bc183c7ebe730c651761'
EXPECTED_POST_RESERVE='1a0b9ac08bc17007a7d7922024d6703eab702fb900bf60d08bbc84fda566cc2c'

for path in "$XEX" "$VOLUME" "$REPORT" "$TRANSCRIPT" "$DOC" \
    "$DRIVER" "$SECOND" "$POST_RESERVE" \
    tools/apf_guarded_first_entry_execute.py \
    tools/apf_guarded_second_boundary_execute.py \
    tools/apf_post_reserve_static.py \
    reports/static_recomp/apf2k8_guarded_first_entry_execution.json \
    reports/static_recomp/apf2k8_second_boundary_static.json \
    reports/static_recomp/apf2k8_boot_leaf_adapters.json \
    reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json \
    reports/static_recomp/apf2k8_guest_instruction_budget_instrumentation.json \
    reports/headers/apf2k8_xex_report.json \
    include/static_runtime/apf_first_entry_gate.h \
    include/static_runtime/apf_first_entry_xenon_bridge.h \
    include/static_runtime/apf_guest_instruction_budget.h \
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
test ! -L build-static-recomp-apf/ppc-opcode-switch-composed
test ! -L build-static-recomp-apf/ppc-opcode-switch-budget-instrumented
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
test "$(sha256sum "$SECOND" | awk '{print $1}')" = "$EXPECTED_SECOND"
test "$(sha256sum "$POST_RESERVE" | awk '{print $1}')" = \
    "$EXPECTED_POST_RESERVE"

mkdir -p /media/noah/Storage/.codex-tmp
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-third-boundary-validation-XXXXXX)
cleanup() {
    rm -rf "$TMP"
}
trap cleanup EXIT

python3 -m py_compile "$DRIVER"

clang++-18 -std=c++20 -O2 tools/xex_extract_pe.cpp \
    -Itools/vendor/XenonRecomp/XenonUtils \
    -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
    -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
    tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
    -o "$TMP/xex_extract_pe"
"$TMP/xex_extract_pe" "$XEX" "$TMP/apf-decoded.pe" \
    > "$TMP/extract.txt"
test "$(stat -c %s "$TMP/apf-decoded.pe")" = 54001664
test "$(sha256sum "$TMP/apf-decoded.pe" | awk '{print $1}')" = \
    "$EXPECTED_DECODED"

# Re-execute both immediate prerequisites.  The guarded-second validator in
# turn revalidates its complete first/header/reserve authorization chain.
tools/validate_apf_guarded_second_boundary_execution.sh \
    > "$TMP/second.txt"
grep -Fq 'APF_GUARDED_SECOND_BOUNDARY_EXECUTION_VALIDATION_PASS' \
    "$TMP/second.txt"
tools/validate_apf_post_reserve_static.sh > "$TMP/post-reserve.txt"
grep -Fq 'APF_POST_RESERVE_STATIC_VALIDATION_PASS' \
    "$TMP/post-reserve.txt"

python3 "$DRIVER" \
    --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report.json" \
    --transcript "$TMP/transcript.txt" \
    --temp-root "$TMP" \
    --jobs "${APF_GUARDED_THIRD_BOUNDARY_JOBS:-12}" \
    > "$TMP/driver.txt"
cmp -s "$TMP/report.json" "$REPORT"
cmp -s "$TMP/transcript.txt" "$TRANSCRIPT"
grep -Fq 'outcome=expected_third_boundary signal=0 entry_authorized=1 entry_called=1' \
    "$TRANSCRIPT"
grep -Fq 'instructions=283 function_dispatches=3 last_pc=0x84BED808 lr=0x84BED80C r3=0x00000000' \
    "$TRANSCRIPT"
grep -Fq 'reserve_ledger_before=1 reserve_pattern_before=1 reserve_fnv_before=0x1F5E0DF9BC822325' \
    "$TRANSCRIPT"
grep -Fq 'third_r3_in=0x7001FC54 third_r4_in=0x7001FD3C third_r5_in=0x60001000 third_r6_in=0x00000004 third_r7_in=0x00000000 third_r3_out=0x00000000' \
    "$TRANSCRIPT"
grep -Fq 'vm_pages=4096 vm_allocations=1 reserved_pages=15 committed_pages=1 ledger_exact=1 first_page_zeroed=1 remaining_pattern_exact=1' \
    "$TRANSCRIPT"
grep -Fq 'backing_fnv_before=0x1F5E0DF9BC822325 backing_fnv_after=0x8179632E8A902325' \
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

assert report["schema"] == "apf2k8_guarded_third_boundary_execution/v1"
assert report["result"] == {
    "child_outcome": "expected_third_boundary",
    "continued_past_first_typed_boundary": True,
    "continued_past_second_typed_boundary": True,
    "continued_past_third_typed_boundary": False,
    "entry_call_authorized_in_isolated_child": True,
    "entry_called_in_isolated_child": True,
    "expected_second_typed_boundary_reached": True,
    "expected_third_typed_boundary_reached": True,
    "first_typed_boundary_returned_under_exact_mode": True,
    "guarded_second_boundary_execution_revalidated": True,
    "main_menu_proved": False,
    "native_boot_proved": False,
    "post_reserve_static_proof_revalidated": True,
    "second_typed_adapter_completed": True,
    "signal_number": 0,
    "static_second_boundary_proof_revalidated": True,
    "third_typed_adapter_completed": True,
    "translated_title_code_executed": True,
    "v2_first_boundary_execution_revalidated": True,
}

gates = report["authorization_gates"]
assert gates["all_instruction_hooks_recounted"] == 1808124
assert gates["dispatch_mapping_count_revalidated"] == 60731
assert gates["typed_bridge_binding_count_revalidated"] == 30
assert gates["instruction_limit"] == 4096
assert gates["function_dispatch_limit"] == 64
assert gates["timeout_milliseconds"] == 5000
assert gates["reserve_vm_ledger_exact_before_continuation"] is True
assert gates["reserve_backing_pattern_exact_before_continuation"] is True
assert gates["third_adapter_dynamic_pc_lr_abi_gate"] is True

execution = report["generated_execution"]
assert execution["entry"] == "0x84BE9D08"
assert execution["executed_guest_instruction_count"] == 283
assert execution["function_dispatch_count"] == 3
assert execution["last_executed_guest_pc"] == "0x84BED808"
assert execution["full_ordered_pc_sha256"] == (
    "e10d02a5f5a6df5580167bc59ebe0ca23abcd6bb7c7009b56ed26824301ab2bb")
assert execution["first_boundary_ordered_pc_sha256"] == (
    "7ce502bf4aa0897bfe95a390ccf6d7e01b305dcb936ae20f178fff4bae7601ce")
assert execution["continuation_ordered_pc_sha256"] == (
    "764c6c72387763e12d8338d9d437b2b815e64f29f88c10cedd761aa334bf31ec")
assert execution["post_reserve_ordered_pc_sha256"] == (
    "df3f3f6aec6fd3b6dbede92272b7a2ae22a6cbba63c9c60d0d9c4d4e9fe638fd")
pcs = execution["ordered_guest_pcs"]
assert len(pcs) == 283
assert pcs[37:39] == ["0x84BF1888", "0x84BF188C"]
assert pcs[263:265] == ["0x84BED7B8", "0x84BED7BC"]
assert pcs[-1] == "0x84BED808"

second = execution["second_boundary"]
assert (second["call_pc"], second["return_pc"], second["thunk"]) == (
    "0x84BED7B8", "0x84BED7BC", "0x84D0863C")
assert second["ntstatus_r3"] == "0x00000000"
assert second["generated_return_instruction_executed"] is True
assert second["reserve_vm_ledger_exact_before_continuation"] is True
assert second["reserve_backing_pattern_exact_before_continuation"] is True
assert second["reserve_backing_fnv1a64_before_continuation"] == (
    "0x1F5E0DF9BC822325")

third = execution["third_boundary"]
assert (third["call_pc"], third["return_pc"], third["thunk"]) == (
    "0x84BED808", "0x84BED80C", "0x84D0863C")
assert third["instruction_count_at_call"] == 283
assert third["arguments"] == {
    "base_value_before_be_u32": "0x40000000",
    "r3_base_pointer": "0x7001FC54",
    "r4_size_pointer": "0x7001FD3C",
    "r5_allocation_type": "0x60001000",
    "r6_protection": "0x00000004",
    "r7_debug_memory": "0x00000000",
    "size_value_before_be_u32": "0x00010000",
}
assert third["adapter_status"] == "ok"
assert third["ntstatus_r3"] == "0x00000000"
assert third["base_value_after_be_u32"] == "0x40000000"
assert third["size_value_after_be_u32"] == "0x00010000"
assert third["generated_return_instruction_executed"] is False

ledger = report["virtual_memory_ledger"]
assert ledger == {
    "active_allocation_count": 1,
    "allocation_base_page": 0,
    "allocation_page_count": 16,
    "allocation_protection": "0x00000004",
    "allocation_slot": 0,
    "arena_base": "0x40000000",
    "arena_size": "0x10000000",
    "backing_fnv1a64_after": "0x8179632E8A902325",
    "backing_fnv1a64_before": "0x1F5E0DF9BC822325",
    "committed_page_count": 1,
    "first_page_backing_zeroed": True,
    "first_page_state": "commit",
    "page_count": 4096,
    "page_size": "0x00010000",
    "remaining_allocation_backing_pattern_exact": True,
    "remaining_allocation_page_state": "reserve",
    "remaining_allocation_slots_inactive": True,
    "remaining_pages_free": True,
    "remaining_reserved_page_count": 15,
}
assert report["outcome_classification"]["observed"] == (
    "expected_third_boundary")
assert report["isolation"]["normal_host_shell_linked"] is False
assert report["isolation"]["normal_host_shell_modified"] is False
assert report["isolation"]["retail_inputs_modified"] is False
assert report["isolation"]["temporary_generated_objects_deleted"] is True
assert len(report["portme"]) == 4
assert all(line.startswith("// PORTME") for line in report["portme"])

for item in report["inputs"]["local_files"]:
    path = Path(item["path"])
    assert path.is_file() and not path.is_symlink()
    assert path.stat().st_size == item["size"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]

tree = ast.parse(driver)
values = {}
for node in tree.body:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        continue
    target = node.targets[0]
    if isinstance(target, ast.Name):
        try:
            values[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            pass
assert values["INSTRUCTION_LIMIT"] == 4096
assert values["FUNCTION_DISPATCH_LIMIT"] == 64
assert values["EXPECTED_POST_RESERVE_INSTRUCTIONS"] == 19
assert values["EXPECTED_THIRD_CUMULATIVE_INSTRUCTIONS"] == 283
assert values["EXPECTED_THIRD_CALL"] == 0x84BED808
assert values["EXPECTED_THIRD_RETURN"] == 0x84BED80C
assert values["EXPECTED_COMMIT_SIZE"] == 0x10000

for marker in (
    "283 translated guest instructions",
    "0x84BED808",
    "0x84BED80C",
    "0x60001000",
    "one committed page",
    "15 reserved pages",
    "0x8179632E8A902325",
    "4096-instruction",
    "64-dispatch",
    "five-second",
    "does not prove native boot or the main menu",
    "// PORTME at 0x84BED80C",
):
    assert marker in doc
PY

# Retail evidence must still be byte-exact after every compile/execution step.
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

printf '%s\n' \
    'APF_GUARDED_THIRD_BOUNDARY_EXECUTION_VALIDATION_PASS instructions=283 dispatches=3 commit_pages=1 reserved_pages=15 stop=0x84BED80C native_boot=no originals_unchanged=yes'
