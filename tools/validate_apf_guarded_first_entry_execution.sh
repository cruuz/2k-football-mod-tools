#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
REPORT='reports/static_recomp/apf2k8_guarded_first_entry_execution.json'
DOC='docs/research/apf_guarded_first_entry_execution.md'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'

for path in "$XEX" "$VOLUME" "$REPORT" "$DOC" \
    reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json \
    reports/static_recomp/apf2k8_guest_instruction_budget_instrumentation.json \
    reports/static_recomp/apf2k8_first_entry_readiness.json \
    include/static_runtime/apf_guest_instruction_budget.h \
    src/static_runtime/apf_guest_instruction_budget.cpp \
    tests/apf_guest_instruction_budget_test.cpp \
    tools/apf_guarded_first_entry_execute.py; do
    test -f "$path"
done
test -d build-static-recomp-apf/ppc-opcode-switch-composed
test -d build-static-recomp-apf/ppc-opcode-switch-budget-instrumented
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

mkdir -p /media/noah/Storage/.codex-tmp
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-guarded-entry-validation-XXXXXX)
cleanup() {
    rm -rf "$TMP"
}
trap cleanup EXIT

python3 -m py_compile tools/apf_guarded_first_entry_execute.py

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

STRICT_C=(-std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror -Iinclude)
STRICT_CXX=(-std=c++20 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror -Iinclude)
C_SOURCES=(
    src/static_runtime/apf_first_entry_gate.c
    src/static_runtime/apf_imported_data_bootstrap.c
    src/static_runtime/apf_boot_leaf_adapters.c
)
for index in "${!C_SOURCES[@]}"; do
    clang-18 "${STRICT_C[@]}" -O0 -c "${C_SOURCES[$index]}" \
        -o "$TMP/runtime-c-$index.o"
done
clang++-18 "${STRICT_CXX[@]}" -O0 \
    tests/apf_guest_instruction_budget_test.cpp \
    src/static_runtime/apf_guest_instruction_budget.cpp \
    "$TMP"/runtime-c-*.o -o "$TMP/budget-test"
"$TMP/budget-test" > "$TMP/budget-test.txt"
grep -Fq 'APF_GUEST_INSTRUCTION_BUDGET_RUNTIME_PASS' "$TMP/budget-test.txt"

# Preserve the v1 milestone as an independently passing historical gate. Its
# pinned local-file set does not include the additive budget trace observer.
tools/validate_apf_first_entry_readiness.sh > "$TMP/v1-readiness.txt"
grep -Fq 'APF_FIRST_ENTRY_READINESS_VALIDATION_PASS mappings=60731 bindings=30 opcode_frontier=0 switch_frontier=0 blockers=2 entry_authorized=0 entry_called=0' \
    "$TMP/v1-readiness.txt"

python3 tools/apf_guarded_first_entry_execute.py \
    --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report.json" \
    --transcript "$TMP/transcript.txt" \
    --temp-root "$TMP" \
    --jobs "${APF_GUARDED_ENTRY_JOBS:-12}" \
    > "$TMP/driver.txt"
cmp -s "$TMP/report.json" "$REPORT"
grep -Fq 'outcome=expected_typed_boundary signal=0 entry_authorized=1 entry_called=1' \
    "$TMP/transcript.txt"
grep -Fq 'instructions=38 function_dispatches=1 last_pc=0x84BF1888 lr=0x84BF188C r3=0x00000000' \
    "$TMP/transcript.txt"
grep -Fq 'containment_normal=1 containment_signal=1 containment_timeout=1' \
    "$TMP/transcript.txt"
grep -Fq 'temporary_outputs_deleted=1' "$TMP/driver.txt"

python3 - "$REPORT" "$DOC" <<'PY'
import hashlib
import json
import pathlib
import sys

report_path, doc_path = map(pathlib.Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
doc = doc_path.read_text(encoding="utf-8")
assert report["schema"] == "apf2k8_guarded_first_entry_execution/v2"
result = report["result"]
assert result["former_composed_corpus_blocker_revalidated"] is True
assert result["former_instruction_budget_blocker_revalidated"] is True
assert result["entry_call_authorized_in_isolated_child"] is True
assert result["entry_called_in_isolated_child"] is True
assert result["translated_title_code_executed"] is True
assert result["expected_first_typed_boundary_reached"] is True
assert result["continued_past_first_typed_boundary"] is False
assert result["child_outcome"] == "expected_typed_boundary"
assert result["native_boot_proved"] is False
assert result["main_menu_proved"] is False
execution = report["generated_execution"]
assert execution["executed_guest_instruction_count"] == 38
assert execution["function_dispatch_count"] == 1
assert execution["last_executed_guest_pc"] == "0x84BF1888"
assert execution["recent_executed_guest_pcs"][-1] == "0x84BF1888"
assert len(execution["recent_executed_guest_pcs"]) == 16
assert report["authorization_gates"]["all_instruction_hooks_recounted"] == 1808124
assert report["authorization_gates"]["dispatch_mapping_count_revalidated"] == 60731
assert report["authorization_gates"]["typed_bridge_binding_count_revalidated"] == 30
assert report["authorization_gates"][
    "v1_readiness_report_and_pinned_files_exact"] is True
assert report["isolation"]["normal_host_shell_linked"] is False
assert report["isolation"]["temporary_generated_objects_deleted"] is True
assert set(report["outcome_classification"]["implemented"]) == {
    "expected_typed_boundary", "budget_exhaustion", "import_abort",
    "signal", "timeout", "unexpected_return", "prerequisite_failure",
    "unexpected_exception",
}
for item in report["inputs"]["local_files"]:
    path = pathlib.Path(item["path"])
    data = path.read_bytes()
    assert len(data) == item["size"], path
    assert hashlib.sha256(data).hexdigest() == item["sha256"], path
assert doc.count("APF_GUARDED_FIRST_ENTRY_EXECUTION_VALIDATION_PASS") == 1
assert "38 guest instructions" in doc
assert "not a title boot" in doc
assert doc.count("// PORTME:") >= 4
PY

# A changed source report must fail before a translated object is compiled or
# an entry-capable child is created.
cp reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json \
    "$TMP/tampered-composed-report.json"
python3 - "$TMP/tampered-composed-report.json" <<'PY'
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["result"]["unrecognized_instruction_count"] = 1
path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
PY
if python3 tools/apf_guarded_first_entry_execute.py \
    --decoded "$TMP/apf-decoded.pe" \
    --composed-report "$TMP/tampered-composed-report.json" \
    --json "$TMP/should-not-exist.json" \
    --transcript "$TMP/should-not-exist.txt" \
    --temp-root "$TMP" \
    > "$TMP/tamper-out.txt" 2> "$TMP/tamper-err.txt"; then
    echo 'guarded driver accepted a changed composed report' >&2
    exit 1
fi
grep -Fq 'composed-corpus report hash changed' "$TMP/tamper-err.txt"
test ! -e "$TMP/should-not-exist.json"
test ! -e "$TMP/should-not-exist.txt"

if rg -n '__imp___xstart[[:space:]]*\(|(^|[^A-Za-z0-9_])_xstart[[:space:]]*\(' \
    CMakeLists.txt src include; then
    echo 'guarded title entry leaked into the normal host build' >&2
    exit 1
fi
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

echo 'APF_GUARDED_FIRST_ENTRY_EXECUTION_VALIDATION_PASS instructions=38 function_dispatches=1 last_pc=0x84BF1888 lr=0x84BF188C outcome=expected_typed_boundary continued=0 native_boot=0 originals_unchanged=yes'
