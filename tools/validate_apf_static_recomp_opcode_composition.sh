#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
volume='extracted/All-Pro Football 2K8 (USA)/0A'
vendor='tools/vendor/XenonRecomp'
baseline='build-static-recomp-apf/ppc-filtered'
probe='reports/static_recomp/apf2k8_static_recomp_probe.json'
config_source='reports/static_recomp/apf2k8_xenonrecomp_filtered_probe.toml'
switches='reports/static_recomp/apf2k8_xenon_switch_tables_filtered.toml'
patch='reports/static_recomp/apf2k8_opcode_candidates_composed.patch'
report='reports/static_recomp/apf2k8_opcode_candidates_composed.json'
tool='tools/apf_static_recomp_opcode_composition.py'
doc='docs/research/apf_static_recomp_opcode_composition.md'
hook_test='tests/apf_dcbst_hook_test.cpp'

isolated_patches=(
  'reports/static_recomp/apf2k8_opcode_gap_candidate.patch'
  'reports/static_recomp/apf2k8_frsqrte_candidate.patch'
  'reports/static_recomp/apf2k8_dcbst_candidate.patch'
)
source_reports=(
  'reports/static_recomp/apf2k8_opcode_gap_audit.json'
  'reports/static_recomp/apf2k8_frsqrte_semantics.json'
  'reports/static_recomp/apf2k8_dcbst_semantics.json'
)

for required in \
  "$xex" "$volume" "$probe" "$config_source" "$switches" \
  "$patch" "$report" "$tool" "$doc" "$hook_test" \
  "${isolated_patches[@]}" "${source_reports[@]}" \
  "$vendor/XenonRecomp/recompiler.cpp" \
  "$vendor/XenonUtils/ppc_context.h" \
  "$vendor/build/XenonRecomp/CMakeFiles/XenonRecomp.dir/main.cpp.o" \
  "$vendor/build/XenonRecomp/CMakeFiles/XenonRecomp.dir/test_recompiler.cpp.o" \
  "$vendor/build/XenonRecomp/CMakeFiles/XenonRecomp.dir/recompiler_config.cpp.o" \
  "$vendor/build/XenonAnalyse/libLibXenonAnalyse.a" \
  "$vendor/build/XenonUtils/libXenonUtils.a" \
  "$vendor/build/thirdparty/fmt/libfmt.a" \
  "$vendor/build/thirdparty/xxHash/cmake_unofficial/libxxhash.a" \
  "$vendor/build/thirdparty/disasm/libdisasm.a"; do
  test -f "$required"
done
test -d "$baseline"

test "$(command -v clang++-18)" = '/usr/bin/clang++-18'
test "$(clang++-18 --version | sed -n '1p')" = \
  'Ubuntu clang version 18.1.3 (1ubuntu1)'
test "$(git -C "$vendor" rev-parse HEAD)" = \
  'ddd128bcca99fe8bfbb99bea583c972351fa6ace'
git -C "$vendor" diff --quiet HEAD --
git -C "$vendor" diff --cached --quiet HEAD --

test "$(sha256sum "$xex" | cut -d' ' -f1)" = \
  '981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
test "$(sha256sum "$volume" | cut -d' ' -f1)" = \
  'dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
test "$(sha256sum "$patch" | cut -d' ' -f1)" = \
  '5a6f15ebb3ff6c0ae2735e370b04e93033cd6d493be0a7a2697379d63e6f26bd'

tree_manifest_digest() {
  python3 - "$1" <<'PY'
from pathlib import Path
import hashlib
import sys

directory = Path(sys.argv[1])
files = sorted((path for path in directory.iterdir() if path.is_file()),
               key=lambda path: path.name)
manifest = b"".join(
    f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n".encode()
    for path in files
)
print(len(files), hashlib.sha256(manifest).hexdigest())
PY
}

originals_before=$(sha256sum "$xex" "$volume")
vendor_before=$(sha256sum \
  "$vendor/XenonRecomp/recompiler.cpp" \
  "$vendor/XenonUtils/ppc_context.h")
baseline_before=$(tree_manifest_digest "$baseline")
test "$baseline_before" = \
  '240 1a0264262be8cc48e44e56c7c87c3a0f77def90dd62d40ea9842d174baed5fd1'

temporary=$(mktemp -d /tmp/apf-opcode-composition.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"
python3 -m py_compile "$tool"

# This check reads the pinned vendor tree but does not change it.
(
  cd "$vendor"
  git apply --check "$root/$patch"
)

# The candidate is applied only to two throwaway source directories. All
# unchanged include trees and static libraries remain pinned read-only inputs.
cp -a "$vendor/XenonRecomp" "$temporary/XenonRecomp"
cp -a "$vendor/XenonUtils" "$temporary/XenonUtils"
(
  cd "$temporary"
  git apply "$root/$patch"
)

test "$(sha256sum "$temporary/XenonRecomp/recompiler.cpp" | cut -d' ' -f1)" = \
  'b12b0cd01f0d29c0d0eff00d145289789d0051b2091f3176a732e8607ca44020'
test "$(sha256sum "$temporary/XenonUtils/ppc_context.h" | cut -d' ' -f1)" = \
  '0c217483f60a4c70d15de1a2ac3a652bf753fc183c2deef4f04b1f8a4727ba52'

includes=(
  -I"$temporary/XenonRecomp"
  -I"$temporary/XenonUtils"
  -I"$root/$vendor/XenonAnalyse"
  -I"$root/$vendor/thirdparty/simde"
  -I"$root/$vendor/thirdparty/disasm"
  -I"$root/$vendor/thirdparty/fmt/include"
  -I"$root/$vendor/thirdparty/xxHash"
  -I"$root/$vendor/thirdparty/tomlplusplus/include"
)
clang++-18 -std=gnu++17 -O3 -DNDEBUG \
  -DXENON_RECOMP_USE_ALIAS -D_CRT_SECURE_NO_WARNINGS \
  -Wno-switch -Wno-unused-variable -Wno-null-arithmetic \
  "${includes[@]}" \
  -fsyntax-only "$temporary/XenonRecomp/recompiler.cpp"
clang++-18 -std=gnu++17 -O3 -DNDEBUG \
  -DXENON_RECOMP_USE_ALIAS -D_CRT_SECURE_NO_WARNINGS \
  -Wno-switch -Wno-unused-variable -Wno-null-arithmetic \
  "${includes[@]}" \
  -c "$temporary/XenonRecomp/recompiler.cpp" \
  -o "$temporary/recompiler.o"

object_root="$root/$vendor/build/XenonRecomp/CMakeFiles/XenonRecomp.dir"
clang++-18 -O3 -DNDEBUG \
  "$object_root/main.cpp.o" \
  "$temporary/recompiler.o" \
  "$object_root/test_recompiler.cpp.o" \
  "$object_root/recompiler_config.cpp.o" \
  -o "$temporary/XenonRecompPatched" \
  "$root/$vendor/build/XenonAnalyse/libLibXenonAnalyse.a" \
  "$root/$vendor/build/XenonUtils/libXenonUtils.a" \
  "$root/$vendor/build/thirdparty/fmt/libfmt.a" \
  "$root/$vendor/build/thirdparty/xxHash/cmake_unofficial/libxxhash.a" \
  "$root/$vendor/build/thirdparty/disasm/libdisasm.a"

ln -s "$root/$xex" "$temporary/default.xex"
ln -s "$root/$switches" "$temporary/switches.toml"
mkdir "$temporary/out"
python3 - "$temporary/config.toml" "$root/$config_source" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[2]).read_text(encoding="utf-8")
source = source.replace(
    "../../extracted/All-Pro Football 2K8 (USA)/default.xex", "default.xex")
source = source.replace(
    "../../build-static-recomp-apf/ppc-filtered", "out")
source = source.replace(
    "apf2k8_xenon_switch_tables_filtered.toml", "switches.toml")
Path(sys.argv[1]).write_text(source, encoding="utf-8")
PY

"$temporary/XenonRecompPatched" \
  "$temporary/config.toml" "$temporary/XenonUtils/ppc_context.h" \
  > "$temporary/patched.log" 2>&1
test "$(tail -1 "$temporary/patched.log")" = \
  'Recompiling functions... 100%'

test "$(find "$temporary/out" -maxdepth 1 -type f | wc -l)" -eq 240
test "$(find "$temporary/out" -maxdepth 1 -type f -name '*.cpp' | wc -l)" \
  -eq 237
test "$(find "$temporary/out" -maxdepth 1 -type f \
  -name 'ppc_recomp.*.cpp' | wc -l)" -eq 236

# Parsing generated functions is a compile-only check. It does not link or run
# any title function.
find "$temporary/out" -maxdepth 1 -type f -name '*.cpp' -print0 | \
  sort -z | \
  xargs -0 -P12 -n1 clang++-18 -std=c++20 -O0 -fsyntax-only \
    -I"$temporary/out" \
    -I"$temporary/XenonUtils" \
    -I"$root/$vendor/thirdparty/simde"

# Exercise only the host-side cache-hook contract, including expected child
# SIGABRT cases. This binary does not contain or call translated title code.
clang++-18 -std=c++20 -O2 -Wall -Wextra -Werror \
  -I"$temporary/out" \
  -I"$root/$vendor/thirdparty/simde" \
  "$hook_test" -o "$temporary/dcbst_hook_test"
"$temporary/dcbst_hook_test" \
  > "$temporary/hook.stdout" 2> "$temporary/hook.stderr"
test ! -s "$temporary/hook.stderr"
test "$(cat "$temporary/hook.stdout")" = \
  'APF_DCBST_HOOK_TEST_PASS nonzero_ra_ea=0x00000145 nonzero_ra_line=0x00000100 rb_only_ea=0x00ABCDEF rb_only_line=0x00ABCD80 line_size=128 default_signal=6 invalid_size_signal=6'

python3 - \
  "$probe" "$temporary/patched.log" "$temporary/out" \
  "$temporary/XenonRecomp/recompiler.cpp" \
  "$temporary/XenonUtils/ppc_context.h" \
  "$temporary/hook.stdout" "$temporary/hook.stderr" \
  "$temporary/observation.json" <<'PY'
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

(probe_path, log_path, out_path, recompiler_path, context_path,
 hook_stdout_path, hook_stderr_path, observation_path) = map(
    Path, sys.argv[1:])
probe = json.loads(probe_path.read_text(encoding="utf-8"))
before = probe["instruction_gaps"]["mnemonic_counts"]
assert sum(before.values()) == 172

lines = log_path.read_text(encoding="utf-8").splitlines()
unrecognized_pattern = re.compile(
    r"^Unrecognized instruction at 0x[0-9A-F]+: (\w+)$")
after = Counter(
    match.group(1) for line in lines
    if (match := unrecognized_pattern.match(line)))
assert not after

switch_pattern = re.compile(
    r"^ERROR: Switch case at ([0-9A-F]+) is trying to jump outside function: "
    r"([0-9A-F]+)$")
switch_errors = [
    match.groups() for line in lines if (match := switch_pattern.match(line))
]
assert len(switch_errors) == 3337
assert len({base for base, _ in switch_errors}) == 196

output = out_path
files = sorted((path for path in output.iterdir() if path.is_file()),
               key=lambda path: path.name)
manifest = b"".join(
    f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n".encode()
    for path in files
)
numbered = sorted(
    output.glob("ppc_recomp.*.cpp"),
    key=lambda path: int(path.name.split(".")[1]))
generated = "".join(path.read_text(encoding="utf-8") for path in numbered)

expected_mnemonics = {
    "dcbst": 1, "frsqrte": 28, "mulhdu": 5, "stfsu": 8,
    "vaddsws": 6, "vandc": 16, "vpkswss": 51, "vrfip": 1,
    "vsel128": 54, "vsrab": 1, "vsubuwm": 1,
}
comment_counts = {
    mnemonic: len(re.findall(
        rf"^\s*// {mnemonic}(?:\s|$)", generated, re.MULTILINE))
    for mnemonic in sorted(expected_mnemonics)
}
assert comment_counts == expected_mnemonics

observation = {
    "schema": "apf2k8_static_recomp_opcode_composition_observation/v1",
    "candidate_patch_applied_in_temporary_copy": True,
    "patched_recompiler_syntax_pass": True,
    "patched_recompiler_link_pass": True,
    "translation_completed": True,
    "translation_log_terminal": lines[-1],
    "unrecognized_instruction_count_before": 172,
    "unrecognized_instruction_count_after": sum(after.values()),
    "unrecognized_mnemonic_counts_after": dict(sorted(after.items())),
    "generated_file_count": len(files),
    "generated_cpp_count": len(list(output.glob("*.cpp"))),
    "generated_numbered_cpp_count": len(numbered),
    "generated_translation_units_syntax_checked": 237,
    "generated_translation_unit_syntax_failure_count": 0,
    "data_state_candidate_site_count": 143,
    "frsqrte_candidate_site_count": 28,
    "dcbst_candidate_site_count": 1,
    "composed_candidate_site_count": 172,
    "generated_mnemonic_comment_counts": comment_counts,
    "frsqrte_helper_call_count": len(re.findall(
        r"^\s*ctx\.f\d+\.u64 = PPC_FRSQRTE_XENIA_6E5B832_VALUE\(",
        generated, re.MULTILINE)),
    "dcbst_hook_call_count": len(re.findall(
        r"^\s*PPC_DATA_CACHE_BLOCK_STORE\(", generated, re.MULTILINE)),
    "dcbst_address_portme_count": generated.count(
        "// PORTME(0x84B46518):"),
    "switch_outside_function_error_count": len(switch_errors),
    "switch_base_with_error_count": len({base for base, _ in switch_errors}),
    "output_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
    "composed_recompiler_sha256": hashlib.sha256(
        recompiler_path.read_bytes()).hexdigest(),
    "composed_context_sha256": hashlib.sha256(
        context_path.read_bytes()).hexdigest(),
    "dcbst_hook_test_exit_code": 0,
    "dcbst_hook_test_stdout": hook_stdout_path.read_text(encoding="utf-8"),
    "dcbst_hook_test_stderr_empty": not hook_stderr_path.read_bytes(),
    "compiler": subprocess.run(
        ["clang++-18", "--version"], check=True, capture_output=True,
        text=True).stdout.splitlines()[0],
    "title_code_executed": False,
    "vendor_originals_or_baseline_modified": False,
    "switch_tail_candidate_composed": False,
}
observation_path.write_text(
    json.dumps(observation, indent=2) + "\n", encoding="utf-8")
PY

python3 "$tool" \
  --candidate-observation "$temporary/observation.json" \
  --reconstructed-patch "$temporary/reconstructed.patch" \
  --json "$temporary/report.json"
cmp "$temporary/reconstructed.patch" "$patch"
cmp "$temporary/report.json" "$report"

python3 - "$report" "$patch" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, patch_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_static_recomp_opcode_composition/v1"
assert report["result"] == {
    "baseline_unrecognized_instruction_site_count": 172,
    "composed_unrecognized_instruction_site_count": 0,
    "all_baseline_opcode_omissions_have_candidate_emission": True,
    "data_state_candidate_site_count": 143,
    "frsqrte_candidate_site_count": 28,
    "dcbst_candidate_site_count": 1,
    "composed_candidate_site_count": 172,
    "generated_cpp_count": 237,
    "generated_translation_units_syntax_passed": 237,
    "candidate_applied_to_vendor": False,
    "title_code_executed": False,
    "architecture_complete": False,
    "ready_to_merge": False,
}
assert report["semantic_boundaries"]["saturating_vmx"] == {
    "site_count": 57,
    "lane_data_candidate_present": True,
    "sticky_vscr_sat_implemented": False,
}
assert report["semantic_boundaries"]["control_flow"] == {
    "switch_tail_candidate_included": False,
    "outside_function_diagnostics_in_opcode_only_regeneration": 3337,
    "affected_switch_bases": 196,
    "opcode_coverage_implies_control_flow_complete": False,
}
assert report["regeneration"]["compiler"] == \
    "Ubuntu clang version 18.1.3 (1ubuntu1)"
assert len(report["portme"]) == 5
assert all("PORTME" in item for item in report["portme"])
assert report["composition"]["switch_tail_candidate_included"] is False
assert report["sources"]["report_embeds_title_bytes"] is False

patch = patch_path.read_text(encoding="utf-8")
assert patch.count("+    case PPC_INST_FRSQRTE:") == 1
assert patch.count("+    case PPC_INST_DCBST:") == 1
assert patch.count("PORTME: update sticky VSCR.SAT") == 2

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Outcome", "## Worked", "## Failed or unproved", "## Blocking",
    "172 unrecognized", "zero", "237 generated C++ translation units",
    "3,337 outside-function", "VSCR.SAT", "FPSCR", "GPU/DMA/MMIO",
    "not a playable or merge-ready port",
    "APF_STATIC_RECOMP_OPCODE_COMPOSITION_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

test "$(sha256sum "$xex" "$volume")" = "$originals_before"
test "$(sha256sum \
  "$vendor/XenonRecomp/recompiler.cpp" \
  "$vendor/XenonUtils/ppc_context.h")" = "$vendor_before"
test "$(tree_manifest_digest "$baseline")" = "$baseline_before"
git -C "$vendor" diff --quiet HEAD --
git -C "$vendor" diff --cached --quiet HEAD --

echo 'APF_STATIC_RECOMP_OPCODE_COMPOSITION_VALIDATION_PASS before=172 after=0 candidates=143+28+1 tus=237 switch_errors=3337 architecture_complete=no vendor_unchanged=yes originals_unchanged=yes title_executed=no'
