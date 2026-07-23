#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
report='reports/assets/nfl_motion_object_pools.json'
trace='reports/assets/nfl_motion_object_pools_ghidra/motion_object_pool_trace.txt'
pseudo='reports/assets/nfl_motion_object_pools_ghidra/motion_object_pool_focused_pseudo_c.c'

for required in \
  "$xbe" "$xbe_header" \
  tools/nfl_motion_object_pools.py tools/nfl_motion_sampler_inventory.py \
  tools/ghidra_scripts/NflMotionObjectPoolTrace.java \
  docs/research/nfl_motion_object_pools.md \
  "$report" "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile \
  tools/nfl_motion_object_pools.py tools/nfl_motion_sampler_inventory.py
temporary=$(mktemp -d /tmp/nfl-motion-object-pools.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_motion_object_pools.py \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --json "$temporary/object_pools.json"

cmp "$temporary/object_pools.json" "$report"
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  e17463f958af37d2566d8e018b45d87f0b1bc1f2fe5aad7f016e378b0fafb443
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  c6ce0822cd92db557a2b19df4bb15b467b14795959c1a730266c06cd3d82a3f0
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  7049c6f05ae90d5108b8e07a642545dc813c243f5951c68dbcc8c2f76c611ab3

python3 - "$report" "$xbe" "$xbe_header" "$trace" "$pseudo" <<'PY'
import hashlib
import json
from pathlib import Path
import struct
import sys

report_path, xbe_path, header_path, trace_path, pseudo_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_motion_object_pools/v1"
assert report["executable_md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert report["summary"] == {
    "all_actor_configuration_indices_dense": True,
    "all_actor_configuration_records_use_21_packed_dwords": True,
    "configuration_count": 5,
    "maximum_combined_side_actor_count": 22,
    "maximum_seven_actor_pool_count": 7,
    "maximum_team_affiliated_actor_pool_count": 2,
}

allocation = report["allocation_table"]
assert allocation["va"] == "0x004f9e98"
assert allocation["record_size"] == 20
assert allocation["sha256"] == "ba2c5b0ab36f30157d9425dfce3d645d67fdb8838cddb857dfa1dcb9f2152874"
rows = allocation["rows"]
expected_rows = [
    [1, 1, 0, 1, 0],
    [11, 11, 0, 1, 2],
    [11, 0, 0, 1, 1],
    [11, 11, 0, 1, 2],
    [11, 11, 7, 1, 2],
]
assert [row["raw_words"] for row in rows] == expected_rows
assert [row["combined_side_actor_count"] for row in rows] == [2, 22, 11, 22, 22]

pools = report["motion_mapped_pools"]
assert [pool["structural_name"] for pool in pools] == [
    "two_side_actor_pool", "seven_actor_pool", "team_affiliated_actor_pool"
]
assert [pool["maximum_count"] for pool in pools] == [22, 7, 2]
assert [pool["head_global_va"] for pool in pools] == [
    "0x00e60268", "0x00e60274", "0x00e537f4"
]
assert [pool["allocator"] for pool in pools] == [
    "0x00075b30", "0x00074d40", "0x000dd6a0"
]
assert [pool["linked_record_stride"] for pool in pools] == [0x50, 0x38, 0x3C]
assert [pool["backing_record_stride"] for pool in pools] == [0x15C0, 0x640, 0x640]
assert [pool["allocator_type_value"] for pool in pools] == [1, 2, 3]
assert [pool["next_pointer_offset"] for pool in pools] == [0x30, 0x30, 0x38]
assert [pool["channel_map_va"] for pool in pools] == [
    "0x0051cd70", "0x0051d010", "0x0051d010"
]
assert [pool["enabled_channel_count"] for pool in pools] == [23, 21, 21]
assert [pool["semantic_confidence"] for pool in pools] == [
    "strong_inference_not_source_symbol",
    "plausible_inference_explicitly_unproved",
    "team_affiliation_proved_role_name_unproved",
]

seven = pools[1]["configuration_record_table"]
team = pools[2]["configuration_record_table"]
assert seven["va"] == "0x0050df00" and seven["record_count"] == 7
assert seven["sha256"] == "f81d2cc44798e2a58cbf0564b6678037a95bab5e84e7737a4a6a2be2de433578"
assert team["va"] == "0x0050dfc4" and team["record_count"] == 2
assert team["sha256"] == "74cca2ebfd7e8e87e3a8608c14a35f7a47882b16a47f4b041144f827b2831ad3"
for table in (seven, team):
    assert [record["actor_or_owner_index"] for record in table["records"]] == list(range(table["record_count"]))
    assert all(record["packed_quaternion_dwords_per_frame"] == 21 for record in table["records"])
    assert all(record["trailing_zero_words"] == [0, 0] for record in table["records"])
assert [record["coordinates"] for record in team["records"]] == [["0", "0", "0"], ["0", "0", "0"]]
assert pools[2]["team_binding"] == {
    "function": "0x001d2b00",
    "owner_globals": ["0x00e5fc20", "0x00e5fc60"],
    "owner_index_source": "record +0x10 / word 4",
    "owner_indices": [0, 1],
}
assert report["separate_unmapped_pool"] == {
    "allocation_count_column": 3,
    "allocator": "0x000ddad0",
    "count_in_all_configurations": 1,
    "head_global_va": "0x00e537f0",
    "installed_by_motion_channel_initializer": False,
    "meaning": "retained separately; this pool is not assigned either recovered map",
}
assert all("PORTME:" in value for value in report["portme"])

expected_functions = {
    "0x00074d40": (0x78, "0d3ccc0a2df97ab83d172fb61a1e2c75a28ef19ad282b50f0cb6381e50e2c60f"),
    "0x00075b30": (0x98, "f08ae810e33cf50ec2141745854ac653656094c739fab573c21630c2bf4c5403"),
    "0x000dd6a0": (0x75, "b10a0185e881a52b5ff36f5e7d2fb3dd85a27df22a6bb14e64bc84c53ee51a4a"),
    "0x000ddad0": (0x60, "7e7a84a3f74607a5fda6dfadc674fd678f8948ccb8ffe63ad4891c2d77a936fc"),
    "0x0011a540": (0x1CB, "cfffe5b10aba7094ebd0f318b79f48f51e0cb06f17b29dae9c0f5afa64b114a6"),
    "0x001d2b00": (0x40, "dd99069f3200c121f648d00346c86d9973c35ea7854d3e42adf68922d2753bee"),
    "0x00217e10": (0x9A, "af2e563d0ada69f608f78bc44b329b8327705f8ca76d7de08748b78046c9b460"),
    "0x00217eb0": (0x6F, "c58daedb47eead40708b3edcc5904b5c704769a7a509185322944cb34aca73fe"),
    "0x00217f20": (0x6F, "229362ded28d90e505317da57306fec0d660440910cd644484145fd1520c13d5"),
}
assert {key: (value["size"], value["sha256"]) for key, value in report["function_hashes"].items()} == expected_functions

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

assert list(struct.unpack("<25I", at(0x004F9E98, 100))) == [word for row in expected_rows for word in row]
assert hashlib.sha256(at(0x0050DF00, 196)).hexdigest() == seven["sha256"]
assert hashlib.sha256(at(0x0050DFC4, 56)).hexdigest() == team["sha256"]
for key, (size, digest) in expected_functions.items():
    assert hashlib.sha256(at(int(key, 16), size)).hexdigest() == digest

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "ALLOCATION_TABLE_004F9E98=01000000010000000000000001000000000000000b0000000b0000000000000001000000020000000b000000000000000000000001000000010000000b0000000b0000000000000001000000020000000b0000000b000000070000000100000002000000",
    "0x0011A567 MOV ECX,dword ptr [EDI + 0x4f9ea0] owner=0x0011A540:FUN_0011a540",
    "0x0011A572 MOV ECX,dword ptr [EDI + 0x4f9e98] owner=0x0011A540:FUN_0011a540",
    "0x0011A578 ADD ECX,dword ptr [EDI + 0x4f9e9c] owner=0x0011A540:FUN_0011a540",
    "0x0011A583 MOV ECX,dword ptr [EDI + 0x4f9ea8] owner=0x0011A540:FUN_0011a540",
    "0x0011A59F MOV ECX,dword ptr [EDI + 0x4f9ea4] owner=0x0011A540:FUN_0011a540",
    "0x00074DA2 ADD ECX,0x640 owner=0x00074D40:FUN_00074d40",
    "0x00074DA8 ADD EAX,0x38 owner=0x00074D40:FUN_00074d40",
    "0x00075B97 ADD ESI,0x15c0 owner=0x00075B30:FUN_00075b30",
    "0x00075B9D ADD EAX,0x50 owner=0x00075B30:FUN_00075b30",
    "0x000DD6FB ADD ECX,0x640 owner=0x000DD6A0:FUN_000dd6a0",
    "0x000DD701 ADD EAX,0x3c owner=0x000DD6A0:FUN_000dd6a0",
    "0x001D2B21 MOV EAX,0xe5fc20 owner=0x001D2B00:FUN_001d2b00",
    "0x001D2B28 MOV EAX,0xe5fc60 owner=0x001D2B00:FUN_001d2b00",
    "0x00217E12 MOV EDI,dword ptr [0x00e60268] owner=0x00217E10:FUN_00217e10",
    "0x00217EB2 MOV EDI,dword ptr [0x00e60274] owner=0x00217EB0:FUN_00217eb0",
    "0x00217F22 MOV EDI,dword ptr [0x00e537f4] owner=0x00217F20:FUN_00217f20",
):
    assert exact in trace, exact
for address in ("0011A540", "00074D40", "00075B30", "000DD6A0", "000DDAD0", "001D2B00", "00217E10", "00217EB0", "00217F20"):
    assert f"/* 0x{address}:" in pseudo
assert pseudo.count("/* 0x") == 9
assert "// PORTME: could not decompile function at " not in pseudo
assert "piVar3 = &DAT_0050dfd4;" in pseudo
assert "puVar1 = &DAT_00e5fc20;" in pseudo
assert "puVar1 = &DAT_00e5fc60;" in pseudo

print("NFL_MOTION_OBJECT_POOLS_JSON_XBE_GHIDRA_ASSERTIONS_PASS")
PY

if [[ ${NFL_MOTION_OBJECT_POOLS_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflMotionObjectPoolTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/motion_object_pool_trace.txt" "$trace"
  cmp "$temporary/ghidra/motion_object_pool_focused_pseudo_c.c" "$pseudo"
  echo NFL_MOTION_OBJECT_POOLS_GHIDRA_REGEN_PASS
fi

echo 'NFL_MOTION_OBJECT_POOLS_VALIDATION_PASS configurations=5 maxima=22/7/2'
