#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
decoded='reports/static_recomp/apf2k8_opcode_gap_decoded.tsv'
baseline_report='reports/static_recomp/apf2k8_static_recomp_probe.json'
baseline_unit='build-static-recomp-apf/ppc-filtered/ppc_recomp.191.cpp'
config_source='reports/static_recomp/apf2k8_xenonrecomp_filtered_probe.toml'
switches='reports/static_recomp/apf2k8_xenon_switch_tables_filtered.toml'
vendor='tools/vendor/XenonRecomp'
xenia='/media/noah/Storage/.codex-tmp/xenia-source'
tool='tools/apf_dcbst_semantics.py'
patch='reports/static_recomp/apf2k8_dcbst_candidate.patch'
hook_test='tests/apf_dcbst_hook_test.cpp'
report='reports/static_recomp/apf2k8_dcbst_semantics.json'
doc='docs/research/apf_dcbst_semantics.md'

for required in \
  "$xex" "$decoded" "$baseline_report" "$baseline_unit" \
  "$config_source" "$switches" "$tool" "$patch" "$hook_test" \
  "$report" "$doc" \
  "$vendor/XenonRecomp/recompiler.cpp" \
  "$vendor/XenonUtils/ppc_context.h" \
  "$vendor/build/XenonRecomp/CMakeFiles/XenonRecomp.dir/main.cpp.o" \
  "$vendor/build/XenonRecomp/CMakeFiles/XenonRecomp.dir/test_recompiler.cpp.o" \
  "$vendor/build/XenonRecomp/CMakeFiles/XenonRecomp.dir/recompiler_config.cpp.o" \
  "$vendor/build/XenonAnalyse/libLibXenonAnalyse.a" \
  "$vendor/build/XenonUtils/libXenonUtils.a" \
  "$vendor/build/thirdparty/fmt/libfmt.a" \
  "$vendor/build/thirdparty/xxHash/cmake_unofficial/libxxhash.a" \
  "$vendor/build/thirdparty/disasm/libdisasm.a" \
  "$xenia/src/xenia/cpu/ppc/ppc_emit_memory.cc" \
  "$xenia/src/xenia/cpu/backend/x64/x64_seq_memory.cc" \
  "$xenia/src/xenia/cpu/hir/opcodes.h" \
  "$xenia/src/xenia/cpu/hir/hir_builder.cc"; do
  test -f "$required"
done

test "$(command -v clang++-18)" = '/usr/bin/clang++-18'
test "$(git -C "$vendor" rev-parse HEAD)" = \
  'ddd128bcca99fe8bfbb99bea583c972351fa6ace'
test "$(git -C "$xenia" rev-parse HEAD)" = \
  '95a5c3ee250f80c3b9d139658649d9ffb6db3eec'
git -C "$vendor" diff --quiet HEAD --
git -C "$xenia" diff --quiet HEAD --

temporary=$(mktemp -d /tmp/apf-dcbst-semantics.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"
python3 -m py_compile "$tool"

inputs=(
  "$xex"
  "$decoded"
  "$baseline_report"
  "$baseline_unit"
  "$vendor/XenonRecomp/recompiler.cpp"
  "$vendor/XenonUtils/ppc_context.h"
  "$xenia/src/xenia/cpu/ppc/ppc_emit_memory.cc"
  "$xenia/src/xenia/cpu/backend/x64/x64_seq_memory.cc"
  "$xenia/src/xenia/cpu/hir/opcodes.h"
  "$xenia/src/xenia/cpu/hir/hir_builder.cc"
  "$patch"
  "$hook_test"
  "$tool"
  "$doc"
)
sha256sum "${inputs[@]}" > "$temporary/before.sha256"

test "$(sha256sum "$xex" | cut -d' ' -f1)" = \
  '981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'
test "$(sha256sum "$patch" | cut -d' ' -f1)" = \
  '018ce6f0fe2596b59606cfd85eb77648eaa32fcecab7ff78a213ac2128847de1'
test "$(sha256sum "$hook_test" | cut -d' ' -f1)" = \
  '21155e45fe713f0e6a25f538dfce206891f4c17a3505054c50004d7791b15b26'

(
  cd "$vendor"
  git apply --check "$root/$patch"
)

# Apply only the dcbst candidate in a throwaway source copy. Pinned build
# products and all unmodified third-party includes remain read-only inputs.
cp -a "$vendor/XenonRecomp" "$temporary/XenonRecomp"
cp -a "$vendor/XenonUtils" "$temporary/XenonUtils"
(
  cd "$temporary"
  git apply "$root/$patch"
)

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

clang++-18 -std=c++20 -O2 -Wall -Wextra -Werror \
  -I"$temporary/out" \
  -I"$root/$vendor/thirdparty/simde" \
  "$hook_test" -o "$temporary/hook_test"
"$temporary/hook_test" \
  > "$temporary/hook.stdout" 2> "$temporary/hook.stderr"
test ! -s "$temporary/hook.stderr"
test "$(cat "$temporary/hook.stdout")" = \
  'APF_DCBST_HOOK_TEST_PASS nonzero_ra_ea=0x00000145 nonzero_ra_line=0x00000100 rb_only_ea=0x00ABCDEF rb_only_line=0x00ABCD80 line_size=128 default_signal=6 invalid_size_signal=6'

test "$(find "$temporary/out" -maxdepth 1 -type f -name '*.cpp' | wc -l)" \
  -eq 237
find "$temporary/out" -maxdepth 1 -type f -name '*.cpp' -print0 | \
  sort -z | \
  xargs -0 -P12 -n1 clang++-18 -std=c++20 -O0 -fsyntax-only \
    -I"$temporary/out" \
    -I"$root/$vendor/XenonUtils" \
    -I"$root/$vendor/thirdparty/simde"

python3 - \
  "$baseline_report" "$temporary/patched.log" "$temporary/out" \
  "$temporary/hook.stdout" "$temporary/hook.stderr" \
  "$temporary/observation.json" <<'PY'
from collections import Counter
import json
from pathlib import Path
import re
import signal
import sys

baseline_path, log_path, output_path, hook_out_path, hook_err_path, observation_path = map(
    Path, sys.argv[1:])
baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
before = baseline["instruction_gaps"]["mnemonic_counts"]
assert sum(before.values()) == 172
assert before["dcbst"] == 1

log = log_path.read_text(encoding="utf-8").splitlines()
pattern = re.compile(r"^Unrecognized instruction at 0x[0-9A-F]+: (\w+)$")
after = Counter(
    match.group(1) for line in log if (match := pattern.match(line)))
expected_after = {
    "frsqrte": 28, "mulhdu": 5, "stfsu": 8, "vaddsws": 6,
    "vandc": 16, "vpkswss": 51, "vrfip": 1, "vsel128": 54,
    "vsrab": 1, "vsubuwm": 1,
}
assert dict(sorted(after.items())) == expected_after
assert sum(after.values()) == 171 and after["dcbst"] == 0

output = output_path
all_cpp = sorted(output.glob("*.cpp"))
numbered = sorted(
    output.glob("ppc_recomp.*.cpp"),
    key=lambda path: int(path.name.split(".")[1]))
assert len(all_cpp) == 237 and len(numbered) == 236
texts = {path: path.read_text(encoding="utf-8") for path in numbered}
site_units = [path for path, text in texts.items()
              if "PORTME(0x84B46518)" in text]
assert len(site_units) == 1
site = site_units[0]
site_text = texts[site]
hook_line = next(line.strip() for line in site_text.splitlines()
                 if "PPC_DATA_CACHE_BLOCK_STORE" in line)
portme_line = next(line.strip() for line in site_text.splitlines()
                   if "PORTME(0x84B46518)" in line)
assert site.name == "ppc_recomp.191.cpp"
assert "PPC_FUNC_IMPL(__imp__sub_84B464D8)" in site_text
assert hook_line == (
    "PPC_DATA_CACHE_BLOCK_STORE((ctx.r11.u32 + ctx.r9.u32), 128);")
assert sum(text.count("PPC_DATA_CACHE_BLOCK_STORE")
           for text in texts.values()) == 1
assert sum(text.count("PORTME(0x84B46518)")
           for text in texts.values()) == 1

hook_stdout = hook_out_path.read_text(encoding="utf-8")
hook_stderr = hook_err_path.read_text(encoding="utf-8")
assert signal.SIGABRT == 6
expected_hook = (
    "APF_DCBST_HOOK_TEST_PASS nonzero_ra_ea=0x00000145 "
    "nonzero_ra_line=0x00000100 rb_only_ea=0x00ABCDEF "
    "rb_only_line=0x00ABCD80 line_size=128 default_signal=6 "
    "invalid_size_signal=6\n")
assert hook_stdout == expected_hook and hook_stderr == ""

observation = {
    "schema": "apf2k8_dcbst_candidate_observation/v1",
    "candidate_patch_applied_in_temporary_copy": True,
    "patched_recompiler_syntax_pass": True,
    "patched_recompiler_link_pass": True,
    "translation_completed": True,
    "translation_log_terminal": log[-1],
    "unrecognized_instruction_count_before": 172,
    "unrecognized_instruction_count_after": 171,
    "unrecognized_mnemonic_counts_after": dict(sorted(after.items())),
    "dcbst_omission_count_before": 1,
    "dcbst_omission_count_after": 0,
    "generated_cpp_count": len(all_cpp),
    "generated_numbered_cpp_count": len(numbered),
    "generated_dcbst_hook_call_count": 1,
    "generated_address_specific_portme_count": 1,
    "generated_site_unit": site.name,
    "generated_site_function": "0x84B464D8",
    "generated_site_address": "0x84B46518",
    "generated_site_hook_line": hook_line,
    "generated_site_portme_line": portme_line,
    "syntax_checked_cpp_count": len(all_cpp),
    "syntax_failure_count": 0,
    "hook_test_exit_code": 0,
    "hook_test_stdout": hook_stdout,
    "hook_test_stderr_empty": True,
    "default_hook_signal": "SIGABRT",
    "invalid_line_size_signal": "SIGABRT",
    "title_code_executed": False,
    "vendor_or_baseline_modified": False,
}
observation_path.write_text(
    json.dumps(observation, indent=2) + "\n", encoding="utf-8")
PY

python3 "$tool" \
  --xex "$xex" \
  --decoded-tsv "$decoded" \
  --generated-unit "$baseline_unit" \
  --vendor-root "$vendor" \
  --xenia-root "$xenia" \
  --candidate-patch "$patch" \
  --hook-test "$hook_test" \
  --candidate-observation "$temporary/observation.json" \
  --json "$temporary/report.json"
cmp "$temporary/report.json" "$report"

python3 - "$report" "$patch" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, patch_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_dcbst_semantics/v1"
assert report["result"] == {
    "dcbst_site_count": 1,
    "containing_function_count": 1,
    "exact_ra0_effective_address_emission_proved": True,
    "xenon_128_byte_line_contract_proved": True,
    "runtime_overridable_hook_present_in_candidate": True,
    "default_hook_fail_fast_proved": True,
    "invalid_line_size_fail_fast_proved": True,
    "dcbst_omission_count_after_isolated_regeneration": 0,
    "generated_translation_units_syntax_passed": 237,
    "candidate_applied_to_vendor": False,
    "gpu_dma_mmio_visibility_policy_implemented": False,
    "architecture_complete_runtime_proved": False,
    "title_code_executed": False,
}

ibm = report["official_ibm_semantics"]
assert ibm["source"].startswith("https://www.ibm.com/docs/")
assert ibm["effective_address"] == \
    "RA != 0 ? GPR[RA] + GPR[RB] : GPR[RB]"
assert ibm["translation_and_protection"] == \
    "treat as a load from the addressed byte"
assert ibm["fixed_point_exception_register_affected"] is False

xenia = report["pinned_xenia"]
assert xenia["commit"] == "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"
assert xenia["effective_address_helper"]["line"] == 30
assert xenia["dcbst_emitter"]["line"] == 1089
assert xenia["dcbst_emitter"]["cache_control_type"] == "DATA_STORE"
assert xenia["dcbst_emitter"]["xenon_cache_line_size"] == 128
assert xenia["x64_lowering"]["data_store_action"] == \
    "clflush addressed host line"

site = report["apf_site"]
assert site["address"] == "0x84B46518"
assert site["raw_word"] == "0x7C0B486C"
assert site["function_start"] == "0x84B464D8"
assert site["alternate_dcbf_address"] == "0x84B464F8"
assert site["loop_stride_bytes"] == 128
assert site["x_form_decode"] == {
    "primary_opcode": 31, "ra": 11, "rb": 9,
    "extended_opcode": 54, "record_bit": 0}
assert site["candidate_generated_expression"] == (
    "PPC_DATA_CACHE_BLOCK_STORE((ctx.r11.u32 + ctx.r9.u32), 128);")
assert site["candidate_generated_portme"].startswith(
    "// PORTME(0x84B46518)")

candidate = report["candidate_contract"]
assert candidate["applied_to_vendor"] is False
assert candidate["runtime_overridable"] is True
assert candidate["default_policy"] == "abort"
assert candidate["null_install_policy"] == "restore_abort_default"
assert candidate["accepted_cache_line_size"] == 128
assert candidate["line_alignment"] == "effective_address & ~127"
assert candidate["dcbf_existing_no_op_changed"] is False
assert candidate["ready_to_merge"] is False

observed = report["isolated_validation"]
assert observed["unrecognized_instruction_count_before"] == 172
assert observed["unrecognized_instruction_count_after"] == 171
assert observed["dcbst_omission_count_before"] == 1
assert observed["dcbst_omission_count_after"] == 0
assert observed["generated_cpp_count"] == 237
assert observed["syntax_checked_cpp_count"] == 237
assert observed["syntax_failure_count"] == 0
assert observed["default_hook_signal"] == "SIGABRT"
assert observed["invalid_line_size_signal"] == "SIGABRT"
assert observed["title_code_executed"] is False

policy = report["runtime_policy_boundary"]
assert policy["coherent_flat_host_ram_visibility_no_op_permitted"] is True
assert policy["gpu_dma_mmio_policy_currently_implemented"] is False
assert policy["alternate_dcbf_at_0x84B464F8_currently_hooked"] is False
assert len(report["portme"]) == 2
assert report["portme"][0].startswith("// PORTME(0x84B46518)")
assert report["portme"][1].startswith("// PORTME(0x84B464F8)")

patch = patch_path.read_text(encoding="utf-8")
assert "+    case PPC_INST_DCBST:" in patch
assert "PPC_DATA_CACHE_BLOCK_STORE" in patch
assert "PPCFailFastDataCacheStoreHook" in patch
assert "std::abort();" in patch
assert "effectiveAddress & ~(cacheLineSize - 1)" in patch
assert "PORTME(0x{:08X})" in patch

serialized = report_path.read_text(encoding="utf-8")
for forbidden in ('"raw_title_bytes":', '"decoded_image_bytes":',
                  '"generated_source_text":', '"executable_path":'):
    assert forbidden not in serialized, forbidden
assert report["sources"]["candidate_observation_embeds_title_bytes"] is False

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Outcome", "## Official PowerPC semantics", "## Pinned Xenia evidence",
    "## Candidate hook contract", "## Hook test", "## Isolated regeneration",
    "## Worked", "## Failed or unproved", "## Blocking",
    "aborts by default", "PPC_DATA_CACHE_BLOCK_STORE",
    "237 / 237", "alternate `dcbf` path", "coherent flat host RAM",
    "APF_DCBST_SEMANTICS_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

sha256sum --check --status "$temporary/before.sha256"
git -C "$vendor" diff --quiet HEAD --
git -C "$xenia" diff --quiet HEAD --
test "$(sha256sum "$xex" | cut -d' ' -f1)" = \
  '981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f'

echo 'APF_DCBST_SEMANTICS_VALIDATION_PASS site=0x84B46518 ea=RA0 line=128 hook=runtime default=SIGABRT invalid_size=SIGABRT omission_before=1 omission_after=0 tus=237/237 gpu_dma_mmio=PORTME dcbf=PORTME title_executed=no vendor_unchanged=yes'
