#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

python3 -m py_compile tools/director_inventory.py
tmp=$(mktemp -d /tmp/vc-director-validate.XXXXXX)
trap 'rm -rf "$tmp"' EXIT

PYTHONPATH=tools python3 tools/director_inventory.py \
  --apf-index 'extracted/All-Pro Football 2K8 (USA)/0A' \
  --nfl-index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --json "$tmp/director.json" \
  --tsv "$tmp/director.tsv"

cmp "$tmp/director.json" reports/assets/cross_title_director_inventory.json
cmp "$tmp/director.tsv" reports/assets/cross_title_director_records.tsv

python3 - <<'PY'
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import zlib

report = json.loads(
    Path("reports/assets/cross_title_director_inventory.json").read_text(
        encoding="utf-8"
    )
)
assert report["schema"] == "vc_cross_title_director_inventory/v1"
assert report["constants"] == {
    "apf_fixed_slot_count": 217,
    "director_crc32": "0x1e90d3f0",
    "drct_crc32": "0xed586383",
    "fixed_record_header_size": 28,
    "nfl_fixed_slot_count": 193,
    "relative_pointer_rule": (
        "target = pointer_field_offset - 1 + signed_stored_value"
    ),
}
assert report["summary"] == {
    "all_decoded_bytes_preserved_in_raw_partitions": True,
    "all_fixed_record_packages_bounded": True,
    "all_instruction_records_exactly_partitioned": True,
    "all_primary_strings_exactly_partitioned": True,
    "all_relative_pointers_bounded": True,
    "apf_fixed_record_count": 137,
    "apf_instruction_record_count": 1623,
    "apf_primary_string_count": 120,
    "apf_resource_count": 5,
    "nfl_fixed_record_count": 136,
    "nfl_instruction_record_count": 2041,
    "nfl_primary_string_count": 583,
    "nfl_resource_count": 5,
    "shared_exact_primary_string_count": 114,
    "writer_implemented": False,
}
assert all("PORTME:" in item for item in report["portme"])

resources = report["resources"]
assert len(resources) == 10
apf = resources[:5]
nfl = resources[5:]
roles = ["ingame", "wrapup", "tutorial", "intro", "halftime"]
assert [item["role"] for item in apf] == roles
assert [item["role"] for item in nfl] == roles
assert [item["outer_index"] for item in apf] == [153, 265, 553, 1071, 681]
assert [item["outer_index"] for item in nfl] == [4, 19, 345, 1194, 1195]
assert [item["outer_name"] for item in apf] == [
    "dir_ingame.iff", "dir_wrapup.iff", "dir_tutorial.iff",
    "dir_intro.iff", "dir_halftime.iff",
]
assert [item["byte_size"] for item in apf] == [
    402080, 36912, 38752, 50272, 33920,
]
assert [item["byte_size"] for item in nfl] == [
    505568, 36160, 38736, 73680, 29168,
]
assert [item["sha256"] for item in apf] == [
    "cd5bea8f217ce8fc2ca2ba5f8fc0666f325f12980646df10dc68b27c90aa5a49",
    "3545b4bc8ae3a17fb24edcd278010d814ad9a73ae74bb87064476139c3205dbc",
    "6438d7f7da112980a62a00fa464d6e2ab89564d75185b05fe29b3bb6110fa31b",
    "62b0eff9a1092a4ae9b355694b0516ee43759a449de976d0facf663b954d6496",
    "dea46a25512b6f9802d5c4552ff49504fab424d4cc8267434c2db2440f960aee",
]
assert [item["sha256"] for item in nfl] == [
    "79a35653bf251c3261530092e10a3a224a18e8cf758a4b68769bc3f43176bfce",
    "5c2b4f619ef0a02150281c42436ac77446f93f476ea32dd7b190774f94bf95f8",
    "862e224898a9983b9b476cfa338ebaf9a871c6dd44147e923afa11669e8b6370",
    "0b6b6b8cbf5c79b3a982c128c20ce78db051f287d10cd3bc78bbaa217b752654",
    "271475eb8c9a6ed66bfb76084f3189ff5dbbdca78836c8ff5f5791a9576806c5",
]

assert [item["graph"]["instruction_count"] for item in apf] == [
    1015, 96, 3, 393, 116,
]
assert [item["graph"]["instruction_count"] for item in nfl] == [
    1310, 96, 3, 526, 106,
]
assert [item["graph"]["string_count"] for item in apf] == [7, 0, 101, 0, 12]
assert [item["graph"]["string_count"] for item in nfl] == [347, 0, 101, 123, 12]
assert [item["graph"]["nonnull_fixed_record_count"] for item in apf] == [
    112, 20, 1, 3, 1,
]
assert [item["graph"]["nonnull_fixed_record_count"] for item in nfl] == [
    111, 20, 1, 3, 1,
]
assert all(item["graph"]["fixed_slot_count"] == 217 for item in apf)
assert all(item["graph"]["fixed_slot_count"] == 193 for item in nfl)
assert all(item["root"]["opaque_auxiliary_count_u32_10"] == 1 for item in apf)
assert all(len(item["opaque_auxiliary_directory"]["entries"]) == 1 for item in apf)
assert all(item["common_header"]["name_pointer"]["target_offset"] == 0x20 for item in nfl)
assert all(item["common_header"]["root_pointer"]["target_offset"] == 0x40 for item in nfl)

for resource in resources:
    reconstructed = bytearray()
    cursor = 0
    for region in resource["raw_partition"]:
        assert region["offset"] == cursor
        raw = bytes.fromhex(region["raw_hex"])
        assert len(raw) == region["size"]
        assert hashlib.sha256(raw).hexdigest() == region["sha256"]
        reconstructed.extend(raw)
        cursor += len(raw)
    assert len(reconstructed) == resource["byte_size"]
    assert hashlib.sha256(reconstructed).hexdigest() == resource["sha256"]

    graph = resource["graph"]
    assert len(graph["fixed_slots"]) == graph["fixed_slot_count"]
    assert len(graph["fixed_records"]) == graph["nonnull_fixed_record_count"]
    assert len(graph["instructions"]) == graph["instruction_count"]
    assert len(graph["strings"]) == graph["string_count"]
    assert graph["instruction_pointer_fields_end"] == graph["fixed_table_offset"]
    assert graph["fixed_records"][0]["offset"] == graph["fixed_table_end"]
    assert graph["fixed_records"][-1]["package_end"] == graph["instruction_records_offset"]
    assert graph["instructions"][-1]["end_offset"] == graph["string_directory_offset"]
    assert all(record["size"] > 0 for record in graph["instructions"])
    for record in graph["fixed_records"]:
        assert len(record["child_references"]) == record["child_count"]
        assert record["package_end"] == record["offset"] + record["package_size"]
        for pointer in record["pointer_fields"] + record["child_references"]:
            target = pointer["target_offset"]
            assert target is None or record["offset"] <= target < record["package_end"]
    expected = graph["string_directory_end"]
    for string in graph["strings"]:
        assert string["offset"] == expected
        expected = string["end_offset"]
    assert expected == graph["string_pool_end"]

cross = {item["role"]: item for item in report["cross_title_roles"]}
assert list(cross) == roles
assert [cross[role]["shared_exact_primary_string_count"] for role in roles] == [
    1, 0, 101, 0, 12,
]
assert [cross[role]["shared_structural_signature_multiset_count"] for role in roles] == [
    24, 19, 1, 1, 0,
]
assert cross["wrapup"]["ordered_structural_signature_match_count"] == 19
assert cross["tutorial"]["ordered_structural_signature_match_count"] == 1
assert cross["tutorial"]["ordered_record_pairs"] == [
    {
        "apf_child_count": 109,
        "apf_slot_index": 142,
        "apf_unknown_u16_04": 4,
        "apf_unknown_u16_06": 109,
        "nfl_child_count": 109,
        "nfl_slot_index": 135,
        "nfl_unknown_u16_04": 4,
        "nfl_unknown_u16_06": 109,
        "ordinal": 0,
        "structural_signature_equal": True,
    }
]
assert {item["text"] for item in cross["ingame"]["shared_exact_primary_strings"]} == {
    "_HIDE_"
}
assert "Coach Pick" in {
    item["text"] for item in cross["tutorial"]["shared_exact_primary_strings"]
}
assert "Team Comparison" in {
    item["text"] for item in cross["halftime"]["shared_exact_primary_strings"]
}

with Path("reports/assets/cross_title_director_records.tsv").open(
    encoding="utf-8", newline=""
) as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 4640
counts = Counter(row["kind"] for row in rows)
assert counts == {
    "fixed_record_package": 273,
    "opaque_instruction_record": 3664,
    "primary_string": 703,
}
assert sum(row["shared_exact_text"] == "True" for row in rows) == 228

xbe = Path("extracted/ESPN NFL 2K5 (USA)/default.xbe").read_bytes()
def at(va: int, size: int) -> bytes:
    # This XBE's complete .text mapping is file offset = VA - 0x10000.
    return xbe[va - 0x10000 : va - 0x10000 + size]

assert at(0x00166760, 21) == bytes.fromhex(
    "6830671600ba44524354b930b7bd00e82ccfedffc3"
)
assert at(0x00166700, 38) == bytes.fromhex(
    "8bca568b710c33d233c081fe445243545e750abac0661600b8e066160050"
    "e8edd6edffc20800"
)
assert at(0x00166730, 44) == bytes.fromhex(
    "56578bf28bf9e895d0edff8b56048bc8e8bb1feeff8b4e046a0068006716"
    "00518bd08bcfe83766f8ff5f5ec3"
)
expected_hashes = {
    (0x001666C0, 26): "2966b5ebb96887f3615edea2c82f36fdf5112d2880317b65c4c3eb6d61235c06",
    (0x001666E0, 25): "e4634fe094e18f8e12e6b5ce3c89e787ab88217490476674a9a8e192f0069467",
    (0x000DC700, 254): "78c555da346cefdacd60fa0cf31b5dcff8e6489a43c92fe9ef29465cc28630cf",
    (0x000DC840, 150): "f37345ac976b9577b2335115cde02bb453faa23f2eeac9af45b0d6383dd417fa",
    (0x000DC8E0, 32): "a468e3f4138564935a4c373697c6e6188bddf071a99bc395492e63b828159426",
    (0x000DCA40, 207): "c26a816a7a9d805025a1dd4044876b1f5856cab0917ad84c2dcdca48df70da0a",
    (0x000DCBA0, 7): "71b5718cb6494f0171b6774007cb898e42eb9277f977d16958d5ae3299cabba2",
    (0x000DCB20, 119): "9b9de0f06db4903e5f7cd6e11644ea1958910c3a1b946566911881de7214f4e6",
}
for (va, size), expected in expected_hashes.items():
    assert hashlib.sha256(at(va, size)).hexdigest() == expected

assert zlib.crc32(b"DRCT") & 0xFFFFFFFF == 0xED586383
assert zlib.crc32(b"director") & 0xFFFFFFFF == 0x1E90D3F0
trace = Path(
    "reports/assets/cross_title_director_ghidra/director_trace.txt"
).read_text(encoding="utf-8")
pseudo = Path(
    "reports/assets/cross_title_director_ghidra/director_focused_pseudo_c.c"
).read_text(encoding="utf-8")
assert "CRC32('DRCT')=0xED586383" in trace
assert "0x84D1B834 raw=0xED586383 refs=" in trace
assert "0x84D1B830 raw=0x82003F90" in trace
assert "registry_base_refs=0x8466AF94(0x8466AF70:Function_8466AF70,PARAM)" in trace
assert "LOW_HALFWORD_COLLISIONS_NOT_DIRECT_DRCT_EVIDENCE" in trace
assert "void Function_8466AF70(void)" in pseudo
assert "0xffffffff84d1b7d0" in pseudo
assert "Function_8468DA70" in pseudo
PY

if [[ ${DIRECTOR_GHIDRA_REGEN:-0} == 1 ]]; then
  env HOME="$ROOT/tools/ghidra-home" \
    XDG_CONFIG_HOME="$ROOT/tools/ghidra-home/.config" \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      ghidra_projects apf2k8 -process default.xex -noanalysis -readOnly \
      -scriptPath tools/ghidra_scripts/apf \
      -postScript ApfDirectorTrace.java "$tmp/ghidra"
  cmp "$tmp/ghidra/director_trace.txt" \
    reports/assets/cross_title_director_ghidra/director_trace.txt
  cmp "$tmp/ghidra/director_focused_pseudo_c.c" \
    reports/assets/cross_title_director_ghidra/director_focused_pseudo_c.c
  echo DIRECTOR_GHIDRA_REGEN_PASS
fi

echo 'DIRECTOR_VALIDATION_PASS apf=5/137/1623/120 nfl=5/136/2041/583 shared=114'
