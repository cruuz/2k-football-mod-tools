#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

python3 -m py_compile tools/layout_semantics.py
temporary=$(mktemp -d /tmp/vc-layout-semantics.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 tools/layout_semantics.py \
  --json "$temporary/layout_semantics.json" \
  --tsv "$temporary/layout_semantics.tsv"

cmp "$temporary/layout_semantics.json" \
  reports/assets/cross_title_layout_semantics.json
cmp "$temporary/layout_semantics.tsv" \
  reports/assets/cross_title_layout_semantics.tsv

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(
    Path("reports/assets/cross_title_layout_semantics.json").read_text()
)
assert report["schema"] == "vc_cross_title_layout_semantics/v1"
assert report["summary"] == {
    "ambiguous_exact_name_key_count": 4,
    "ambiguous_same_index_bridge_count": 16,
    "apf_exposed_name_crc_match_count": 356,
    "apf_exposed_name_crc_tested_count": 1408,
    "apf_field_4c_equals_layout_name_count": 1217,
    "apf_field_4c_false_string_candidate_count": 11,
    "apf_field_4c_legacy_string_candidate_count": 1228,
    "apf_type0_record_count": 1228,
    "apf_type0_serialized_bit29_set_count": 0,
    "exact_whole_layout_sequence_count": 27,
    "exact_whole_layout_sequence_record_count": 120,
    "exact_whole_layout_sequence_type_counts": {"0": 79, "1": 14, "2": 27},
    "nfl_source_name_crc_match_count": 280,
    "nfl_source_name_crc_tested_count": 280,
    "sequence_type0_bridge_count": 79,
    "sequence_type0_default_one_bit_identical": 79,
    "sequence_type0_x_bit_identical": 79,
    "sequence_type0_y_bit_identical": 79,
    "sequence_type0_z_bit_identical": 75,
    "sequence_type1_bridge_count": 14,
    "sequence_type1_x_bit_identical": 14,
    "sequence_type1_y_bit_identical": 14,
    "shared_exact_name_key_count": 102,
    "unique_exact_name_bridge_count": 98,
    "unique_type0_bridge_count": 71,
    "unique_type0_default_one_bit_identical": 71,
    "unique_type0_x_bit_identical": 71,
    "unique_type0_y_bit_identical": 71,
    "unique_type0_z_bit_identical": 64,
}
assert len(report["shared_name_key_groups"]) == 102
assert len(report["unique_name_bridges"]) == 98
assert len(report["ambiguous_name_same_index_bridges"]) == 16
assert len(report["exact_whole_layout_sequences"]) == 27
assert len(report["exact_layout_sequence_bridges"]) == 120
assert len(report["unique_type0_transform_divergences"]) == 7
assert all("PORTME:" in item for item in report["portme"])
assert report["writer_safety"]["safe"] is False
assert report["main_menu_entries"]["state_entry_status"] == "not proved"
assert report["main_menu_entries"]["apf"]["outer_index"] == 1493
assert report["main_menu_entries"]["apf"]["inner_index"] == 53
assert report["main_menu_entries"]["apf"]["record_count"] == 7
assert report["main_menu_entries"]["nfl_container"]["outer_index"] == 8
assert report["main_menu_entries"]["nfl_container"]["inner_index"] == 17
assert report["main_menu_entries"]["nfl_navigation"]["inner_index"] == 19
assert report["field_semantics"]["inherited_default_one"]["semantic_name"] is None

apf_trace = Path("reports/assets/apf_layout_ghidra/layout_trace.txt").read_text()
apf_pseudo = Path(
    "reports/assets/apf_layout_ghidra/layout_focused_pseudo_c.c"
).read_text()
nfl_trace = Path("reports/assets/nfl2k5_layout_ghidra/layout_trace.txt").read_text()
nfl_pseudo = Path(
    "reports/assets/nfl2k5_layout_ghidra/layout_focused_pseudo_c.c"
).read_text()
nfl_disassembly = Path(
    "reports/assets/nfl2k5_layout_ghidra/layout_focused_disassembly.txt"
).read_text()

assert "Program MD5: 217eea6084c3d03f0f1143802b1f5636" in apf_trace
assert "0x846EED58 section=.text owner=0x846EED58:Function_846EED58" in apf_trace
assert "0x8475AD0C(0x8475AC48:Function_8475AC48,UNCONDITIONAL_CALL)" in apf_trace
assert "high_hits=0x84C77ED8:sth r10,0x48c6(r11)" in apf_trace
assert "low_hits=0x84CCB66C:ori r12,r12,0xd154" in apf_trace
assert "TIMELINE_CONSTANT 0x82000E94 raw=0x3C888889 float=0.0166666675" in apf_trace
assert "return uVar1 + 0x10;" in apf_pseudo
assert "(puVar1[1] == 2) && (puVar1[10] != 0)" in apf_pseudo
assert "(param_3 & 1) << 0x1d" in apf_pseudo
assert "Function_846EEC98(uVar1,0xffffffffaa0cdc21,0);" in apf_pseudo
assert "Function_846EEC98(uVar1,uVar3,1);" in apf_pseudo
assert "*(float *)(iVar3 + 4) = *(float *)(iVar3 + 4) - DAT_84d48c80;" in apf_pseudo
assert "*(float *)(param_2 + 0x5c) = (float)(longlong)*(int *)(iVar4 + 0x20) * DAT_82000e94;" in apf_pseudo
assert "void Function_846EDD30" in apf_pseudo
assert "void Function_846EDEA8" in apf_pseudo
assert "void Function_846ED638" in apf_pseudo
assert "void Function_846ED698" in apf_pseudo
assert "iVar1 = *(int *)(param_1 + 0x3c);" in apf_pseudo
assert "(**(code **)(iVar1 + 8))(&local_30);" in apf_pseudo

assert "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8" in nfl_trace
assert "0x00E8B1E0 section=.string_ refs=0x00515678(none,DATA)" in nfl_trace
assert "0x00E9D4A8 section=.string_ refs=0x00AD0154(none,DATA)" in nfl_trace
assert "param_1[0xc] = param_1[8] * param_4" in nfl_pseudo
assert "fVar1 = *(float *)(unaff_EBX + 0x10);" in nfl_pseudo
assert "fVar3 = *(float *)(unaff_EBX + 0x14);" in nfl_pseudo
assert "fVar5 = *(float *)(unaff_EBX + 0x18);" in nfl_pseudo
assert "else if (puVar1[10] != 0)" in nfl_pseudo
assert "local_2d0 = *param_3 + (float)puVar1[4];" in nfl_pseudo
assert "*(undefined4 *)(iVar1 + 0x38) = param_2;" in nfl_pseudo
assert "*(undefined4 *)(iVar4 + 0x10) = *param_2;" in nfl_pseudo
assert "return iVar1 + 0x10;" in nfl_pseudo
assert "void FUN_00143450" in nfl_pseudo
assert "piVar7 = *(int **)(param_1 + 0xc)" in nfl_pseudo
assert "void FUN_00143510" in nfl_pseudo
assert "for (piVar3 = *(int **)(param_1 + 0x10)" in nfl_pseudo
assert "void FUN_00143600" in nfl_pseudo
assert "void FUN_00143660" in nfl_pseudo
assert "0x001690B0  8B 41 14 8B 48 04 85 C9" in nfl_disassembly
assert "0x001691A0  68 60 91 16 00 BA 4C 41 59 54" in nfl_disassembly
assert "0x00143A93  8B 47 08  MOV EAX,dword ptr [EDI + 0x8]" in nfl_disassembly
assert "0x00143A9A  8B CB  MOV ECX,EBX" in nfl_disassembly
assert "0x00143A9C  FF D0  CALL EAX" in nfl_disassembly

xbe = Path("extracted/ESPN NFL 2K5 (USA)/default.xbe").read_bytes()
assert xbe[0x1590B0:0x159110] == bytes.fromhex(
    "8b41148b480485c974078d4c01038948048b400485c074498b480885c974078d"
    "5401078950088b0885c974068d4c01ff89088b480483e900741349741e8b4820"
    "85c974178d54011f895020eb0e8b482085c974078d4c011f8948208b0085c075"
)
assert xbe[0x1591A0:0x1591B5] == bytes.fromhex(
    "6860911600ba4c415954b978b9bd00e8eca4edffc3"
)
assert xbe[0xB19EC0:0xB19EDC] == "main_menu_sub\0".encode("utf-16le")
assert xbe[0xB2C188:0xB2C19C] == "main_navi\0".encode("utf-16le")
PY

if [[ ${LAYOUT_SEMANTICS_GHIDRA:-0} == 1 ]]; then
  mkdir -p "$temporary/apf-ghidra" "$temporary/nfl-ghidra"
  env HOME="$ROOT/tools/ghidra-home" \
    XDG_CONFIG_HOME="$ROOT/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$ROOT/ghidra_projects" apf2k8 \
      -process default.xex -noanalysis -readOnly \
      -scriptPath "$ROOT/tools/ghidra_scripts/apf" \
      -postScript ApfLayoutTrace.java "$temporary/apf-ghidra"
  env HOME="$ROOT/tools/ghidra-home" \
    XDG_CONFIG_HOME="$ROOT/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$ROOT/ghidra_projects" nfl2k5 \
      -process default.xbe -noanalysis -readOnly \
      -scriptPath "$ROOT/tools/ghidra_scripts" \
      -postScript Nfl2k5LayoutTrace.java "$temporary/nfl-ghidra"
  for name in layout_trace.txt layout_focused_pseudo_c.c layout_focused_disassembly.txt; do
    cmp "$temporary/apf-ghidra/$name" "reports/assets/apf_layout_ghidra/$name"
    cmp "$temporary/nfl-ghidra/$name" "reports/assets/nfl2k5_layout_ghidra/$name"
  done
  echo LAYOUT_SEMANTICS_GHIDRA_REGEN_PASS
fi

echo 'LAYOUT_SEMANTICS_VALIDATION_PASS keys=102 unique=98 ordinal=16 layouts=27/120 transform=71/71/64'
