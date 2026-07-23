#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
xex_report='reports/headers/apf2k8_xex_report.json'
ghidra_report='reports/headers/apf2k8_ghidra_program.json'
raw='reports/static_recomp/apf2k8_xenon_switch_tables.toml'
filtered='reports/static_recomp/apf2k8_xenon_switch_tables_filtered.toml'
config='reports/static_recomp/apf2k8_xenonrecomp_filtered_probe.toml'
log='reports/static_recomp/apf2k8_xenonrecomp_filtered.log'
generated='build-static-recomp-apf/ppc-filtered'
vendor='tools/vendor/XenonRecomp'
report='reports/static_recomp/apf2k8_static_recomp_probe.json'
doc='docs/research/apf_static_recomp_probe.md'

for required in \
    "$xex" "$xex_report" "$ghidra_report" "$raw" "$filtered" "$config" \
    "$log" "$report" "$doc" tools/apf_static_recomp_probe.py \
    "$vendor/README.md" "$vendor/build/XenonRecomp/XenonRecomp" \
    "$generated/ppc_func_mapping.cpp" "$generated/ppc_recomp_shared.h"; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-static-recomp-probe.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_static_recomp_probe.py

python3 tools/apf_static_recomp_probe.py \
  --xex "$xex" \
  --xex-report "$xex_report" \
  --ghidra-report "$ghidra_report" \
  --raw-switches "$raw" \
  --filtered-switches "$filtered" \
  --config "$config" \
  --log "$log" \
  --output-dir "$generated" \
  --vendor-root "$vendor" \
  --xenon-utils "$vendor/XenonUtils" \
  --simde "$vendor/thirdparty/simde" \
  --json "$temporary/report.json"

cmp "$temporary/report.json" "$report"

python3 - "$report" "$doc" <<'PY'
import json
from pathlib import Path
import sys

report_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_static_recomp_probe/v1"
assert report["result"] == {
    "xenon_analyse_completed": True,
    "xenon_recomp_completed": True,
    "generated_cpp_syntax_sample_passed": True,
    "generated_code_semantically_complete": False,
    "title_runtime_exists": False,
    "native_gameplay_boot_proved": False,
    "turnkey_static_recomp_port": False,
}
switches = report["switch_analysis"]
assert switches["raw_switch_count"] == 992
assert switches["raw_label_count"] == 734076
assert switches["pathological_32767_label_table_count"] == 22
assert switches["filtered_switch_count"] == 970
assert switches["filtered_label_count"] == 13202
assert switches["filtered_max_label_count"] == 229
assert switches["remaining_out_of_function_error_count"] == 3337
assert switches["remaining_out_of_function_switch_count"] == 196
assert switches["missing_switch_sites"] == ["0x84BC849C"]

gaps = report["instruction_gaps"]
assert gaps["site_count"] == 172
assert gaps["unique_mnemonic_count"] == 11
assert gaps["mnemonic_counts"] == {
    "vsel128": 54, "vpkswss": 51, "frsqrte": 28, "vandc": 16,
    "stfsu": 8, "vaddsws": 6, "mulhdu": 5, "vsrab": 1,
    "vrfip": 1, "vsubuwm": 1, "dcbst": 1,
}

output = report["generated_output"]
assert output["file_count"] == 240
assert output["cpp_file_count"] == 237
assert output["total_file_bytes"] == 130462146
assert output["function_mapping_count"] == 60731
assert output["function_implementation_count"] == 60397
assert output["ghidra_recovered_text_function_count"] == 21347
assert output["generated_to_ghidra_function_ratio"] == 2.829297
assert len(output["syntax_checks"]) == 2
assert all(row["return_code"] == 0 and row["stderr"] == ""
           for row in output["syntax_checks"])

runtime = report["runtime_gap"]
assert runtime["xex_import_count"] == 347
assert runtime["required"][1] == "implement 11 missing PPC/VMX mnemonics at 172 sites"
assert len(report["portme"]) == 3
assert all("PORTME" in row for row in report["portme"])

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking",
    "3,337", "cross-function switch violations", "172 instruction sites",
    "2.83 times", "not a 72-hour route", "11 missing PPC/VMX mnemonics",
    "APF_STATIC_RECOMP_PROBE_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

echo 'APF_STATIC_RECOMP_PROBE_VALIDATION_PASS switches=970 switch_errors=3337 unsupported_sites=172 unsupported_mnemonics=11 cpp=237 runtime=no'
