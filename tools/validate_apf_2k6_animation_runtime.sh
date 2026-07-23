#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xex='extracted/All-Pro Football 2K8 (USA)/default.xex'
lineage='reports/cut_content/apf_nfl_lineage/apf_2k6_animation_lineage.json'
mocap='reports/assets/apf_mocap_inventory.json'
report='reports/cut_content/apf_nfl_lineage/apf_2k6_animation_runtime.json'
table='reports/cut_content/apf_nfl_lineage/apf_2k6_animation_runtime_mappings.tsv'
ghidra_dir='reports/cut_content/apf_nfl_lineage/apf_2k6_animation_runtime_ghidra'
trace="$ghidra_dir/apf_2k6_animation_runtime_ghidra_trace.txt"
pseudo="$ghidra_dir/apf_2k6_animation_runtime_ghidra_pseudo_c.c"
doc='docs/research/apf_2k6_animation_runtime.md'

for required in \
    "$xex" "$lineage" "$mocap" "$report" "$table" "$trace" "$pseudo" "$doc" \
    tools/apf_2k6_animation_runtime.py \
    tools/ghidra_scripts/apf/Apf2k6AnimationRuntimeTrace.java \
    tools/xex_extract_pe.cpp; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/apf-2k6-animation-runtime.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_2k6_animation_runtime.py

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$temporary/xex_extract_pe"

"$temporary/xex_extract_pe" "$xex" "$temporary/apf.pe" | \
  grep -F 'blocks=642 chunks=1648 lzx_bytes=37717546 image_bytes=54001664 window_size=32768'

generate_report() {
  local evidence_trace=$1
  local evidence_pseudo=$2
  local prefix=$3
  python3 tools/apf_2k6_animation_runtime.py \
    --apf-pe "$temporary/apf.pe" \
    --lineage "$lineage" \
    --mocap-report "$mocap" \
    --ghidra-trace "$evidence_trace" \
    --ghidra-pseudo "$evidence_pseudo" \
    --json "$prefix.json" \
    --tsv "$prefix.tsv"
}

generate_report "$trace" "$pseudo" "$temporary/normal"
cmp "$temporary/normal.json" "$report"
cmp "$temporary/normal.tsv" "$table"

python3 - "$report" "$table" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, table_path, trace_path, pseudo_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "apf2k8_2k6_animation_runtime/v1"
assert report["result"] == {
    "all_two_k6_mappings_have_concrete_motion_roots": True,
    "at_least_one_two_k6_payload_has_code_owned_runtime_config": True,
    "definition_table_record_count": 5884,
    "definition_table_record_size": 44,
    "formal_nfl_2k6_product_identity_proved": False,
    "name_definition_table_classic_materialization_count": 0,
    "name_definition_table_direct_code_reference_count": 0,
    "runtime_consumption_of_every_identifier_proved": False,
    "runtime_execution_observed": False,
    "selector_array_count": 54,
    "selector_array_record_count": 540,
    "two_k6_definition_record_count": 309,
    "two_k6_name_field_mapping_count": 597,
    "two_k6_selector_linked_definition_count": 106,
    "two_k6_selector_linked_identifier_count": 149,
    "two_k6_selector_target_group_count": 49,
    "two_k6_unique_animation_filename_count": 225,
    "two_k6_unique_identifier_count": 519,
    "two_k6_unique_single_mocap_root_count": 597,
    "worked_movement_config_reached_by_recovered_direct_lookup_calls": False,
}
assert report["definition_table"]["first"] == "0x84D75500"
assert report["definition_table"]["after_last"] == "0x84DB4850"
assert report["definition_table"]["sha256"] == (
    "40f063e925420c21076ccedc868524f0c83ea7f0eede25624e0b7606cc6f4497"
)
assert len(report["aggregates"]) == 75
assert len(report["mappings"]) == 597
assert len(report["selector_array_path"]["arrays"]) == 54
assert len(report["selector_array_path"]["two_k6_links"]) == 49
assert report["master_runtime_lookup_path"]["recovered_direct_call_selector_domain"] == list(range(8))
assert report["portme"] == [
    "// PORTME(0x84D75500): recover any indirect/non-classic owner before calling the 5,884-record name table live.",
    "// PORTME(0x848AEB78): translate the shared-save wrapper and full selector-array initializer to compilable native source.",
    "// PORTME(0x848FDC0C): recover missing caller boundaries and prove the concrete selector values reaching every 2K6 config.",
    "// PORTME: require an exact formal product/build identifier before naming the retail executable a cancelled NFL 2K6 build.",
]

with table_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 597
assert [int(row["mapping_index"]) for row in rows] == list(range(597))
first = next(row for row in rows if row["name"] == "ANM_BLOCK_2K6_PASS_LOW_B(0)")
assert first["record_address"] == "0x84D7E6C0"
assert first["animation_filename"] == "cb300_fa_ply_01.ani"
assert first["single_mocap_root_address"] == "0x8409BB00"
assert first["variant_aggregate_address"] == "0x8409C820"
assert first["selector_record_addresses"] == "0x84DBC8AC"
movement = next(row for row in rows if row["name"] == "ANM_MOVEMENT_2K6_LM_READY_WALK_B")
assert movement["record_address"] == "0x84D9109C"
assert movement["animation_filename"] == "mr115_fa_ply_02.ani"
assert movement["single_mocap_root_address"] == "0x834DD0A8"

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for marker in (
    "CODE_REFERENCE_COUNT 0",
    "CLASSIC_MATERIALIZATION_COUNT 0",
    "0x848AF59C->0x84DBC768",
    "0x848EA3EC->0x84DEB650",
    "RAW_SPAN 0x848AEB78..0x848AEC10",
    "0x848FDC04 raw=0x38800000 instruction=li r4,0x0",
    "0x848FDF78 raw=0x38800001 instruction=li r4,0x1",
):
    assert marker in trace, marker
for marker in (
    "APF_AnimationSelectorArrayInit_Body",
    "param_1 = param_1 + 9",
    "Function_848AEB78(0xffffffff84dbc768,0x1e)",
    "(&PTR_PTR_84deb650)[uVar1 * 0xb + param_2]",
    "// PORTME(0x848AEB78)",
    "// PORTME(0x848FDC0C/0x848FDF80)",
):
    assert marker in pseudo, marker

expected_sources = {
    "lineage_report": Path("reports/cut_content/apf_nfl_lineage/apf_2k6_animation_lineage.json"),
    "mocap_report": Path("reports/assets/apf_mocap_inventory.json"),
    "ghidra_trace": trace_path,
    "ghidra_pseudo_c": pseudo_path,
    "generator": Path("tools/apf_2k6_animation_runtime.py"),
}
for key, path in expected_sources.items():
    data = path.read_bytes()
    source = report["sources"][key]
    assert source["size"] == len(data)
    assert source["sha256"] == hashlib.sha256(data).hexdigest()
assert report["sources"]["apf_memory_image"]["size"] == 54001664
assert report["sources"]["apf_memory_image"]["sha256"] == (
    "cde5b9224c6f999060df7372eea1bfd6463d63b4e59a87b2801826f76d52b1cf"
)

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking",
    "597 roots", "149 of the 519", "selectors only in `0..7`",
    "formal product/build identifier", "APF_2K6_ANIMATION_RUNTIME_VALIDATION_PASS",
):
    assert phrase in doc, phrase
PY

mode=normal
if [[ "${APF_2K6_ANIMATION_RUNTIME_GHIDRA:-0}" == 1 ]]; then
  ghidra='tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless'
  test -x "$ghidra"
  mkdir -p "$temporary/ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript Apf2k6AnimationRuntimeTrace.java "$temporary/ghidra"

  cmp "$trace" "$temporary/ghidra/apf_2k6_animation_runtime_ghidra_trace.txt"
  cmp "$pseudo" "$temporary/ghidra/apf_2k6_animation_runtime_ghidra_pseudo_c.c"
  generate_report \
    "$temporary/ghidra/apf_2k6_animation_runtime_ghidra_trace.txt" \
    "$temporary/ghidra/apf_2k6_animation_runtime_ghidra_pseudo_c.c" \
    "$temporary/full"
  cmp "$temporary/full.json" "$report"
  cmp "$temporary/full.tsv" "$table"
  mode=full
fi

echo "APF_2K6_ANIMATION_RUNTIME_VALIDATION_PASS mode=$mode definitions=309 mappings=597 roots=597 selector_arrays=54 selector_groups=49 selector_identifiers=149 formal_product_identity=unproved"
