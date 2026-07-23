#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
resource_inventory='reports/assets/nfl2k5_resource_chunks_v2.json'
report='reports/assets/nfl2k5_motion_inventory.json'
tsv='reports/assets/nfl2k5_motion_roots.tsv'
trace='reports/assets/nfl2k5_motion_ghidra/motion_trace.txt'
pseudo='reports/assets/nfl2k5_motion_ghidra/motion_focused_pseudo_c.c'

for required in \
  "$index" "$xbe" "$resource_inventory" \
  tools/nfl_motion_inventory.py tools/nfl_outer.py \
  tools/ghidra_scripts/Nfl2k5MotionTrace.java \
  docs/research/nfl_motion.md "$report" "$tsv" "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_motion_inventory.py
temporary=$(mktemp -d /tmp/nfl2k5-motion.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_motion_inventory.py "$index" \
  --resource-inventory "$resource_inventory" \
  --json "$temporary/inventory.json" \
  --tsv "$temporary/roots.tsv"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/roots.tsv" "$tsv"
test "$(wc -l < "$tsv")" -eq 6069
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  7b1af7c95d3c2774c2129f2832c4a760c3c9df8330ed38c00ed5e00646210c1e
test "$(sha256sum "$tsv" | cut -d' ' -f1)" = \
  fca7d9d150a5e599dc5fa20c3c30c0136035d2880bad6ee318cf0e3824d48c13

python3 - "$report" "$tsv" "$xbe" "$trace" "$pseudo" <<'PY'
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, tsv_path, xbe_path, trace_path, pseudo_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))

assert report["schema"] == "nfl2k5_motion_inventory/v1"
assert report["pointer_rule"] == (
    "target = field_offset + signed_le32(stored_value) - 1; "
    "zero is null only where allowed"
)
assert report["summary"] == {
    "all_pointer_bounded_regions_reconstruct": True,
    "all_wrapper_bodies_uncompressed": True,
    "alternate_four_region_root_count": 171,
    "decoded_motion_body_bytes": 60930224,
    "mmcd_body_length": {"maximum": 62288, "minimum": 5552, "unique_count": 284},
    "mmcd_child_count_distribution": {"2": 436, "3": 179, "4": 20, "5": 4},
    "mmcd_embedded_root_count": 1509,
    "mmcd_outer_count": 3,
    "mmcd_resource_count": 639,
    "mmcd_unique_name_count": 639,
    "motion_outer_count": 574,
    "motion_resource_count": 5198,
    "packed_region_count": 18375,
    "smcd_body_length": {"maximum": 61168, "minimum": 656, "unique_count": 423},
    "smcd_outer_count": 571,
    "smcd_repeated_name_count": 1894,
    "smcd_resource_count": 4559,
    "smcd_unique_name_count": 2333,
    "standalone_and_embedded_root_count": 6068,
    "standard_three_region_root_count": 5897,
    "zero_padding_before_motion_chunk_bytes": 29835360,
    "zero_padding_before_motion_chunk_count": 1058,
    "zero_trailing_region_bytes": 141408,
    "zero_trailing_region_count": 13,
}
assert report["proved_layout"] == {
    "alternate_target_order": [44, 48, 40, 36],
    "common_body": {
        "callback_slots_offset": 24,
        "fourcc_offset": 12,
        "name_pointer_offset": 16,
        "name_target": 32,
        "root_pointer_offset": 20,
    },
    "mmcd_child_root_array_stride": 52,
    "mmcd_directory_record_size": 16,
    "root_pointer_fields": [36, 40, 44, 48],
    "smcd_compatible_root_size": 52,
    "standard_target_order": [44, 40, 36],
}
assert report["executable_evidence"] == {
    "common_mmcd_load_callback": "0x00168440",
    "common_mmcd_release_callback": "0x00168470",
    "common_smcd_load_callback": "0x00168400",
    "common_smcd_release_callback": "0x00168430",
    "contract": (
        "SMCD relocates root +0x24/+0x28/+0x2c/+0x30; MMCD loops a "
        "root count over 0x10-byte directory records, relocates record +0, "
        "and applies the SMCD relocator to every child root"
    ),
    "mmcd_root_inverse": "0x002d0280",
    "mmcd_root_relocator": "0x002d0240",
    "smcd_root_inverse": "0x002d01d0",
    "smcd_root_relocator": "0x002d0180",
    "type_registration": "0x00168520",
}
assert all("PORTME:" in item for item in report["portme"])

resources = report["resources"]
assert len(resources) == 5198
assert Counter(item["kind"] for item in resources) == {"SMCD": 4559, "MMCD": 639}
roots = [root for item in resources for root in item["roots"]]
regions = [region for item in resources for region in item["packed_regions"]]
assert len(roots) == 6068 and len(regions) == 18375
assert Counter(root["variant"] for root in roots) == {
    "standard_three_region": 5897,
    "alternate_four_region": 171,
}
assert sum(item["decoded_length"] for item in resources) == 60930224
assert sum(item["root_count"] for item in resources if item["kind"] == "MMCD") == 1509
assert all(item["stored_size"] == item["decoded_length"] for item in resources)
assert all(item["common"]["name_pointer"]["target"] == 0x20 for item in resources)
assert all(item["common"]["root_pointer"]["target"] >= item["common"]["name_end"]
           for item in resources)

for item in resources:
    assert len(item["roots"]) == item["root_count"]
    assert len(item["packed_regions"]) == sum(
        3 if root["variant"] == "standard_three_region" else 4
        for root in item["roots"]
    )
    assert item["packed_regions"][0]["offset"] == item["prefix_length"]
    assert item["packed_regions"][-1]["end"] == item["decoded_length"]
    assert all(left["end"] == right["offset"]
               for left, right in zip(item["packed_regions"], item["packed_regions"][1:]))
    targets = []
    for root in item["roots"]:
        concrete = [pointer for pointer in root["pointers"] if pointer is not None]
        targets.extend(pointer["target"] for pointer in concrete)
        relative_order = [
            pointer["field_offset_relative_to_root"]
            for pointer in sorted(concrete, key=lambda pointer: pointer["target"])
        ]
        assert relative_order == (
            [44, 40, 36] if root["variant"] == "standard_three_region"
            else [44, 48, 40, 36]
        )
    assert len(targets) == len(set(targets))
    if item["kind"] == "SMCD":
        assert item["root_count"] == 1 and item["directory_records"] == []
    else:
        assert item["root_count"] in (2, 3, 4, 5)
        assert len(item["directory_records"]) == item["root_count"]
        first_child = item["roots"][0]["offset"]
        assert [root["offset"] for root in item["roots"]] == [
            first_child + index * 0x34 for index in range(item["root_count"])
        ]
        assert [record["child_target"] for record in item["directory_records"]] == [
            root["offset"] for root in item["roots"]
        ]

tails = report["zero_trailing_regions"]
assert len(tails) == 13
assert sum(item["length"] for item in tails) == 141408
assert all(item["sha256"] == hashlib.sha256(bytes(item["length"])).hexdigest()
           for item in tails)

with tsv_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 6068
assert Counter(row["variant"] for row in rows) == {
    "standard_three_region": 5897,
    "alternate_four_region": 171,
}

xbe = xbe_path.read_bytes()
assert hashlib.md5(xbe).hexdigest() == "444064a9ec984dd29d2c05a43f5c96e8"
def at(va: int, size: int) -> bytes:
    return xbe[va - 0x10000:va - 0x10000 + size]

assert hashlib.sha256(at(0x00168400, 0x80)).hexdigest() == \
    "18e9380f58dcefb782645715a3d886795f54844cd33abb13cfea008e5d635d4c"
assert hashlib.sha256(at(0x00168520, 0x5B)).hexdigest() == \
    "9bf9f244f1c6e40a3370049bd1e09b95e2015b22726e2df8e12bf44ad3606679"
assert hashlib.sha256(at(0x002D0180, 0x99)).hexdigest() == \
    "29144e1ab23ce763afae8e59d597000d4249033ad225665713db6e12d8ce516b"
assert hashlib.sha256(at(0x002D0240, 0x7D)).hexdigest() == \
    "243a36eaf958d96247eefe38dce767603afe7ab33858488743566e8f57432ea6"

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "0x00168525 MOV EDX,0x44434d53",
    "0x00168539 MOV EDX,0x44434d4d",
    "0x00168548 PUSH 0x168430",
    "0x0016854D PUSH 0x168400",
    "0x00168561 PUSH 0x168470",
    "0x00168566 PUSH 0x168440",
    "0x00168423 CALL 0x002d0180",
    "0x00168433 CALL 0x002d01d0",
    "0x00168463 CALL 0x002d0240",
    "0x00168473 CALL 0x002d0280",
    "0x002D0184 MOV EAX,dword ptr [ECX + 0x24]",
    "0x002D0192 MOV EAX,dword ptr [ECX + 0x28]",
    "0x002D01A0 MOV EAX,dword ptr [ECX + 0x2c]",
    "0x002D01AE MOV EAX,dword ptr [ECX + 0x30]",
    "0x002D026A ADD ESI,0x10",
):
    assert exact in trace

for address in ("002D0180", "002D01D0", "002D0240", "002D0280"):
    assert f"/* 0x{address}:" in pseudo
for offset in ("0x24", "0x28", "0x2c", "0x30"):
    assert f"param_1 + {offset}" in pseudo
missing = (
    "0x00168300", "0x001683D0", "0x00168400", "0x00168430",
    "0x00168440", "0x00168470", "0x00168480", "0x001684D0",
)
for address in missing:
    assert (f"// PORTME: could not decompile function at {address}; "
            "Ghidra has no saved function boundary") in pseudo
assert pseudo.count("// PORTME: could not decompile function at ") == len(missing)

print("NFL2K5_MOTION_JSON_AND_XBE_INVARIANTS_PASS")
PY

if [[ ${NFL_MOTION_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript Nfl2k5MotionTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/motion_trace.txt" "$trace"
  cmp "$temporary/ghidra/motion_focused_pseudo_c.c" "$pseudo"
  echo NFL2K5_MOTION_GHIDRA_REGEN_PASS
fi

echo 'NFL2K5_MOTION_VALIDATION_PASS resources=5198 roots=6068 regions=18375'
