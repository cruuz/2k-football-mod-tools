#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

XEX='extracted/All-Pro Football 2K8 (USA)/default.xex'
VOLUME='extracted/All-Pro Football 2K8 (USA)/0A'
PRIOR='reports/static_recomp/apf2k8_guarded_second_boundary_execution.json'
REPORT='reports/static_recomp/apf2k8_post_reserve_static.json'
DOC='docs/research/apf_post_reserve_static.md'
ANALYZER='tools/apf_post_reserve_static.py'
GENERATED='build-static-recomp-apf/ppc-opcode-switch-budget-instrumented/ppc_recomp.217.cpp'
EXPECTED_XEX='981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
EXPECTED_VOLUME='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
EXPECTED_DECODED='cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf'
EXPECTED_PRIOR='d60c0116a5445624453d867c8600c0466b06a0fb64f3bc183c7ebe730c651761'
EXPECTED_GENERATED='ed97b7cf74b5368eeae914b770108681e0447bb7afa75238604b2e684234d5e3'

for path in "$XEX" "$VOLUME" "$PRIOR" "$REPORT" "$DOC" "$ANALYZER" \
    "$GENERATED" \
    reports/static_recomp/apf2k8_second_boundary_static.json \
    reports/static_recomp/apf2k8_boot_leaf_adapters.json \
    reports/static_recomp/apf2k8_opcode_gap_sites.tsv \
    reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv \
    reports/headers/apf2k8_xex_report.json \
    src/static_runtime/apf_boot_leaf_adapters.c \
    src/static_runtime/apf_first_entry_xenon_bridge.cpp \
    tools/apf_guarded_second_boundary_execute.py \
    research/functions/apf2k8/ledger/apf2k8_functions_19456_19967.jsonl; do
    test -f "$path"
    test ! -L "$path"
done

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
test "$(sha256sum "$PRIOR" | awk '{print $1}')" = "$EXPECTED_PRIOR"
test "$(sha256sum "$GENERATED" | awk '{print $1}')" = "$EXPECTED_GENERATED"

mkdir -p /media/noah/Storage/.codex-tmp
TMP=$(mktemp -d /media/noah/Storage/.codex-tmp/apf-post-reserve-static-XXXXXX)
cleanup() {
    rm -rf "$TMP"
}
trap cleanup EXIT

python3 -m py_compile "$ANALYZER"

# The analyzer may only parse pinned evidence. It cannot delegate execution or
# call a translated title function.
python3 - "$ANALYZER" <<'PY'
import ast
from pathlib import Path
import re
import sys

tree = ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
for node in ast.walk(tree):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        names = [item.name for item in node.names]
        assert "subprocess" not in names
        assert "os" not in names
    if not isinstance(node, ast.Call):
        continue
    name = None
    if isinstance(node.func, ast.Name):
        name = node.func.id
    elif isinstance(node.func, ast.Attribute):
        name = node.func.attr
    assert name not in {
        "_xstart", "exec", "eval", "system", "popen", "run", "call",
        "Popen", "check_call", "check_output",
    }
    assert name is None or re.fullmatch(r"sub_[0-9A-Fa-f]+", name) is None
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

python3 "$ANALYZER" \
    --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report-one.json" > "$TMP/analyzer-one.txt"
python3 "$ANALYZER" \
    --decoded "$TMP/apf-decoded.pe" \
    --json "$TMP/report-two.json" > "$TMP/analyzer-two.txt"
cmp -s "$TMP/report-one.json" "$TMP/report-two.json"
cmp -s "$TMP/report-one.json" "$REPORT"
grep -Fq 'APF_POST_RESERVE_STATIC_REPORT start=0x84BED7BC prior=264 next=NtAllocateVirtualMemory operation=commit call=0x84BED808 return=0x84BED80C continuation=19 cumulative=283 indirect=0 opcode=0 switch=0 executed=0' \
    "$TMP/analyzer-one.txt"

python3 - "$REPORT" "$DOC" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
doc = doc_path.read_text(encoding="utf-8")

assert report["schema"] == "apf2k8_post_reserve_static/v1"
assert report["scope"] == {
    "leaf_adapter_invoked": False,
    "main_menu_proved": False,
    "method": "nonexecuting path-specific static continuation",
    "native_boot_proved": False,
    "subprocess_invoked": False,
    "translated_title_functions_called": False,
}

start = report["start_checkpoint"]
assert (start["pc"], start["lr"], start["r1"], start["r31"]) == (
    "0x84BED7BC", "0x84BED7BC", "0x7001FC00", "0x7001FC00")
assert start["r3_ntstatus"] == "0x00000000"
assert start["prior_executed_guest_instructions"] == 264
assert start["last_executed_guest_pc"] == "0x84BED7B8"
assert start["generated_instruction_at_start_executed"] is False
assert start["big_endian_cells"] == {
    "0x7001FC50_reserved_base": "0x40000000",
    "0x7001FD34_reserved_size": "0x00100000",
    "0x7001FD3C_rounded_commit_size": "0x00010000",
}
ledger = start["virtual_memory_ledger"]
assert ledger["active_allocation_count"] == 1
assert ledger["allocation_base_page"] == 0
assert ledger["allocation_page_count"] == 16
assert ledger["allocation_state"] == "reserve"
assert ledger["arena_base"] == "0x40000000"
assert ledger["page_size"] == "0x00010000"
assert ledger["backing_pattern_byte_exact_unchanged"] is True

trace = report["static_trace"]
expected_pcs = [
    "0x84BED7BC", "0x84BED7C0", "0x84BED7C4", "0x84BED7C8",
    "0x84BED7CC", "0x84BED7D0", "0x84BED7D8", "0x84BED7DC",
    "0x84BED7E0", "0x84BED7E4", "0x84BED7E8", "0x84BED7EC",
    "0x84BED7F0", "0x84BED7F4", "0x84BED7F8", "0x84BED7FC",
    "0x84BED800", "0x84BED804", "0x84BED808",
]
assert trace["ordered_guest_pcs"] == expected_pcs
assert trace["continuation_instruction_count_through_next_call"] == 19
assert trace["cumulative_instruction_count_through_next_call"] == 283
assert trace["unique_pc_count"] == 19
assert trace["first_pc"] == "0x84BED7BC"
assert trace["last_pc"] == "0x84BED808"
assert trace["ordered_pc_sha256"] == (
    "df3f3f6aec6fd3b6dbede92272b7a2ae22a6cbba63c9c60d0d9c4d4e9fe638fd")
assert trace["owner"] == "sub_84BED488"
assert trace["unresolved_indirect_before_boundary"] is False
assert trace["opcode_candidate_intersection_count"] == 0
assert trace["switch_tail_residue_intersection_count"] == 0

boundary = report["next_boundary"]
assert boundary["classification"] == "typed_import"
assert boundary["name"] == "NtAllocateVirtualMemory"
assert boundary["operation"] == "commit"
assert boundary["ordinal"] == 204
assert boundary["thunk"] == "0x84D0863C"
assert boundary["call_pc"] == "0x84BED808"
assert boundary["return_pc"] == "0x84BED80C"
assert boundary["typed_leaf_adapter_exact_site_supported"] is True
assert boundary["adapter_invoked_by_this_analysis"] is False
assert boundary["arguments"] == {
    "base_value_be_u32": "0x40000000",
    "r3_base_pointer": "0x7001FC54",
    "r4_size_pointer": "0x7001FD3C",
    "r5_allocation_type": "0x60001000",
    "r6_protection": "0x00000004",
    "r7_debug_memory": "0x00000000",
    "size_value_be_u32": "0x00010000",
}

authorization = report["authorization"]
assert authorization["typed_adapter_site_is_execution_authority"] is False
assert authorization[
    "existing_guarded_harness_authorizes_return_at_0x84BED7BC"] is False
assert authorization["continuation_executed_by_this_analysis"] is False
assert authorization["commit_executed_by_this_analysis"] is False
assert authorization["generated_return_0x84BED80C_executed"] is False
assert [item["order"] for item in report["ordered_prerequisites"]] == [1, 2, 3]
assert len(report["portme"]) == 3
assert [line.split(":", 1)[0] for line in report["portme"]] == [
    "// PORTME at 0x84BED7BC",
    "// PORTME at 0x84BED808",
    "// PORTME at 0x84BED80C",
]

assert doc.count("APF_POST_RESERVE_STATIC_VALIDATION_PASS") == 1
assert "Those 19 instructions were **not executed**" in doc
assert "ABI support, not execution authority" in doc
assert "no title or commit execution occurred" in doc.lower()
assert doc.count("// PORTME at 0x84BED") == 3

# Every durable input pin resolves to exact bytes. The decoded image is a
# validator-only temporary artifact and is intentionally represented by hash.
for key, item in report["inputs"].items():
    if key == "decoded_image":
        assert item["size"] == 54001664
        assert item["sha256"] == (
            "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf")
        continue
    path = Path(item["path"])
    data = path.read_bytes()
    assert len(data) == item["size"]
    assert hashlib.sha256(data).hexdigest() == item["sha256"]

serialized = report_path.read_text(encoding="utf-8")
for forbidden in (
        '"decoded_bytes"', '"raw_image_bytes"',
        '"translated_title_execution"', '"adapter_execution_dump"'):
    assert forbidden not in serialized
PY

# Fail closed if either the exact checkpoint or exact generated owner is
# replaced, even with a parseable/copy-equivalent path.
cp --reflink=auto "$PRIOR" "$TMP/forged-prior.json"
printf '\n' >> "$TMP/forged-prior.json"
if python3 "$ANALYZER" \
    --decoded "$TMP/apf-decoded.pe" \
    --prior-report "$TMP/forged-prior.json" \
    --json "$TMP/forged-prior-report.json" \
    > "$TMP/forged-prior.txt" 2>&1; then
    echo 'post-reserve analyzer accepted a changed checkpoint report' >&2
    exit 1
fi
test ! -e "$TMP/forged-prior-report.json"

cp --reflink=auto "$GENERATED" "$TMP/forged-generated.cpp"
printf '\n' >> "$TMP/forged-generated.cpp"
if python3 "$ANALYZER" \
    --decoded "$TMP/apf-decoded.pe" \
    --generated-source "$TMP/forged-generated.cpp" \
    --json "$TMP/forged-generated-report.json" \
    > "$TMP/forged-generated.txt" 2>&1; then
    echo 'post-reserve analyzer accepted changed generated code' >&2
    exit 1
fi
test ! -e "$TMP/forged-generated-report.json"

test "$(sha256sum "$XEX" | awk '{print $1}')" = "$EXPECTED_XEX"
test "$(sha256sum "$VOLUME" | awk '{print $1}')" = "$EXPECTED_VOLUME"
test "$(sha256sum "$PRIOR" | awk '{print $1}')" = "$EXPECTED_PRIOR"
test "$(sha256sum "$GENERATED" | awk '{print $1}')" = "$EXPECTED_GENERATED"

echo 'APF_POST_RESERVE_STATIC_VALIDATION_PASS start=0x84BED7BC prior=264 next=NtAllocateVirtualMemory operation=commit call=0x84BED808 return=0x84BED80C continuation=19 cumulative=283 indirect=0 opcode=0 switch=0 executed=0 originals_unchanged=yes'
