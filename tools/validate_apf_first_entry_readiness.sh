#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
REPORT='reports/static_recomp/apf2k8_first_entry_readiness.json'
DOC='docs/research/apf_first_entry_readiness.md'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'

for path in "$XEX" "$VOLUME" "$REPORT" "$DOC" \
    include/static_runtime/apf_first_entry_gate.h \
    include/static_runtime/apf_first_entry_xenon_bridge.h \
    src/static_runtime/apf_first_entry_gate.c \
    src/static_runtime/apf_first_entry_xenon_bridge.cpp \
    tools/apf_first_entry_gate_probe.c \
    tools/apf_first_entry_link_probe.py \
    tools/apf_first_entry_readiness.py \
    tests/apf_first_entry_gate_test.c; do
    test -f "$path"
done

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

mkdir -p .codex-tmp
TMP=$(mktemp -d .codex-tmp/apf-first-entry-validation-XXXXXX)
cleanup() {
    rm -rf "$TMP"
}
trap cleanup EXIT

clang++-18 -std=c++20 -O2 tools/xex_extract_pe.cpp \
    -Itools/vendor/XenonRecomp/XenonUtils \
    -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
    -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
    tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
    -o "$TMP/xex_extract_pe"
"$TMP/xex_extract_pe" "$XEX" "$TMP/apf-decoded.pe" \
    > "$TMP/extract-transcript.txt"
test "$(stat -c %s "$TMP/apf-decoded.pe")" = 54001664
test "$(sha256sum "$TMP/apf-decoded.pe" | awk '{print $1}')" = \
    "$EXPECTED_DECODED"

COMMON_C=(
    src/static_runtime/apf_first_entry_gate.c
    src/static_runtime/apf_imported_data_bootstrap.c
    src/static_runtime/apf_boot_leaf_adapters.c
)
STRICT_C=(
    -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
    -Iinclude
)

cc "${STRICT_C[@]}" tests/apf_first_entry_gate_test.c \
    "${COMMON_C[@]}" -o "$TMP/gate-test"
"$TMP/gate-test" > "$TMP/gate-test.txt"
grep -Fq 'APF_FIRST_ENTRY_GATE_PASS bindings=30 resumable=24 terminal=4 exception=1 thread_create=1 blockers=3 entry_authorized=0 entry_called=0 containment=3' \
    "$TMP/gate-test.txt"

cc "${STRICT_C[@]}" -O1 -g -fno-omit-frame-pointer \
    -fsanitize=address,undefined \
    tests/apf_first_entry_gate_test.c "${COMMON_C[@]}" \
    -o "$TMP/gate-test-sanitized"
ASAN_OPTIONS=detect_leaks=1:abort_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
    "$TMP/gate-test-sanitized" > "$TMP/gate-test-sanitized.txt"
grep -Fq 'APF_FIRST_ENTRY_GATE_PASS' "$TMP/gate-test-sanitized.txt"

for source in "${COMMON_C[@]}" tests/apf_first_entry_gate_test.c; do
    gcc -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
        -fanalyzer -Iinclude -c "$source" \
        -o "$TMP/$(basename "$source").analyzer.o"
done

cc "${STRICT_C[@]}" tools/apf_first_entry_gate_probe.c \
    "${COMMON_C[@]}" -o "$TMP/image-probe"
"$TMP/image-probe" "$TMP/apf-decoded.pe" "$XEX" \
    > "$TMP/image-probe.txt"
grep -Fq 'APF_FIRST_ENTRY_PROBE_PASS mapped_bytes=4294967296' \
    "$TMP/image-probe.txt"
grep -Fq 'first_call=0x84BF1888 first_return=0x84BF188C first_thunk=0x84D0859C adapter_status=ok blockers=3 entry_authorized=0 entry_called=0' \
    "$TMP/image-probe.txt"

clang++-18 -std=c++20 -Wall -Wextra -Wpedantic -Wconversion -Werror \
    -Wno-shadow -Wno-shorten-64-to-32 \
    -Iinclude -Ibuild-static-recomp-apf/ppc-filtered \
    -Itools/vendor/XenonRecomp/XenonUtils \
    -Itools/vendor/XenonRecomp/thirdparty/simde \
    -c src/static_runtime/apf_first_entry_xenon_bridge.cpp \
    -o "$TMP/xenon-bridge.o"

python3 tools/apf_first_entry_link_probe.py \
    --decoded "$TMP/apf-decoded.pe" \
    --temp-root "$TMP" \
    --transcript "$TMP/link-probe.txt" \
    --jobs "${APF_FIRST_ENTRY_JOBS:-16}" \
    > "$TMP/link-build.txt"
grep -Fq 'APF_FIRST_ENTRY_LINK_PASS mappings=60731 typed_bindings=30 first_thunk=0x84D0859C bridge_stop=1 blockers=2 entry_authorized=0 entry_called=0' \
    "$TMP/link-probe.txt"
grep -Fq 'generated_cpp=237 typed_imports=30 nonfrontier_failfast=304' \
    "$TMP/link-build.txt"
grep -Fq 'temporary_outputs_deleted=1' "$TMP/link-build.txt"

python3 tools/apf_first_entry_readiness.py \
    --probe-transcript "$TMP/image-probe.txt" \
    --link-transcript "$TMP/link-probe.txt" \
    --json "$TMP/readiness.json" \
    > "$TMP/readiness-transcript.txt"
cmp -s "$TMP/readiness.json" "$REPORT"

python3 - "$REPORT" "$DOC" <<'PY'
import json
import pathlib
import sys

report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
doc = pathlib.Path(sys.argv[2]).read_text(encoding="utf-8")
assert report["schema"] == "apf2k8_first_entry_readiness/v1"
result = report["result"]
assert result["exact_first_typed_boundary_proved"] is True
assert result["first_typed_boundary_adapter_probed"] is True
assert result["guest_address_space_exactly_mapped"] is True
assert result["raw_xex_header_separately_installed"] is True
assert result["frontier_imported_data_slots_installed"] == 2
assert result["frontier_import_thunks_bound"] == 30
assert result["generated_dispatch_mapping_count_installed"] == 60731
assert result["augmented_frontier_generated_nodes"] == 426
assert result["augmented_frontier_opcode_gap_sites"] == 0
assert result["augmented_frontier_unresolved_switch_occurrences"] == 0
assert result["preboundary_unresolved_indirect_sites"] == 0
assert result["ordered_blocker_count"] == 2
assert result["entry_call_authorized"] is False
assert result["entry_called"] is False
assert result["translated_title_code_executed"] is False
assert result["first_boundary_reached_by_generated_execution"] is False
assert result["native_boot_proved"] is False
assert [item["code"] for item in report["ordered_blockers"]] == [
    "COMPOSED_DERIVED_CORPUS",
    "INSTRUCTION_BUDGET_INSTRUMENTATION",
]
assert report["execution_order"]["maximum_nested_frame_bytes_before_boundary"] == 752
assert report["semantic_intersections"]["opcode_gap_site_count_global"] == 172
assert report["semantic_intersections"]["switch_tail_residue_occurrences_global"] == 1076
assert report["isolated_harness"]["normal_host_shell_linked"] is False
assert report["isolated_harness"]["entry_call_api_present"] is False
assert report["isolated_harness"]["generated_instruction_budget_instrumented"] is False
assert doc.count("APF_FIRST_ENTRY_READINESS_VALIDATION_PASS") == 1
assert "entry_call_authorized = false" in doc
assert "does **not**\ncall `_xstart`" in doc
assert doc.count("// PORTME:") >= 2
PY

if rg -n '__imp___xstart[[:space:]]*\(|(^|[^A-Za-z0-9_])_xstart[[:space:]]*\(' \
    src/static_runtime/apf_first_entry_gate.c \
    src/static_runtime/apf_first_entry_xenon_bridge.cpp \
    tools/apf_first_entry_gate_probe.c; then
    echo 'title entry call leaked into isolated first-entry sources' >&2
    exit 1
fi

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"

echo 'APF_FIRST_ENTRY_READINESS_VALIDATION_PASS mappings=60731 bindings=30 opcode_frontier=0 switch_frontier=0 blockers=2 entry_authorized=0 entry_called=0'
