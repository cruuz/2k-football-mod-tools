#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
decoded='reports/static_recomp/apf2k8_opcode_gap_decoded.tsv'
generated='build-static-recomp-apf/ppc-filtered'
vendor='tools/vendor/XenonRecomp'
ghidra='tools/vendor/ghidra_12.1.2_PUBLIC/Ghidra/Processors/PowerPC/data/languages'
differential='reports/static_recomp/apf2k8_frsqrte_differential.json'
constants='reports/static_recomp/apf2k8_frsqrte_constants.tsv'
report='reports/static_recomp/apf2k8_frsqrte_semantics.json'
sites='reports/static_recomp/apf2k8_frsqrte_sites.tsv'
vectors='reports/static_recomp/apf2k8_frsqrte_vectors.tsv'
patch='reports/static_recomp/apf2k8_frsqrte_candidate.patch'
doc='docs/research/apf_frsqrte_semantics.md'

for required in \
  "$xex" "$decoded" "$generated/ppc_recomp_shared.h" \
  "$vendor/XenonRecomp/recompiler.cpp" "$vendor/XenonUtils/ppc_context.h" \
  "$vendor/build/XenonUtils/libXenonUtils.a" \
  "$vendor/build/XenonAnalyse/libLibXenonAnalyse.a" \
  "$vendor/build/thirdparty/disasm/libdisasm.a" \
  "$vendor/build/thirdparty/fmt/libfmt.a" \
  "$vendor/build/thirdparty/xxHash/cmake_unofficial/libxxhash.a" \
  "$ghidra/ppc_instructions.sinc" "$differential" "$constants" \
  "$report" "$sites" "$vectors" "$patch" "$doc" \
  tools/apf_frsqrte_semantics.py tools/apf_frsqrte_xex_evidence.cpp \
  tests/apf_frsqrte_semantics_test.cpp; do
  test -f "$required"
done

test "$(sha256sum "$xex" | cut -d' ' -f1)" = \
  981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f
test "$(git -C "$vendor" rev-parse HEAD)" = \
  ddd128bcca99fe8bfbb99bea583c972351fa6ace

temporary=$(mktemp -d /tmp/apf-frsqrte-semantics.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"

python3 -m py_compile tools/apf_frsqrte_semantics.py

clang++-18 -std=c++20 -O2 -ffp-contract=off -Wall -Wextra -Werror \
  tests/apf_frsqrte_semantics_test.cpp -o "$temporary/frsqrte_test"
"$temporary/frsqrte_test" > "$temporary/differential.json"
cmp "$temporary/differential.json" "$differential"

c++ -std=c++20 -O2 -Wall -Wextra -Werror \
  -I"$vendor/XenonUtils" \
  tools/apf_frsqrte_xex_evidence.cpp \
  "$vendor/build/XenonUtils/libXenonUtils.a" \
  -o "$temporary/xex_evidence"
"$temporary/xex_evidence" "$xex" > "$temporary/constants.tsv"
cmp "$temporary/constants.tsv" "$constants"

python3 tools/apf_frsqrte_semantics.py \
  --xex "$xex" \
  --decoded-tsv "$decoded" \
  --generated-dir "$generated" \
  --vendor-root "$vendor" \
  --ghidra-powerpc "$ghidra" \
  --differential-json "$differential" \
  --constants-tsv "$constants" \
  --candidate-patch "$patch" \
  --json "$temporary/report.json" \
  --sites-tsv "$temporary/sites.tsv" \
  --vectors-tsv "$temporary/vectors.tsv"
cmp "$temporary/report.json" "$report"
cmp "$temporary/sites.tsv" "$sites"
cmp "$temporary/vectors.tsv" "$vectors"

python3 - "$report" "$sites" "$vectors" "$differential" "$patch" "$doc" <<'PY'
import csv
import json
from pathlib import Path
import sys

report_path, sites_path, vectors_path, differential_path, patch_path, doc_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_frsqrte_semantics/v1"
assert report["result"] == {
    "site_count": 28,
    "containing_function_count": 19,
    "all_record_bits_zero": True,
    "all_seeds_rounded_to_float32": True,
    "all_sites_have_two_newton_corrections": True,
    "containing_functions_with_direct_fpscr_access": 0,
    "pinned_xenia_ieee_value_model_supported_site_count": 28,
    "architecture_complete_site_count": 0,
    "dense_xenon_hardware_oracle_proved": False,
    "native_runtime_proved": False,
}
assert report["pinned_xenia"]["commit"] == \
    "6e5b8324f4101464de0f8c2334edb03cac8826c4"
assert report["pinned_xenia"]["ieee_x64_mismatches"] == 0
assert report["pinned_xenia"]["ieee_a64_mismatches"] == 0
assert report["pinned_xenia"]["non_ieee_subnormal_cross_backend_divergences"] == 16
assert report["candidate_patch"]["applied_to_vendor"] is False
assert report["candidate_patch"]["ready_to_merge"] is False
assert report["ghidra_boundary"]["estimate_bit_model"] is False
assert len(report["known_vectors"]) == 12
assert len(report["sites"]) == 28
assert all(row["record_bit"] == 0 for row in report["sites"])
assert all(row["newton_round_count"] == 2 for row in report["sites"])
assert all(row["portme"].startswith("// PORTME(0x") for row in report["sites"])

with sites_path.open("r", encoding="utf-8", newline="") as stream:
    sites = list(csv.DictReader(stream, dialect="excel-tab"))
with vectors_path.open("r", encoding="utf-8", newline="") as stream:
    vectors = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(sites) == 28
assert len(vectors) == 12
assert len({row["address"] for row in sites}) == 28
assert len({row["function_start"] for row in sites}) == 19
assert all(row["record_bit"] == "0" and row["newton_round_count"] == "2"
           for row in sites)
assert all(row["candidate_ieee_match"] == "True" for row in vectors)

differential = json.loads(differential_path.read_text(encoding="utf-8"))
assert differential["source_differential_cases"] == 2065536
assert differential["refinement_corpus_count"] == 16646144
assert differential["two_round_seed_path_mismatch_count"] == 10986089
assert differential["two_round_seed_path_max_ulp"] == 50
assert differential["maximum_raw_relative_error"] <= 1.0 / 32.0

patch = patch_path.read_text(encoding="utf-8")
assert "+    case PPC_INST_FRSQRTE:" in patch
assert "PPC_FRSQRTE_XENIA_6E5B832_VALUE" in patch
assert "false);" in patch
assert "FPSCR" in patch and "enabled exceptions" in patch

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Outcome", "## Worked", "## Failed or unproved", "## Blocking",
    "10,986,089", "50 ULP", "2,065,536", "16,646,144",
    "architecture-complete", "APF_FRSQRTE_SEMANTICS_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

vendor_recompiler_before=$(sha256sum "$vendor/XenonRecomp/recompiler.cpp" | cut -d' ' -f1)
vendor_context_before=$(sha256sum "$vendor/XenonUtils/ppc_context.h" | cut -d' ' -f1)
baseline_before=$(sha256sum "$generated/ppc_recomp.1.cpp" | cut -d' ' -f1)

(
  cd "$vendor"
  git apply --check "$root/$patch"
)

# Exercise the candidate only in a throwaway copy. The two copied source
# directories are sufficient; all unchanged libraries/includes remain pinned.
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
ln -s "$root/reports/static_recomp/apf2k8_xenon_switch_tables_filtered.toml" \
  "$temporary/switches.toml"
mkdir "$temporary/out"
python3 - "$temporary/config.toml" "$root" <<'PY'
from pathlib import Path
import sys

source = Path(
    sys.argv[2], "reports/static_recomp/apf2k8_xenonrecomp_filtered_probe.toml"
).read_text(encoding="utf-8")
source = source.replace(
    "../../extracted/All-Pro Football 2K8 (USA)/default.xex", "default.xex"
)
source = source.replace("../../build-static-recomp-apf/ppc-filtered", "out")
source = source.replace("apf2k8_xenon_switch_tables_filtered.toml", "switches.toml")
Path(sys.argv[1]).write_text(source, encoding="utf-8")
PY

"$temporary/XenonRecompPatched" \
  "$temporary/config.toml" "$temporary/XenonUtils/ppc_context.h" \
  > "$temporary/patched.log" 2>&1
test "$(tail -1 "$temporary/patched.log")" = 'Recompiling functions... 100%'

python3 - "$temporary/patched.log" "$temporary/out" "$sites" <<'PY'
from collections import Counter
import csv
from pathlib import Path
import re
import sys

log = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
pattern = re.compile(r"^Unrecognized instruction at 0x[0-9A-F]+: (\w+)$")
counts = Counter(match.group(1) for line in log if (match := pattern.match(line)))
assert counts == {
    "vsel128": 54, "vpkswss": 51, "vandc": 16, "stfsu": 8,
    "vaddsws": 6, "mulhdu": 5, "vsrab": 1, "vrfip": 1,
    "vsubuwm": 1, "dcbst": 1,
}, counts

output = Path(sys.argv[2])
cpp = list(output.glob("ppc_recomp.*.cpp"))
assert len(cpp) == 236
text = "".join(path.read_text(encoding="utf-8") for path in cpp)
assert text.count("PPC_FRSQRTE_XENIA_6E5B832_VALUE") == 28
addresses = re.findall(r"PORTME\((0x[0-9A-F]{8})\): value matches Xenia", text)
assert len(addresses) == 28
with Path(sys.argv[3]).open("r", encoding="utf-8", newline="") as stream:
    expected = {row["address"] for row in csv.DictReader(stream, dialect="excel-tab")}
assert set(addresses) == expected
assert "Unrecognized instruction" not in "\n".join(
    line for line in log if line.endswith(": frsqrte")
)
PY

mapfile -t candidate_units < <(
  rg -l 'PPC_FRSQRTE_XENIA_6E5B832_VALUE' \
    "$temporary/out" --glob 'ppc_recomp.*.cpp' | sort -u
)
test "${#candidate_units[@]}" -ge 10
for source in "${candidate_units[@]}"; do
  clang++-18 -std=c++20 -O0 -fsyntax-only \
    -I"$temporary/out" \
    -I"$root/$vendor/thirdparty/simde" \
    "$source"
done

test "$(sha256sum "$vendor/XenonRecomp/recompiler.cpp" | cut -d' ' -f1)" = \
  "$vendor_recompiler_before"
test "$(sha256sum "$vendor/XenonUtils/ppc_context.h" | cut -d' ' -f1)" = \
  "$vendor_context_before"
test "$(sha256sum "$generated/ppc_recomp.1.cpp" | cut -d' ' -f1)" = \
  "$baseline_before"

echo 'APF_FRSQRTE_SEMANTICS_VALIDATION_PASS sites=28 functions=19 vectors=12 differential=2065536 refinement=16646144 xenia_ieee=yes hardware_dense=no fpscr=no vendor_unchanged=yes'
