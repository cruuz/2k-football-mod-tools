#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
SOURCE='build-static-recomp-apf/ppc-opcode-switch-composed'
BASELINE='build-static-recomp-apf/ppc-filtered'
OUTPUT='build-static-recomp-apf/ppc-opcode-switch-budget-instrumented'
SOURCE_REPORT='reports/static_recomp/apf2k8_static_recomp_opcode_switch_composed.json'
REPORT='reports/static_recomp/apf2k8_guest_instruction_budget_instrumentation.json'
DOC='docs/research/apf_guest_instruction_budget.md'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_SOURCE_REPORT='4e15f16f06263dc48279f5e59d9019345d915dc74e2ac8306d9795f5f37518b1'

for path in "$XEX" "$VOLUME" "$SOURCE_REPORT" "$REPORT" "$DOC" \
    include/static_runtime/apf_guest_instruction_budget.h \
    src/static_runtime/apf_guest_instruction_budget.cpp \
    tests/apf_guest_instruction_budget_test.cpp \
    tests/apf_instruction_budget_instrumenter_test.py \
    tools/apf_instrument_guest_instruction_budget.py \
    tools/apf_instruction_budget_link_probe.py; do
    test -f "$path"
done
test -d "$SOURCE"
test -d "$BASELINE"
test -d "$OUTPUT"
test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
test "$(sha256sum "$SOURCE_REPORT" | awk '{print $1}')" = \
    "$EXPECTED_SOURCE_REPORT"

mkdir -p .codex-tmp
TMP=$(mktemp -d .codex-tmp/apf-guest-instruction-budget-XXXXXX)
cleanup() {
    rm -rf "$TMP"
}
trap cleanup EXIT

python3 -m py_compile \
    tools/apf_instrument_guest_instruction_budget.py \
    tools/apf_instruction_budget_link_probe.py \
    tests/apf_instruction_budget_instrumenter_test.py
python3 tests/apf_instruction_budget_instrumenter_test.py \
    > "$TMP/instrumenter-test.txt"
grep -Fq 'APF_INSTRUCTION_BUDGET_INSTRUMENTER_TEST_PASS' \
    "$TMP/instrumenter-test.txt"

STRICT_C=(
    -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
    -Iinclude
)
STRICT_CXX=(
    -std=c++20 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
    -Iinclude
)
C_SOURCES=(
    src/static_runtime/apf_first_entry_gate.c
    src/static_runtime/apf_imported_data_bootstrap.c
    src/static_runtime/apf_boot_leaf_adapters.c
)

for index in "${!C_SOURCES[@]}"; do
    cc "${STRICT_C[@]}" -O0 -c "${C_SOURCES[$index]}" \
        -o "$TMP/runtime-c-$index.o"
done
clang++-18 "${STRICT_CXX[@]}" -O0 \
    tests/apf_guest_instruction_budget_test.cpp \
    src/static_runtime/apf_guest_instruction_budget.cpp \
    "$TMP"/runtime-c-*.o -o "$TMP/runtime-test"
"$TMP/runtime-test" > "$TMP/runtime-test.txt"
grep -Fq 'APF_GUEST_INSTRUCTION_BUDGET_RUNTIME_PASS unbound_stop=1 exact_limit=1 pre_effect_stop=1 pre_transfer_stop=1 loop_dynamic=4 invalid_address=1' \
    "$TMP/runtime-test.txt"

SANITIZERS=(
    -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined
)
for index in "${!C_SOURCES[@]}"; do
    clang-18 "${STRICT_C[@]}" "${SANITIZERS[@]}" \
        -c "${C_SOURCES[$index]}" -o "$TMP/sanitized-c-$index.o"
done
clang++-18 "${STRICT_CXX[@]}" "${SANITIZERS[@]}" \
    tests/apf_guest_instruction_budget_test.cpp \
    src/static_runtime/apf_guest_instruction_budget.cpp \
    "$TMP"/sanitized-c-*.o -o "$TMP/runtime-test-sanitized"
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
    "$TMP/runtime-test-sanitized" > "$TMP/runtime-test-sanitized.txt"
grep -Fq 'APF_GUEST_INSTRUCTION_BUDGET_RUNTIME_PASS' \
    "$TMP/runtime-test-sanitized.txt"

python3 tools/apf_instrument_guest_instruction_budget.py \
    --input "$SOURCE" \
    --baseline "$BASELINE" \
    --source-manifest "$SOURCE_REPORT" \
    --output "$TMP/instrumented" \
    --json "$TMP/instrumentation.json" \
    > "$TMP/instrumentation.txt"
grep -Fq 'APF_GUEST_INSTRUCTION_INSTRUMENTATION_PASS functions=60397 occurrences=1808124 unique_addresses=1793755 hooks=1808124 labels=102729 uninstrumentable=0 entry_authorized=0 entry_called=0' \
    "$TMP/instrumentation.txt"

python3 - "$REPORT" "$TMP/instrumentation.json" "$OUTPUT" \
    "$TMP/instrumented" "$SOURCE_REPORT" "$DOC" <<'PY'
import copy
import hashlib
import json
import pathlib
import sys

canonical_path, regenerated_path, canonical_tree, regenerated_tree, \
    source_report_path, doc_path = map(pathlib.Path, sys.argv[1:])
canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
regenerated = json.loads(regenerated_path.read_text(encoding="utf-8"))
source_report = json.loads(source_report_path.read_text(encoding="utf-8"))
doc = doc_path.read_text(encoding="utf-8")

assert canonical["schema"] == \
    "apf2k8_guest_instruction_budget_instrumentation/v1"
result = canonical["result"]
assert result["source_corpus_read_only"] is True
assert result["source_provenance_stream_exact"] is True
assert result["translated_function_count"] == 60397
assert result["guest_instruction_occurrence_count"] == 1808124
assert result["unique_guest_instruction_address_count"] == 1793755
assert result["overlapping_translation_occurrence_count"] == 14369
assert result["instrumented_hook_count"] == 1808124
assert result["control_flow_label_count"] == 102729
assert result["audited_goto_count"] == 149956
assert result["every_marker_has_exactly_one_immediate_pre_body_hook"] is True
assert result["deinstrumentation_recovers_exact_source"] is True
assert result["uninstrumentable_construct_count"] == 0
assert result["runtime_hook_source_wired_at_every_marker"] is True
assert result["instruction_budget_blocker_resolved_for_derived_corpus"] is True
assert result["entry_call_authorized"] is False
assert result["entry_called"] is False
assert result["translated_title_code_executed_by_pipeline"] is False
assert result["native_boot_proved"] is False

coverage = canonical["coverage_proof"]
assert coverage["marker_manifest_sha256"] == \
    coverage["hook_manifest_sha256"] == \
    "e6feaf772baf701a84164a7cae4904b40f539888d2a8f37960445431f8545a4c"
assert coverage["minimum_instrumented_address"] == "0x84630000"
assert coverage["maximum_instrumented_address"] == "0x84D07B68"
manifest = canonical["inputs"]["source_manifest"]
assert manifest["corpus_binding_verified"] is True
assert manifest["declared_tree_sha256"] == \
    "33bd100b5a7b358dd651b4c55ace6b41c73f9d3552a6684cede299ae9ac9532f"
assert manifest["declared_cpp_manifest_sha256"] == \
    "216e11b389a0da0c808bf7a7f598cf9210e481f90477a73eacb15ea37d120079"
assert canonical["inputs"]["changed_support_files_bound_by_manifest"] == [
    "ppc_context.h"]
assert canonical["ordered_blockers_for_this_lane"] == []
assert canonical["scope_boundary"]["title_entry_api_added"] is False
assert source_report["result"]["single_composed_derived_corpus_exists"] is True
assert source_report["result"]["title_entry_called"] is False

left = copy.deepcopy(canonical)
right = copy.deepcopy(regenerated)
left["output"]["instrumented_corpus"] = "<normalized>"
right["output"]["instrumented_corpus"] = "<normalized>"
assert left == right

left_files = sorted(path for path in canonical_tree.iterdir() if path.is_file())
right_files = sorted(path for path in regenerated_tree.iterdir() if path.is_file())
assert [path.name for path in left_files] == [path.name for path in right_files]
for left_path, right_path in zip(left_files, right_files, strict=True):
    assert left_path.read_bytes() == right_path.read_bytes(), left_path.name

assert doc.count("APF_GUEST_INSTRUCTION_BUDGET_VALIDATION_PASS") == 1
assert "does **not**\ncall `_xstart`" in doc
assert "1,808,124" in doc and "1,793,755" in doc
assert "does not authorize title entry" in doc
PY

if python3 tools/apf_instrument_guest_instruction_budget.py \
    --input "$SOURCE" --baseline "$BASELINE" \
    --source-manifest "$SOURCE_REPORT" \
    --output "$TMP/instrumented" --json "$TMP/duplicate.json" \
    > "$TMP/duplicate-out.txt" 2> "$TMP/duplicate-err.txt"; then
    echo 'instrumenter overwrote an existing output' >&2
    exit 1
fi
grep -Fq 'output already exists' "$TMP/duplicate-err.txt"

cp -al "$SOURCE" "$TMP/tampered-source"
cp --reflink=auto "$SOURCE/ppc_recomp.0.cpp" "$TMP/tampered-0.cpp"
python3 - "$TMP/tampered-0.cpp" <<'PY'
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "\t// fabs f1,f1\n"
assert text.count(old) == 1
path.write_text(text.replace(old, "\t// fabs f1,f2\n", 1), encoding="utf-8")
PY
mv "$TMP/tampered-0.cpp" "$TMP/tampered-source/ppc_recomp.0.cpp"
if python3 tools/apf_instrument_guest_instruction_budget.py \
    --input "$TMP/tampered-source" --baseline "$BASELINE" \
    --source-manifest "$SOURCE_REPORT" \
    --output "$TMP/tampered-output" --json "$TMP/tampered.json" \
    > "$TMP/tampered-out.txt" 2> "$TMP/tampered-err.txt"; then
    echo 'instrumenter accepted a source-manifest mismatch' >&2
    exit 1
fi
grep -Fq 'composed-corpus manifest does not bind this safe input' \
    "$TMP/tampered-err.txt"

python3 tools/apf_instruction_budget_link_probe.py \
    --generated "$TMP/instrumented" \
    --instrumentation-report "$TMP/instrumentation.json" \
    --temp-root "$TMP" \
    --transcript "$TMP/link-transcript.txt" \
    --jobs "${APF_BUDGET_JOBS:-16}" \
    > "$TMP/link-build.txt"
grep -Fq 'APF_INSTRUCTION_BUDGET_LINK_PASS mappings=60731 generated_cpp=237 hooks=1808124 entry_mapping=1 entry_called=0' \
    "$TMP/link-transcript.txt"
grep -Fq 'APF_INSTRUCTION_BUDGET_LINK_BUILD_PASS objects=243' \
    "$TMP/link-build.txt"
grep -Fq 'imports_failfast=334 temporary_outputs_deleted=1' \
    "$TMP/link-build.txt"

if rg -n '__imp___xstart[[:space:]]*\(|(^|[^A-Za-z0-9_])_xstart[[:space:]]*\(' \
    include/static_runtime/apf_guest_instruction_budget.h \
    src/static_runtime/apf_guest_instruction_budget.cpp \
    tests/apf_guest_instruction_budget_test.cpp \
    tools/apf_instrument_guest_instruction_budget.py \
    tools/apf_instruction_budget_link_probe.py; then
    echo 'translated title-entry call leaked into budget sources' >&2
    exit 1
fi

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

echo 'APF_GUEST_INSTRUCTION_BUDGET_VALIDATION_PASS functions=60397 occurrences=1808124 unique_addresses=1793755 hooks=1808124 labels=102729 mappings=60731 imports_failfast=334 entry_authorized=0 entry_called=0'
