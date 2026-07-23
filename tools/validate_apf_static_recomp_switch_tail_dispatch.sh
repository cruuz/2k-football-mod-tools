#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
baseline_log='reports/static_recomp/apf2k8_xenonrecomp_filtered.log'
candidate_log='reports/static_recomp/apf2k8_xenonrecomp_switch_tail_candidate.log'
switches='reports/static_recomp/apf2k8_xenon_switch_tables_filtered.toml'
recovered_switches='reports/static_recomp/apf2k8_xenon_switch_tables_switch_tail_candidate.toml'
patch='reports/static_recomp/apf2k8_switch_tail_dispatch_candidate.patch'
config='reports/static_recomp/apf2k8_xenonrecomp_switch_tail_candidate.toml'
baseline_generated='build-static-recomp-apf/ppc-filtered'
candidate_generated='build-static-recomp-apf/ppc-switch-tail-candidate'
ledger='research/functions/apf2k8/ledger'
vendor='tools/vendor/XenonRecomp'
tool='tools/apf_static_recomp_switch_tail_dispatch.py'
report='reports/static_recomp/apf2k8_static_recomp_switch_tail_dispatch.json'
residue='reports/static_recomp/apf2k8_static_recomp_switch_tail_residue.tsv'
doc='docs/research/apf_static_recomp_switch_tail_dispatch.md'

for required in \
    "$xex" "$baseline_log" "$candidate_log" "$switches" \
    "$recovered_switches" "$patch" "$config" "$tool" "$report" \
    "$residue" "$doc" tools/xex_extract_pe.cpp \
    "$baseline_generated/ppc_func_mapping.cpp" \
    "$candidate_generated/ppc_func_mapping.cpp" \
    "$vendor/XenonRecomp/recompiler.cpp"; do
  test -f "$required"
done
test -d "$ledger"
test -d "$vendor/thirdparty/simde"
test "$(command -v clang++-18)" = '/usr/bin/clang++-18'
test "$(sha256sum "$xex" | cut -d' ' -f1)" = \
  '981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'

temporary=$(mktemp -d /tmp/apf-switch-tail-dispatch.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile "$tool"

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -I"$vendor/XenonUtils" \
  -I"$vendor/thirdparty/TinySHA1" \
  -I"$vendor/thirdparty/tiny-AES-c" \
  "$vendor/build/XenonUtils/libXenonUtils.a" \
  -o "$temporary/xex_extract_pe"

"$temporary/xex_extract_pe" "$xex" "$temporary/apf.pe" | \
  grep -F 'blocks=642 chunks=1648 lzx_bytes=37717546 image_bytes=54001664 window_size=32768'

common_args=(
  --pe "$temporary/apf.pe"
  --baseline-log "$baseline_log"
  --switches "$switches"
  --baseline-generated "$baseline_generated"
  --ledger-dir "$ledger"
  --vendor-root "$vendor"
  --patch "$patch"
  --candidate-config "$config"
  --xenon-utils "$vendor/XenonUtils"
  --simde "$vendor/thirdparty/simde"
)

python3 "$tool" "${common_args[@]}" \
  --recovered-switches "$temporary/recovered.toml" \
  --emit-only | grep -F \
  'APF_SWITCH_TAIL_RECOVERY_EMIT_PASS unique=46 occurrences=263'
cmp "$temporary/recovered.toml" "$recovered_switches"

# Build and execute the patch in a disposable vendor clone. The pinned checkout
# and both canonical generated trees remain read-only inputs to this step.
cp -a --reflink=auto "$vendor" "$temporary/vendor"
git -C "$temporary/vendor" apply "$root/$patch"
rm -rf "$temporary/vendor/build-candidate"
CC=/usr/bin/clang-18 CXX=/usr/bin/clang++-18 cmake \
  -S "$temporary/vendor" -B "$temporary/vendor/build-candidate" \
  -DCMAKE_BUILD_TYPE=Release > "$temporary/cmake.log"
cmake --build "$temporary/vendor/build-candidate" \
  --target XenonRecomp -j12 > "$temporary/build.log"

mkdir -p "$temporary/config" "$temporary/candidate"
cp "$recovered_switches" "$temporary/config/switches.toml"
python3 - "$config" "$root" "$temporary" <<'PY'
from pathlib import Path
import os
import sys

source, root, temporary = map(Path, sys.argv[1:])
config_dir = temporary / "config"
text = source.read_text(encoding="utf-8")
text = text.replace(
    '../../extracted/All-Pro Football 2K8 (USA)/default.xex',
    os.path.relpath(root / 'extracted/All-Pro Football 2K8 (USA)/default.xex', config_dir),
)
text = text.replace(
    '../../build-static-recomp-apf/ppc-switch-tail-candidate',
    '../candidate',
)
text = text.replace(
    'apf2k8_xenon_switch_tables_switch_tail_candidate.toml',
    'switches.toml',
)
(config_dir / 'candidate.toml').write_text(text, encoding='utf-8')
PY

"$temporary/vendor/build-candidate/XenonRecomp/XenonRecomp" \
  "$temporary/config/candidate.toml" \
  "$vendor/XenonUtils/ppc_context.h" > "$temporary/candidate.log"
cmp "$temporary/candidate.log" "$candidate_log"

python3 - "$candidate_generated" "$temporary/candidate" "$report" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

canonical, rebuilt, report_path = map(Path, sys.argv[1:])
expected = json.loads(report_path.read_text(encoding="utf-8"))["candidate_generated_tree"]

def summary(directory):
    files = sorted((path for path in directory.iterdir() if path.is_file()), key=lambda p: p.name)
    state = hashlib.sha256()
    total = 0
    cpp = 0
    for path in files:
        data = path.read_bytes()
        state.update(path.name.encode() + b"\0")
        state.update(len(data).to_bytes(8, "big"))
        state.update(hashlib.sha256(data).digest())
        total += len(data)
        cpp += path.suffix == ".cpp"
    return {
        "file_count": len(files), "cpp_file_count": cpp,
        "total_bytes": total, "tree_sha256": state.hexdigest(),
    }

assert summary(canonical) == expected
assert summary(rebuilt) == expected
PY

python3 "$tool" "${common_args[@]}" \
  --candidate-log "$candidate_log" \
  --recovered-switches "$temporary/full-recovered.toml" \
  --candidate-generated "$candidate_generated" \
  --jobs 12 \
  --json "$temporary/report.json" \
  --tsv "$temporary/residue.tsv" | grep -F \
  'APF_STATIC_RECOMP_SWITCH_TAIL_DISPATCH_PASS baseline=3337 resolved=2261 remaining=1076 unique_remaining=190 syntax=237/237 semantics=partial runtime=no'

cmp "$temporary/full-recovered.toml" "$recovered_switches"
cmp "$temporary/report.json" "$report"
cmp "$temporary/residue.tsv" "$residue"

python3 - "$report" "$residue" "$doc" "$patch" <<'PY'
import csv
import json
from pathlib import Path
import sys

report_path, residue_path, doc_path, patch_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_static_recomp_switch_tail_dispatch/v1"
assert report["result"] == {
    "all_candidate_translation_units_syntax_passed": True,
    "baseline_cross_function_switch_occurrences": 3337,
    "baseline_unique_switch_targets": 806,
    "candidate_tail_dispatch_occurrences": 2261,
    "exact_mapped_tail_dispatch_occurrences": 1998,
    "exact_mapped_unique_targets": 570,
    "ghidra_gated_branch_fold_occurrences": 10,
    "ghidra_gated_branch_fold_unique_targets": 3,
    "ghidra_gated_terminal_fragment_fold_occurrences": 253,
    "ghidra_gated_terminal_fragment_fold_unique_targets": 43,
    "native_boot_proved": False,
    "remaining_portme_occurrences": 1076,
    "remaining_unique_targets": 190,
    "whole_title_semantic_correctness_proved": False,
}
assert report["residue"]["unique_by_classification"] == {
    "no_ghidra_body": 118,
    "outside_code_false_positive": 3,
    "same_ghidra_body": 69,
}
assert report["residue"]["occurrences_by_classification"] == {
    "no_ghidra_body": 825,
    "outside_code_false_positive": 3,
    "same_ghidra_body": 248,
}
assert report["candidate_generated_tree"] == {
    "cpp_file_count": 237,
    "file_count": 240,
    "total_bytes": 130680345,
    "tree_sha256": "c4fca0a78a5013efeeb7ffaba72e92c5f3b9fe191dd54e4c117e49c02132bfb7",
}
syntax = report["syntax_gate"]
assert syntax["translation_unit_count"] == syntax["passed_count"] == 237
assert syntax["failed_count"] == 0
assert syntax["translation_units_with_output"] == []
assert len(syntax["outcomes"]) == 237
assert len(report["portme"]) == 190

recoveries = report["recovered_case_entries"]
branches = [row for row in recoveries
            if row["recovery_kind"] == "direct_branch_to_exact_mapping"]
terminals = [row for row in recoveries
             if row["recovery_kind"] == "byte_identical_terminal_fragment"]
assert [(row["case_entry"], row["mapped_replacement_entry"], row["occurrence_count"])
        for row in branches] == [
    ("0x8464A870", "0x849642B8", 1),
    ("0x8493D600", "0x84946BB8", 1),
    ("0x84ADB2D8", "0x84AD9F40", 8),
]
assert len(terminals) == 43
assert sum(row["occurrence_count"] for row in terminals) == 253
assert all(len(row["raw_words"]) in (1, 2) for row in terminals)

with residue_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 190
assert all(row["portme"].startswith("// PORTME(0x") for row in rows)
assert {row["target"] for row in rows[:3]} == {
    "0x2B0A000D", "0x554A502A", "0x7D4AD670"
}

patch = patch_path.read_text(encoding="utf-8")
assert "CROSS_FUNCTION_SWITCH_TAIL" in patch
assert "PORTME: unresolved cross-function switch target" in patch

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "2,261 of 3,337", "1,076 occurrences / 190 unique targets",
    "237/237", "0x84B29BCC",
    "No longer or control-flow-bearing multi-instruction fragment was guessed",
    "## Worked", "## Failed or unproved", "## Blocking",
    "APF_STATIC_RECOMP_SWITCH_TAIL_DISPATCH_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

test -z "$(git -C "$vendor" status --short --untracked-files=no)"

echo 'APF_STATIC_RECOMP_SWITCH_TAIL_DISPATCH_VALIDATION_PASS baseline=3337 resolved=2261 remaining=1076 unique_remaining=190 syntax=237/237 semantics=partial runtime=no'
