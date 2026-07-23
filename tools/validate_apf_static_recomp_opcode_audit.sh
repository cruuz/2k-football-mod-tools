#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
probe='reports/static_recomp/apf2k8_static_recomp_probe.json'
decoded='reports/static_recomp/apf2k8_opcode_gap_decoded.tsv'
report='reports/static_recomp/apf2k8_opcode_gap_audit.json'
sites='reports/static_recomp/apf2k8_opcode_gap_sites.tsv'
mnemonics='reports/static_recomp/apf2k8_opcode_gap_mnemonics.tsv'
patch='reports/static_recomp/apf2k8_opcode_gap_candidate.patch'
doc='docs/research/apf_static_recomp_opcode_audit.md'
generated='build-static-recomp-apf/ppc-filtered'
vendor='tools/vendor/XenonRecomp'
ghidra_languages='tools/vendor/ghidra_12.1.2_PUBLIC/Ghidra/Processors/PowerPC/data/languages'

for required in \
  "$xex" "$probe" "$decoded" "$report" "$sites" "$mnemonics" "$patch" \
  "$doc" tools/apf_static_recomp_opcode_audit.py \
  tools/apf_xex_opcode_site_dump.cpp \
  "$generated/ppc_recomp_shared.h" "$vendor/XenonRecomp/recompiler.cpp" \
  "$vendor/XenonUtils/ppc_context.h" \
  "$vendor/build/XenonUtils/libXenonUtils.a" \
  "$vendor/build/XenonAnalyse/libLibXenonAnalyse.a" \
  "$vendor/build/thirdparty/disasm/libdisasm.a" \
  "$vendor/build/thirdparty/fmt/libfmt.a" \
  "$vendor/build/thirdparty/xxHash/cmake_unofficial/libxxhash.a" \
  "$ghidra_languages/altivec.sinc" \
  "$ghidra_languages/ppc_instructions.sinc" \
  "$ghidra_languages/ppc_embedded.sinc"; do
  test -f "$required"
done

test "$(sha256sum "$xex" | cut -d' ' -f1)" = \
  981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f
test "$(git -C "$vendor" rev-parse HEAD)" = \
  ddd128bcca99fe8bfbb99bea583c972351fa6ace

temporary=$(mktemp -d /tmp/apf-static-recomp-opcodes.XXXXXX)
trap 'rm -rf "$temporary"' EXIT
export PYTHONPYCACHEPREFIX="$temporary/pycache"
python3 -m py_compile tools/apf_static_recomp_opcode_audit.py

c++ -std=c++20 -O2 -Wall -Wextra -Werror -Wno-unused-function \
  -I"$vendor/XenonUtils" \
  -I"$vendor/thirdparty/disasm" \
  tools/apf_xex_opcode_site_dump.cpp \
  "$vendor/build/XenonUtils/libXenonUtils.a" \
  "$vendor/build/thirdparty/disasm/libdisasm.a" \
  -o "$temporary/apf_xex_opcode_site_dump"

mapfile -t addresses < <(python3 - "$probe" <<'PY'
import json
from pathlib import Path
import sys
for row in json.loads(Path(sys.argv[1]).read_text())["instruction_gaps"]["sites"]:
    print(row["address"])
PY
)
test "${#addresses[@]}" -eq 172
"$temporary/apf_xex_opcode_site_dump" "$xex" "${addresses[@]}" \
  > "$temporary/decoded.tsv"
cmp "$temporary/decoded.tsv" "$decoded"

python3 tools/apf_static_recomp_opcode_audit.py \
  --xex "$xex" \
  --probe-json "$probe" \
  --decoded-tsv "$decoded" \
  --generated-dir "$generated" \
  --vendor-root "$vendor" \
  --ghidra-powerpc "$ghidra_languages" \
  --candidate-patch "$patch" \
  --json "$temporary/audit.json" \
  --sites-tsv "$temporary/sites.tsv" \
  --mnemonics-tsv "$temporary/mnemonics.tsv"
cmp "$temporary/audit.json" "$report"
cmp "$temporary/sites.tsv" "$sites"
cmp "$temporary/mnemonics.tsv" "$mnemonics"

python3 - "$report" "$decoded" "$sites" "$mnemonics" "$patch" "$doc" <<'PY'
import csv
from collections import Counter
import json
from pathlib import Path
import sys

report_path, decoded_path, sites_path, mnemonics_path, patch_path, doc_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_static_recomp_opcode_audit/v1"
assert report["result"] == {
    "site_count": 172,
    "mnemonic_count": 11,
    "all_sites_accounted": True,
    "decoder_false_positive_count": 0,
    "true_missing_recompiler_case_count": 11,
    "high_semantic_risk_site_count": 171,
    "cache_policy_site_count": 1,
    "candidate_patch_data_state_site_count": 143,
    "candidate_patch_architecture_complete": False,
    "native_runtime_proved": False,
}

expected = {
    "vsel128": 54, "vpkswss": 51, "frsqrte": 28, "vandc": 16,
    "stfsu": 8, "vaddsws": 6, "mulhdu": 5, "vsrab": 1,
    "vrfip": 1, "vsubuwm": 1, "dcbst": 1,
}
assert {row["mnemonic"]: row["site_count"] for row in report["mnemonics"]} == expected
assert len(report["sites"]) == 172
assert Counter(row["mnemonic"] for row in report["sites"]) == Counter(expected)
assert all(row["boot_reachability"] == "not_proved_by_static_context"
           for row in report["sites"])
assert all(row["portme"].startswith("// PORTME:") for row in report["sites"])

vsel = report["vsel128_finding"]
assert vsel == {
    "valid_xenon_vmx128_instruction": True,
    "decoder_naming_quirk": False,
    "site_count": 54,
    "mask_operand_equals_destination_count": 54,
    "site_count_using_any_register_above_v31": 51,
    "site_count_with_destination_above_v31": 36,
    "finding": vsel["finding"],
}
assert "old VD" in vsel["finding"]
assert report["vscr_boundary"]["apf_mfvscr_mtvscr_instruction_count"] == 0
assert report["vscr_boundary"]["affected_site_count"] == 57
assert report["frsqrte_context"]["destination_reused_within_next_eight_instructions"] == 26

candidate = report["candidate_patch_validation"]
assert candidate["vendored_source_modified"] is False
assert candidate["full_recompile_completed"] is True
assert candidate["unsupported_site_count_before"] == 172
assert candidate["unsupported_site_count_after"] == 29
assert candidate["restored_data_state_site_count"] == 143
assert candidate["remaining_mnemonic_counts"] == {"frsqrte": 28, "dcbst": 1}

for path, count in ((decoded_path, 172), (sites_path, 172), (mnemonics_path, 11)):
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream, dialect="excel-tab"))
    assert len(rows) == count
with decoded_path.open("r", encoding="utf-8", newline="") as stream:
    decoded = list(csv.DictReader(stream, dialect="excel-tab"))
assert Counter(row["mnemonic"] for row in decoded) == Counter(expected)
assert all(row["operand0"] == row["operand3"]
           for row in decoded if row["mnemonic"] == "vsel128")

patch = patch_path.read_text(encoding="utf-8")
for case in (
    "PPC_INST_MULHDU", "PPC_INST_STFSU", "PPC_INST_VADDSWS",
    "PPC_INST_VANDC", "PPC_INST_VPKSWSS", "PPC_INST_VRFIP",
    "PPC_INST_VSEL128", "PPC_INST_VSRAB", "PPC_INST_VSUBUWM",
):
    assert f"+    case {case}:" in patch
assert "PPC_INST_FRSQRTE" not in patch
assert "PPC_INST_DCBST" not in patch
assert patch.count("PORTME: update sticky VSCR.SAT") == 2

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking",
    "not a naming accident", "Fifty-one sites", "143 sites",
    "exactly 29", "VSCR.SAT", "0x84B46518",
    "APF_STATIC_RECOMP_OPCODE_AUDIT_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

vendor_source_before=$(sha256sum "$vendor/XenonRecomp/recompiler.cpp" | cut -d' ' -f1)
(
  cd "$vendor"
  git apply --check "$root/$patch"
)

# Build and exercise the candidate in a throwaway copy. This must never touch
# the pinned vendor tree or the generated baseline corpus.
cp -a "$vendor/XenonRecomp" "$temporary/XenonRecomp"
(
  cd "$temporary"
  git apply "$root/$patch"
)

includes=(
  -I"$temporary/XenonRecomp"
  -I"$root/$vendor/XenonAnalyse"
  -I"$root/$vendor/XenonUtils"
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
  "$temporary/config.toml" "$root/$vendor/XenonUtils/ppc_context.h" \
  > "$temporary/patched.log" 2>&1
test "$(tail -1 "$temporary/patched.log")" = 'Recompiling functions... 100%'

python3 - "$temporary/patched.log" "$temporary/out" <<'PY'
from collections import Counter
from pathlib import Path
import re
import sys

log = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
pattern = re.compile(r"^Unrecognized instruction at 0x[0-9A-F]+: (\w+)$")
counts = Counter(match.group(1) for line in log if (match := pattern.match(line)))
assert counts == {"frsqrte": 28, "dcbst": 1}, counts
output = Path(sys.argv[2])
files = list(output.iterdir())
assert len(files) == 240
cpp = list(output.glob("*.cpp"))
assert len(cpp) == 237
text = "".join(path.read_text(encoding="utf-8") for path in cpp)
for mnemonic, count in {
    "vsel128": 54, "vpkswss": 51, "vandc": 16, "stfsu": 8,
    "vaddsws": 6, "mulhdu": 5, "vsrab": 1, "vrfip": 1,
    "vsubuwm": 1,
}.items():
    assert len(re.findall(rf"^\s*// {mnemonic}(?:\s|$)", text, re.MULTILINE)) == count
assert "static_cast<unsigned __int128>" in text
assert "simde_mm_packs_epi32" in text
assert "SIMDE_MM_FROUND_TO_POS_INF" in text
PY

largest=$(find "$temporary/out" -maxdepth 1 -name '*.cpp' -printf '%s\t%p\n' \
  | sort -nr | head -1 | cut -f2-)
mapfile -t patched_units < <(
  rg -l '^\s*// (vsel128|vpkswss|vandc|stfsu|vaddsws|mulhdu|vsrab|vrfip|vsubuwm)(\s|$)' \
    "$temporary/out" --glob 'ppc_recomp.*.cpp' | sort -u
)
test "${#patched_units[@]}" -ge 10
syntax_units=("$temporary/out/ppc_recomp.0.cpp" "$largest" "${patched_units[@]}")
mapfile -t syntax_units < <(printf '%s\n' "${syntax_units[@]}" | sort -u)
for source in "${syntax_units[@]}"; do
  clang++-18 -std=c++20 -O0 -fsyntax-only \
    -I"$temporary/out" \
    -I"$root/$vendor/XenonUtils" \
    -I"$root/$vendor/thirdparty/simde" \
    "$source"
done

test "$(sha256sum "$vendor/XenonRecomp/recompiler.cpp" | cut -d' ' -f1)" = \
  "$vendor_source_before"

echo 'APF_STATIC_RECOMP_OPCODE_AUDIT_VALIDATION_PASS sites=172 mnemonics=11 aliases=70 saturating=57 exact_state=16 estimate=28 cache=1 candidate_patch=143 remaining=29 vendor_unchanged=yes runtime=no'
