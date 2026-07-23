#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
REPORT='reports/static_recomp/apf2k8_guarded_second_boundary_execution.json'
DOC='docs/research/apf_guarded_second_boundary_execution.md'
DRIVER='tools/apf_guarded_second_boundary_execute.py'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'

for path in "$XEX" "$VOLUME" "$REPORT" "$DOC" "$DRIVER" \
    tools/apf_guarded_first_entry_execute.py \
    tools/apf_second_boundary_static.py \
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

mkdir -p /media/noah/Storage/.codex-tmp
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-second-boundary-validation-XXXXXX)
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

# Regress every completed gate in the direct authorization chain.  These are
# independent validators, not trust in their stored JSON alone.
tools/validate_apf_static_recomp_opcode_switch_composed.sh \
    > "$TMP/composed.txt"
grep -Fq 'APF_STATIC_RECOMP_OPCODE_SWITCH_COMPOSED_VALIDATION_PASS' \
    "$TMP/composed.txt"
tools/validate_apf_guest_instruction_budget.sh > "$TMP/budget.txt"
grep -Fq 'APF_GUEST_INSTRUCTION_BUDGET_VALIDATION_PASS' "$TMP/budget.txt"
tools/validate_apf_boot_leaf_adapters.sh > "$TMP/leaf.txt"
grep -Fq 'APF_BOOT_LEAF_ADAPTERS_VALIDATION_PASS' "$TMP/leaf.txt"
tools/validate_apf_imported_data_frontier.sh > "$TMP/imported-data.txt"
grep -Fq 'APF_IMPORTED_DATA_FRONTIER_VALIDATION_PASS' \
    "$TMP/imported-data.txt"
tools/validate_apf_first_entry_readiness.sh > "$TMP/readiness.txt"
grep -Fq 'APF_FIRST_ENTRY_READINESS_VALIDATION_PASS' "$TMP/readiness.txt"
tools/validate_apf_guarded_first_entry_execution.sh \
    > "$TMP/first-boundary.txt"
grep -Fq 'APF_GUARDED_FIRST_ENTRY_EXECUTION_VALIDATION_PASS' \
    "$TMP/first-boundary.txt"
tools/validate_apf_second_boundary_static.sh > "$TMP/second-static.txt"
grep -Fq 'APF_SECOND_BOUNDARY_STATIC_VALIDATION_PASS' \
    "$TMP/second-static.txt"

python3 "$DRIVER" \
    --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report.json" \
    --transcript "$TMP/transcript.txt" \
    --temp-root "$TMP" \
    --jobs "${APF_GUARDED_SECOND_BOUNDARY_JOBS:-12}" \
    > "$TMP/driver.txt"
cmp -s "$TMP/report.json" "$REPORT"
grep -Fq 'outcome=expected_second_boundary signal=0 entry_authorized=1 entry_called=1' \
    "$TMP/transcript.txt"
grep -Fq 'instructions=264 function_dispatches=2 last_pc=0x84BED7B8 lr=0x84BED7BC r3=0x00000000' \
    "$TMP/transcript.txt"
grep -Fq 'base_before=0x00000000 size_before=0x00100000 base_after=0x40000000 size_after=0x00100000' \
    "$TMP/transcript.txt"
grep -Fq 'vm_pages=4096 vm_allocations=1 reserved_pages=16 ledger_exact=1 backing_unchanged=1' \
    "$TMP/transcript.txt"
grep -Fq 'containment_normal=1 containment_signal=1 containment_timeout=1' \
    "$TMP/transcript.txt"
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

assert report["schema"] == "apf2k8_guarded_second_boundary_execution/v1"
result = report["result"]
assert result == {
    "child_outcome": "expected_second_boundary",
    "continued_past_first_typed_boundary": True,
    "continued_past_second_typed_boundary": False,
    "entry_call_authorized_in_isolated_child": True,
    "entry_called_in_isolated_child": True,
    "expected_second_typed_boundary_reached": True,
    "first_typed_boundary_returned_under_exact_mode": True,
    "main_menu_proved": False,
    "native_boot_proved": False,
    "second_typed_adapter_completed": True,
    "signal_number": 0,
    "static_second_boundary_proof_revalidated": True,
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
assert gates["first_return_mode_token_required"] is True
assert gates["first_return_dynamic_pc_lr_abi_gate"] is True
assert gates["second_adapter_dynamic_pc_lr_abi_gate"] is True

execution = report["generated_execution"]
assert execution["entry"] == "0x84BE9D08"
assert execution["executed_guest_instruction_count"] == 264
assert execution["function_dispatch_count"] == 2
assert execution["last_executed_guest_pc"] == "0x84BED7B8"
assert execution["full_ordered_pc_sha256"] == (
    "b521057b939a97aee026b06f7fc667c1f6e463e160b32150b296e98cbe309cd0")
assert execution["first_boundary_ordered_pc_sha256"] == (
    "7ce502bf4aa0897bfe95a390ccf6d7e01b305dcb936ae20f178fff4bae7601ce")
assert execution["continuation_ordered_pc_sha256"] == (
    "764c6c72387763e12d8338d9d437b2b815e64f29f88c10cedd761aa334bf31ec")
pcs = execution["ordered_guest_pcs"]
assert len(pcs) == 264
assert pcs[37] == "0x84BF1888"
assert pcs[38] == "0x84BF188C"
assert pcs[-1] == "0x84BED7B8"
first = execution["first_boundary"]
assert first["returned_to_generated_code"] is True
assert (first["call_pc"], first["return_pc"], first["thunk"]) == (
    "0x84BF1888", "0x84BF188C", "0x84D0859C")
assert (first["r3_header"], first["r4_key"], first["r3_result"]) == (
    "0x70020100", "0x00020401", "0x00000000")
second = execution["second_boundary"]
assert (second["call_pc"], second["return_pc"], second["thunk"]) == (
    "0x84BED7B8", "0x84BED7BC", "0x84D0863C")
assert second["adapter_status"] == "ok"
assert second["ntstatus_r3"] == "0x00000000"
assert second["base_value_after_be_u32"] == "0x40000000"
assert second["size_value_after_be_u32"] == "0x00100000"
assert second["generated_return_instruction_executed"] is False
assert second["arguments"] == {
    "base_value_before_be_u32": "0x00000000",
    "r3_base_pointer": "0x7001FC50",
    "r4_size_pointer": "0x7001FD34",
    "r5_allocation_type": "0x60002000",
    "r6_protection": "0x00000004",
    "r7_debug_memory": "0x00000000",
    "size_value_before_be_u32": "0x00100000",
}

ledger = report["virtual_memory_ledger"]
assert ledger == {
    "active_allocation_count": 1,
    "allocation_base_page": 0,
    "allocation_page_count": 16,
    "allocation_protection": "0x00000004",
    "allocation_slot": 0,
    "allocation_state": "reserve",
    "arena_base": "0x40000000",
    "arena_size": "0x10000000",
    "backing_fnv1a64_after": "0x1F5E0DF9BC822325",
    "backing_fnv1a64_before": "0x1F5E0DF9BC822325",
    "backing_pattern_byte_exact_unchanged": True,
    "page_count": 4096,
    "page_size": "0x00010000",
    "remaining_allocation_slots_inactive": True,
    "remaining_pages_free": True,
}
assert set(report["outcome_classification"]["implemented"]) == {
    "expected_second_boundary", "budget_exhaustion", "import_abort",
    "signal", "timeout", "unexpected_return", "prerequisite_failure",
    "unexpected_exception",
}
assert report["outcome_classification"]["observed"] == (
    "expected_second_boundary")
assert report["isolation"]["normal_host_shell_linked"] is False
assert report["isolation"]["normal_host_shell_modified"] is False
assert report["isolation"]["retail_inputs_modified"] is False
assert report["isolation"]["temporary_generated_objects_deleted"] is True
assert len(report["portme"]) == 4
assert all(line.startswith("// PORTME") for line in report["portme"])

for item in report["inputs"]["local_files"]:
    path = Path(item["path"])
    data = path.read_bytes()
    assert len(data) == item["size"], path
    assert hashlib.sha256(data).hexdigest() == item["sha256"], path

# The generated harness must implement every terminal class and an
# unconditional post-adapter throw, without creating a permanent runtime TU.
tree = ast.parse(driver)
assert "expected_second_boundary" in driver
assert "instruction_budget_exhausted" in driver
assert "import_abort" in driver
assert "outcome=signal" in driver
assert "outcome=timeout" in driver
assert "Throw unconditionally: 0x84BED7BC must not execute" in driver
assert "temporary exact-source-derived bridge" in driver
assert doc.count("APF_GUARDED_SECOND_BOUNDARY_EXECUTION_VALIDATION_PASS") == 1
assert "executed 264 translated guest instructions" in " ".join(doc.split())
assert "not a title boot" in doc
assert doc.count("// PORTME") >= 4
PY

# Every changed prerequisite must refuse before compilation/output creation.
cp reports/static_recomp/apf2k8_guarded_first_entry_execution.json \
    "$TMP/forged-first.json"
python3 - "$TMP/forged-first.json" <<'PY'
import json
from pathlib import Path
import sys
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["generated_execution"]["executed_guest_instruction_count"] = 39
path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
PY
if python3 "$DRIVER" --decoded "$TMP/apf-decoded.pe" \
    --first-report "$TMP/forged-first.json" \
    --json "$TMP/forged-first-output.json" \
    --transcript "$TMP/forged-first-transcript.txt" \
    --temp-root "$TMP" > "$TMP/forged-first-out.txt" \
    2> "$TMP/forged-first-err.txt"; then
    echo 'second-boundary driver accepted a forged first report' >&2
    exit 1
fi
grep -Fq 'v2 first-boundary execution report hash changed' \
    "$TMP/forged-first-err.txt"
test ! -e "$TMP/forged-first-output.json"
test ! -e "$TMP/forged-first-transcript.txt"

cp reports/static_recomp/apf2k8_second_boundary_static.json \
    "$TMP/forged-static.json"
python3 - "$TMP/forged-static.json" <<'PY'
import json
from pathlib import Path
import sys
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["next_boundary"]["call_pc"] = "0x84BED7BC"
path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
PY
if python3 "$DRIVER" --decoded "$TMP/apf-decoded.pe" \
    --second-static "$TMP/forged-static.json" \
    --json "$TMP/forged-static-output.json" \
    --transcript "$TMP/forged-static-transcript.txt" \
    --temp-root "$TMP" > "$TMP/forged-static-out.txt" \
    2> "$TMP/forged-static-err.txt"; then
    echo 'second-boundary driver accepted a forged static report' >&2
    exit 1
fi
grep -Fq 'second-boundary static report hash changed' \
    "$TMP/forged-static-err.txt"
test ! -e "$TMP/forged-static-output.json"
test ! -e "$TMP/forged-static-transcript.txt"

cp reports/static_recomp/apf2k8_boot_leaf_adapters.json \
    "$TMP/forged-leaf.json"
printf '\n' >> "$TMP/forged-leaf.json"
if python3 "$DRIVER" --decoded "$TMP/apf-decoded.pe" \
    --leaf-report "$TMP/forged-leaf.json" \
    --json "$TMP/forged-leaf-output.json" \
    --transcript "$TMP/forged-leaf-transcript.txt" \
    --temp-root "$TMP" > "$TMP/forged-leaf-out.txt" \
    2> "$TMP/forged-leaf-err.txt"; then
    echo 'second-boundary driver accepted a forged leaf report' >&2
    exit 1
fi
grep -Fq 'typed leaf-adapter report hash changed' "$TMP/forged-leaf-err.txt"
test ! -e "$TMP/forged-leaf-output.json"
test ! -e "$TMP/forged-leaf-transcript.txt"

cp --reflink=auto "$TMP/apf-decoded.pe" "$TMP/forged-decoded.pe"
printf '\x01' | dd of="$TMP/forged-decoded.pe" bs=1 seek=3 \
    conv=notrunc status=none
if python3 "$DRIVER" --decoded "$TMP/forged-decoded.pe" \
    --json "$TMP/forged-image-output.json" \
    --transcript "$TMP/forged-image-transcript.txt" \
    --temp-root "$TMP" > "$TMP/forged-image-out.txt" \
    2> "$TMP/forged-image-err.txt"; then
    echo 'second-boundary driver accepted a forged decoded image' >&2
    exit 1
fi
grep -Fq 'decoded APF image is not exact' "$TMP/forged-image-err.txt"
test ! -e "$TMP/forged-image-output.json"
test ! -e "$TMP/forged-image-transcript.txt"

# There is still no title-entry call or second-boundary bridge in the normal
# host sources/build graph.
if rg -n '__imp___xstart[[:space:]]*\(|(^|[^A-Za-z0-9_])_xstart[[:space:]]*\(' \
    CMakeLists.txt src include; then
    echo 'guarded APF entry leaked into the normal host build' >&2
    exit 1
fi
if rg -n 'second_boundary_mode_arm|second_boundary_full_trace_copy' \
    CMakeLists.txt src include; then
    echo 'temporary second-boundary bridge leaked into normal sources' >&2
    exit 1
fi

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

echo 'APF_GUARDED_SECOND_BOUNDARY_EXECUTION_VALIDATION_PASS instructions=264 function_dispatches=2 first_call=0x84BF1888 second_call=0x84BED7B8 return=0x84BED7BC base=0x40000000 size=0x00100000 reserved_pages=16 continued=0 native_boot=0 originals_unchanged=yes'
