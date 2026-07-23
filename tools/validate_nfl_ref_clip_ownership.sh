#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
motion='reports/assets/nfl2k5_motion_inventory.json'
sampler='reports/assets/nfl_motion_sampler_inventory.json'
sampler_tsv='reports/assets/nfl_motion_sampler_roots.tsv'
pose='reports/assets/nfl_pose_matrix_apply.json'
pool='reports/assets/nfl_motion_object_pools.json'
bone='reports/assets/nfl_bone_binding.json'
report='reports/assets/nfl_ref_clip_ownership.json'
selectors='reports/assets/nfl_ref_clip_ownership_selectors.tsv'
path_tsv='reports/assets/nfl_ref_clip_ownership_path.tsv'
trace='reports/assets/nfl_ref_clip_ownership_ghidra/nfl_ref_clip_ownership_trace.txt'
pseudo='reports/assets/nfl_ref_clip_ownership_ghidra/nfl_ref_clip_ownership_focused_pseudo_c.c'
doc='docs/research/nfl_ref_clip_ownership.md'

for required in \
  "$index" "$xbe" "$xbe_header" "$motion" "$sampler" "$sampler_tsv" \
  "$pose" "$pool" "$bone" "$report" "$selectors" "$path_tsv" \
  "$trace" "$pseudo" "$doc" \
  tools/nfl_outer.py tools/nfl_ref_clip_ownership.py \
  tools/ghidra_scripts/NflRefClipOwnershipTrace.java; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_ref_clip_ownership.py
temporary=$(mktemp -d /tmp/nfl-ref-clip-ownership.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_ref_clip_ownership.py "$index" \
  --motion-inventory "$motion" \
  --sampler-report "$sampler" \
  --sampler-tsv "$sampler_tsv" \
  --pose-report "$pose" \
  --pool-report "$pool" \
  --bone-report "$bone" \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --json "$temporary/report.json" \
  --selectors-tsv "$temporary/selectors.tsv" \
  --path-tsv "$temporary/path.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/selectors.tsv" "$selectors"
cmp "$temporary/path.tsv" "$path_tsv"
test "$(wc -l < "$selectors")" -eq 27
test "$(wc -l < "$path_tsv")" -eq 11

test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  17c728da2b25099a9ed1271e4476c9f8ff1ce25daaaff6af2a1ff70b517fc8d3
test "$(sha256sum "$selectors" | cut -d' ' -f1)" = \
  4a98310218fa08ce7af99ec1691d0bbc08a2b31091d69af0d90dea7c677356d0
test "$(sha256sum "$path_tsv" | cut -d' ' -f1)" = \
  5cb2b27c6f39c9f8c1caffe0ff0b14ec7d29279f95fc6d2a1bd65224f7130ba2
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  efd334611571a1b1cd167d1435aab9b869b2428e95ae6b2c71b4c1a32a8b52ca
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  8259b85d74f97e5a8122a8c827580e125f4f86c096f3cf981648c18821698943
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  4ac9f6cfbc0f2346a3e089234e21b367284d3ce4890270b5958800eca8c94429

python3 - "$report" "$selectors" "$path_tsv" "$xbe" "$xbe_header" "$trace" "$pseudo" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, selectors_path, path_path, xbe_path, header_path, trace_path, pseudo_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_ref_clip_ownership/v1"
clip = report["selected_clip"]
assert clip == {
    "chunk_index": 27,
    "decoded_length": 4400,
    "decoded_sha256": "75b67ce8f338943a8cc6bdc46718f61c7c2d9c4945d186983796a090aa31363f",
    "duration_raw": "0x403ddddf",
    "duration_seconds": 2.96666694,
    "event_count": 3,
    "exact_inventory_match_count": 1,
    "flags": 2,
    "frame_count": 46,
    "name": "ANM_REF_PENALTY_DELAY_OF_GAME_R",
    "outer_id": "0xda37aa9d",
    "outer_index": 3107,
    "packed_quaternion_dwords_per_frame": 21,
    "quaternion_bytes": 3864,
    "sample_rate_hz": 15,
    "selector_index": 4,
    "selector_name_pointer_va": "0x00513f5c",
    "selector_name_string_va": "0x00e87fb8",
    "selector_row_va": "0x00513f58",
    "selector_side": "right",
    "slot_index": 27,
    "slot_offset": 304128,
    "slot_size": 11264,
    "trajectory_bytes": 368,
    "trajectory_stride": 8,
    "wrapper_size": 32,
}
assert report["fixed_slot_bank"] == {
    "all_resources_kind": "SMCD",
    "all_slot_offsets_equal_index_times_slot_size": True,
    "all_slot_tail_padding_zero": True,
    "all_slots_dense": True,
    "all_wrapper_bodies_match_inventory": True,
    "outer_id": "0xda37aa9d",
    "outer_index": 3107,
    "outer_size": 405504,
    "slot_count": 36,
    "slot_size": 11264,
    "slot_tail_padding_bytes": 143440,
    "target_slot_tail_padding_bytes": 6832,
}
assert report["selector_table"] == {
    "all_nonempty_names_have_one_exact_smcd_match": True,
    "all_nonempty_names_resolve_to_outer_3107": True,
    "base_va": "0x00513f28",
    "end_exclusive_va": "0x00514060",
    "left_pointer_offset": 0,
    "nonempty_name_pointer_count": 50,
    "opaque_pointer_offset": 8,
    "reused_name_pointer_count": 12,
    "right_pointer_offset": 4,
    "row_count": 26,
    "row_stride": 12,
    "unique_name_count": 32,
}
runtime = report["runtime_ownership"]
assert runtime["namespace_name"] == "Referee"
assert runtime["namespace_string_va"] == "0x00e887b0"
assert runtime["smcd_fourcc_immediate"] == "0x44434d53"
assert runtime["referee_scene_name"] == "referee"
assert runtime["referee_shape_names"] == ["ref_low", "ref_high"]
assert runtime["gameplay_actor_pool_head_va"] == "0x00e60274"
assert runtime["gameplay_actor_pool_max_count"] == 7
assert runtime["channel_map_va"] == "0x0051d010"
assert runtime["enabled_channel_count"] == 21
assert runtime["specific_pool_record_instance_link_proved"] is False
type4 = report["cutscene_type4_relation"]
assert type4["descriptor_type"] == 4
assert type4["relation"] == "same_referee_skeletal_family_not_proved_same_descriptor_instance"
assert type4["instance_level_link_proved"] is False
assert type4["portme"].startswith("// PORTME:")
assert all(item.startswith("// PORTME:") for item in report["portme"])

for pin in report["source_pins"].values():
    path = Path(pin["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"]

with selectors_path.open(encoding="utf-8", newline="") as stream:
    selectors = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(selectors) == 26
row4 = selectors[4]
assert row4["selector_index"] == "4"
assert row4["row_va"] == "0x00513f58"
assert row4["right_pointer_field_va"] == "0x00513f5c"
assert row4["right_name_string_va"] == "0x00e87fb8"
assert row4["right_name"] == "ANM_REF_PENALTY_DELAY_OF_GAME_R"
assert row4["right_outer_index"] == "3107" and row4["right_chunk_index"] == "27"
assert row4["right_slot_offset"] == "304128"
for row in selectors:
    for side in ("left", "right"):
        if row[f"{side}_name"]:
            assert row[f"{side}_match_count"] == "1"
            assert row[f"{side}_outer_index"] == "3107"
        else:
            assert row[f"{side}_match_count"] == "0"

with path_path.open(encoding="utf-8", newline="") as stream:
    paths = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(paths) == 10
assert [int(row["step"]) for row in paths] == list(range(1, 11))
assert paths[3]["target"] == "0x00e887b0"
assert paths[-1]["confidence"] == "instruction_exact_abi_relation_instance_unproved"

xbe = xbe_path.read_bytes()
header = json.loads(header_path.read_text(encoding="utf-8"))
assert hashlib.md5(xbe).hexdigest() == "444064a9ec984dd29d2c05a43f5c96e8"
def at(va: int, size: int) -> bytes:
    for section in header["sections"]:
        start = section["virtual_address"]
        if start <= va and va + size <= start + section["raw_size"]:
            offset = section["raw_address"] + va - start
            return xbe[offset:offset + size]
    raise AssertionError(hex(va))

expected_hashes = {
    (0x001685B0, 0xA3): "8b58d794c0c73349d51eb00cba904f0b726f0c8875548e332068dfa0ab47fc9c",
    (0x00240750, 0x77): "04cb30fcd9543c1890ccc695692f2b63c613b95e63144a04176cc607a33dc39b",
    (0x002407D0, 0xC3): "143ae215e45d1ecba61f6ff611176e4efa8130ecbd8567e7c54745c245a460c3",
    (0x001FB1A0, 0xA4): "0341752b975ba67df40f8964ceb5bbcb850dd12ee013fb8777e96d193d9c2ee6",
    (0x00217EB0, 0x6F): "c58daedb47eead40708b3edcc5904b5c704769a7a509185322944cb34aca73fe",
    (0x00096A80, 0x4C): "22c79b223bd234a8f51a1f50dfcf23ec79f2ae2c601fd4fd6476e97003f93c70",
    (0x00096B20, 0x2E): "24484165f9eaf0fcc742022a8dd3e45c929516001c780b9c3fb8019f8ccbff48",
    (0x002D6B70, 0xB0): "ef1830e2ec494cb14f6d43a6ffb0f82d77d5479a1aceb94596c7c32fcfdfc919",
    (0x0031C180, 0x2F3): "f9183d791868eff01a42b152a729865f296d262195e1b4150bb8ccb25dbf0ef3",
    (0x00513F28, 0x138): "b391957a98a00e032ee661b0dab52d332fda9a8fbe77c0f7c26ca910c5214816",
    (0x00514060, 0x14): "953f00b17056ee570550b6a0aaa69094631de8e993338f0ebc2b4e8a0690debf",
    (0x0051D010, 0x32): "39a441532daab4cdbe4ff777641021bc179da9a5a69d43a94cdcb45fcc21e435",
}
for key, digest in expected_hashes.items():
    assert hashlib.sha256(at(*key)).hexdigest() == digest

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "0x001685B5 MOV EDX,0x44434d53",
    "0x0024083C LEA ESI,[ESI*0x4 + 0x513f28]",
    "0x0024085B MOV ECX,0xe887b0",
    "0x00240866 CALL 0x001685b0",
    "0x0024075F MOV ECX,0xe887b0",
    "0x00240764 CALL 0x001685e0",
    "0x001FB3BC CALL 0x001fb1a0",
    "0x001FB200 CALL 0x002407d0",
    "0x0024073C CALL 0x002d6b70",
    "0x002D6C13 CALL 0x0031c180",
    "0x00217EB2 MOV EDI,dword ptr [0x00e60274]",
    "0x00217EF6 MOV dword ptr [ESI + 0x18],0x51d010",
    "0x00217F04 MOV dword ptr [ESI + 0x30],0x96a80",
    "0x00096604 PUSH 0xe65dd0",
    "0x0012F872 CALL 0x00096a80",
    "0x0012F9BA CALL 0x00096b20",
    "0x00E65DD0 length=32 bytes=72006500660065007200650065000000",
    "0x00E887B0 length=32 bytes=52006500660065007200650065000000",
):
    assert exact in trace, exact
assert pseudo.count("// PORTME: could not decompile function at") == 2
assert "// PORTME: could not decompile function at 0x001FB0B0" in pseudo
assert "// PORTME: could not decompile function at 0x002405F0" in pseudo
assert "/* 0x002407D0:FUN_002407d0 */" in pseudo
assert "/* 0x00096600:FUN_00096600 */" in pseudo
assert "/* 0x00217EB0:FUN_00217eb0 */" in pseudo
PY

mode=normal
if [[ "${NFL_REF_CLIP_OWNERSHIP_GHIDRA:-0}" == 1 ]]; then
  ghidra='tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless'
  test -x "$ghidra"
  test -d ghidra_projects/nfl2k5.rep
  mkdir -p "$temporary/ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflRefClipOwnershipTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_ref_clip_ownership_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_ref_clip_ownership_focused_pseudo_c.c" "$pseudo"
  mode=full
fi

echo "NFL_REF_CLIP_OWNERSHIP_VALIDATION_COMPLETE mode=$mode selector_rows=26 path_steps=10"
