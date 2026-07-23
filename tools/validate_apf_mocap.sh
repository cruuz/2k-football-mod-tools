#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index=${APF_INDEX:-extracted/All-Pro Football 2K8 (USA)/0A}
scene=${APF_SCENE_INVENTORY:-reports/assets/apf_scene_inventory.json}
nfl=${NFL_MOTION_INVENTORY:-reports/assets/nfl2k5_motion_inventory.json}
report=reports/assets/apf_mocap_inventory.json
mocap_tsv=reports/assets/apf_mocap.tsv
event_tsv=reports/assets/apf_mocap_events.tsv
sample_tsv=reports/assets/apf_mocap_root_samples.tsv
bone_tsv=reports/assets/apf_bone_scale_map.tsv
driver_tsv=reports/assets/apf_bone_scale_drivers.tsv
mocap_bin=reports/assets/apf_mocap_corpus.bin
bone_bin=reports/assets/apf_bone_scale_map_corpus.bin
trace=reports/assets/apf_mocap_ghidra/mocap_trace.txt
pseudo=reports/assets/apf_mocap_ghidra/mocap_focused_pseudo_c.c

for required in \
  "$index" "$scene" "$nfl" tools/apf_mocap.py \
  tools/ghidra_scripts/apf/ApfMoCapTrace.java \
  docs/research/apf_mocap.md "$report" "$mocap_tsv" "$event_tsv" \
  "$sample_tsv" "$bone_tsv" "$driver_tsv" "$mocap_bin" "$bone_bin" \
  "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile tools/apf_mocap.py
temporary=$(mktemp -d /tmp/apf-mocap.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/apf_mocap.py "$index" \
  --scene-inventory "$scene" \
  --nfl-motion-inventory "$nfl" \
  --json "$temporary/inventory.json" \
  --mocap-tsv "$temporary/mocap.tsv" \
  --event-tsv "$temporary/events.tsv" \
  --sample-tsv "$temporary/samples.tsv" \
  --bone-tsv "$temporary/bones.tsv" \
  --driver-tsv "$temporary/drivers.tsv" \
  --mocap-bin "$temporary/mocap.bin" \
  --bone-bin "$temporary/bone.bin"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/mocap.tsv" "$mocap_tsv"
cmp "$temporary/events.tsv" "$event_tsv"
cmp "$temporary/samples.tsv" "$sample_tsv"
cmp "$temporary/bones.tsv" "$bone_tsv"
cmp "$temporary/drivers.tsv" "$driver_tsv"
cmp "$temporary/mocap.bin" "$mocap_bin"
cmp "$temporary/bone.bin" "$bone_bin"

test "$(sha256sum "$scene" | cut -d' ' -f1)" = \
  2243b5a3eb4dfcdebdda055e1a6fd9399b12b2704338f80ae4529d8476e85a17
test "$(sha256sum "$nfl" | cut -d' ' -f1)" = \
  7b1af7c95d3c2774c2129f2832c4a760c3c9df8330ed38c00ed5e00646210c1e
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  e477214f818be01891253683d731551c98a06bf3da0b396dc9de968b031dfb69
test "$(sha256sum "$mocap_bin" | cut -d' ' -f1)" = \
  ba6ddcddd018f579e4ddbe385d63b31b45cca3c2aaf450850cf0fce20344d15f
test "$(sha256sum "$bone_bin" | cut -d' ' -f1)" = \
  4dba548a093efd5a5746166d2637ace40024d8ea2577c1b793d254d5019939d0
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  3e9b2de50f05e826833b79855f23ddce85db3b1469ca22a49d84ca2015e5ad87
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  329e4f8070b7c3b49138c2c78756b654377cc6d4a6431586a1a39769d5063940

test "$(wc -c < "$mocap_bin")" -eq 1301080
test "$(wc -c < "$bone_bin")" -eq 2048
test "$(wc -l < "$mocap_tsv")" -eq 69
test "$(wc -l < "$event_tsv")" -eq 35
test "$(wc -l < "$sample_tsv")" -eq 6783
test "$(wc -l < "$bone_tsv")" -eq 145
test "$(wc -l < "$driver_tsv")" -eq 39

python3 - "$report" "$event_tsv" "$sample_tsv" "$bone_tsv" "$driver_tsv" <<'PY'
import csv
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "apf_mocap_inventory/v1"
assert report["pointer_rule"] == (
    "target = field_offset + signed_be32(stored_value) - 1; zero means null"
)
assert report["summary"] == {
    "alignment_tail_bytes": 256,
    "alignment_tail_length": {"maximum": 6, "minimum": 0, "unique_count": 4},
    "all_event_streams_uniquely_terminated": True,
    "all_full_clip_regions_reconstruct": True,
    "all_root_samples_bounded": True,
    "body_length": {"maximum": 175808, "minimum": 48, "unique_count": 23},
    "clips_with_events": 28,
    "compact_alias_count": 1,
    "corpus_sha256": "ba6ddcddd018f579e4ddbe385d63b31b45cca3c2aaf450850cf0fce20344d15f",
    "decoded_body_bytes": 1301080,
    "duration": {
        "maximum": 61.599998474121094,
        "minimum": 0.699999988079071,
        "unique_count": 22,
    },
    "event_count": 34,
    "event_id_counts": {"109": 26, "110": 2, "156": 2, "182": 2, "43": 2},
    "flags_counts": {
        "0x78007881": 1,
        "0x780078c1": 1,
        "0x89801e81": 37,
        "0x89801ec1": 29,
    },
    "full_clip_count": 67,
    "mirror_flag_count": 30,
    "mirror_pair_count": 30,
    "nonzero_alignment_tail_count": 28,
    "optional_packed_motion_bytes": 11328,
    "optional_packed_region_count": 6,
    "packed_motion_bytes": 1245136,
    "resource_count": 68,
    "root_sample_count": 6782,
    "sample_rate_counts": {"15": 66, "60": 1},
    "unique_body_sha256_count": 68,
    "unique_name_count": 68,
}
assert report["proved_layout"]["fixed_pointer_fields"] == [0x20, 0x24, 0x28, 0x2C]
assert report["proved_layout"]["root_vector_sample"]["record_stride"] == 6

sources = report["sources"]
assert [(item["outer_table_index"], item["mocap_count"], item["mocap_bytes"])
        for item in sources] == [(659, 8, 583176), (1310, 2, 5520), (1493, 58, 712384)]
assert [item["block0_decoded_sha256"] for item in sources] == [
    "f0f60830c078c510fd39ec0ac3f58e5f7e16b758a3efec40413e0da3349eed56",
    "a7ceb209338e0892cec168eecbc9fe4b0acd0ddf8c276a60fb4cb2547c613f58",
    "d8a44f3bc61f0d137e959c711bf5aa26d7d3730db8329063019313f239966f5b",
]

resources = report["resources"]
assert len(resources) == 68
cursor = 0
for item in resources:
    assert item["corpus_offset"] == cursor
    cursor += item["length"]
    regions = item["regions"]
    assert regions[0]["offset"] == 0 and regions[-1]["end"] == item["length"]
    assert all(left["end"] == right["offset"] for left, right in zip(regions, regions[1:]))
    assert sum(region["length"] for region in regions) == item["length"]
assert cursor == 1301080

clips = [item for item in resources if item["kind"] == "full_clip"]
aliases = [item for item in resources if item["kind"] == "compact_mirror_alias"]
assert len(clips) == 67 and len(aliases) == 1
assert all(item["variable_pointer_count"] == 0 for item in resources)
assert all(item["root_sample_stride"] == 6 for item in clips)
assert all(item["root_sample_bytes"] == item["sample_count"] * 6 for item in clips)
assert sum(item["event_count"] for item in clips) == 34
assert sum(item["sample_count"] for item in clips) == 6782
assert sum(any(pointer["field_offset"] == 0x2C and pointer["target"] is not None
               for pointer in item["pointers"]) for item in clips) == 6
alias = aliases[0]
assert alias["name"] == "hand_pose_mirror"
assert alias["alias_target_name"] == "hand_pose"
assert alias["alias_target_crc32"] == "0xfe2226ba"
assert alias["sha256"] == "4d419269ecb4fa37b14556fefe7bb365ec01f7fe7f8f86b7e026e8b75067b933"
assert len(report["mirror_pairs"]) == 30

bone = report["bone_scale_map"]
assert bone["summary"] == {
    "all_regions_reconstruct": True,
    "bone_record_count": 144,
    "corpus_bytes": 2048,
    "corpus_sha256": "4dba548a093efd5a5746166d2637ace40024d8ea2577c1b793d254d5019939d0",
    "distinct_driver_hash_count": 19,
    "distinct_unresolved_driver_hash_count": 5,
    "driver_tables_identical": True,
    "resolved_bone_name_count": 144,
    "resolved_driver_hash_count": 14,
    "resolved_driver_record_count": 28,
    "resource_count": 2,
    "scale_slot_count_per_map": 19,
    "scale_slot_record_count": 38,
    "unresolved_driver_hashes": [
        "0x3ca995ec", "0x7c6bff00", "0x99eab480", "0xa08d05db", "0xc0297a21"
    ],
    "unresolved_driver_record_count": 10,
}
assert [(item["name"], item["bone_count"], item["pointer_targets"])
        for item in bone["resources"]] == [
    ("lores", 52, [28, 236, 444, 528]),
    ("hires", 92, [28, 396, 764, 848]),
]

cross = report["cross_title_nfl2k5"]
assert cross["exact_apf_name_match_count"] == 7
assert cross["exact_nfl_resource_match_count"] == 7
assert [item["apf_name"] for item in cross["matches"]] == [
    "es213bk", "es263bl", "es264bl", "es267bl", "es268bl", "es269bl", "es270bl"
]
assert all(item["nfl_kind"] == "SMCD" and item["nfl_outer_index"] == 346
           for item in cross["matches"])
assert report["scene_inventory_source"]["sha256"] == (
    "2243b5a3eb4dfcdebdda055e1a6fd9399b12b2704338f80ae4529d8476e85a17"
)
assert all("PORTME:" in item for item in report["portme"])

def read_tsv(path):
    with Path(path).open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))

event_rows = read_tsv(sys.argv[2])
sample_rows = read_tsv(sys.argv[3])
bone_rows = read_tsv(sys.argv[4])
driver_rows = read_tsv(sys.argv[5])
assert len(event_rows) == 34 and len(sample_rows) == 6782
assert len(bone_rows) == 144 and all(row["bone_name"] for row in bone_rows)
assert len(driver_rows) == 38 and sum(not row["driver_name"] for row in driver_rows) == 10
assert {(row["map_name"], row["bone_name"]) for row in bone_rows
        if row["bone_hash"] == "0xbb538070"} == {("lores", "def_root"), ("hires", "def_root")}
print("APF_MOCAP_JSON_TSV_INVARIANTS_PASS")
PY

rg -q '^Program MD5: 217eea6084c3d03f0f1143802b1f5636$' "$trace"
rg -q '^Program language: PowerPC:BE:64:A2ALT-32addr$' "$trace"
rg -q '^0x82000BD0 raw=0x37800000 label=event fixed-point scale float=1.5258789E-5$' "$trace"
rg -q '^0x82000C30 raw=0x3E000000 label=root sample int16 scale float=0.125$' "$trace"
rg -q '^0x82000C44 raw=0x60900D71 label=SingleMoCap typed lookup hash$' "$trace"
rg -q '^0x84D11084 raw=0x60900D71 label=SingleMoCap runtime registry hash$' "$trace"
rg -q '^0x82005EEC raw=0x2ADC17FC label=compact alias name CRC32 hand_pose_mirror$' "$trace"
rg -q '^0x82005EF0 raw=0xFE2226BA label=compact alias target CRC32 hand_pose$' "$trace"
rg -q '^0x82003854 raw=0x1BBFAB40 label=BoneScaleMap descriptor type hash$' "$trace"
rg -q '^0x820D2B70 raw=0xA7701F00 label=CDAN type hash table value$' "$trace"
rg -q '^0x84E20594 raw=0xA7701F00 label=CDAN runtime registry hash$' "$trace"
rg -q '^HASH 0x60900D71 raw_hits=9$' "$trace"
rg -q '^HASH 0x1BBFAB40 raw_hits=3$' "$trace"
rg -q '^HASH 0xA7701F00 raw_hits=2$' "$trace"
rg -q '^HASH 0xC6ED33A2 raw_hits=13$' "$trace"
rg -q '^HASH 0xFE2226BA raw_hits=1$' "$trace"
rg -q '^0x8463B05C bl 0x84636ce8$' "$trace"
rg -q '^0x8463B0C0 bl 0x84636de8$' "$trace"
rg -q '^0x84975E78 lis r6,0x78ff$' "$trace"
rg -q '^0x84975E90 ori r6,r6,0xaf5$' "$trace"
rg -q '^0x84975EB8 lis r6,0x4f73$' "$trace"
rg -q '^0x84975EC8 ori r6,r6,0xc815$' "$trace"
rg -q '^CANDIDATE_FUNCTIONS count=27$' "$trace"

for address in \
  84636CE8 84636DE8 84638720 846389A8 84638C18 84638CC8 84638D68 \
  84639260 846392C8 8463B010 8463B098 84659638 846596B0 846597C0 \
  84979058 84A619E8; do
  rg -q "^/\\* 0x${address}:" "$pseudo"
done
rg -Fq 'puVar2 = param_1 + 8;' "$pseudo"
rg -Fq 'puVar2 = param_1 + 9;' "$pseudo"
rg -Fq 'puVar2 = param_1 + 10;' "$pseudo"
rg -Fq 'puVar2 = param_1 + 0xb;' "$pseudo"
rg -Fq '(*param_1 >> 0x11 & 0x1f)' "$pseudo"
rg -Fq '(*param_2 >> 9 & 0xff)' "$pseudo"
rg -Fq '*(uint **)(param_3 + 0x28)' "$pseudo"
rg -Fq 'FUN_84636ce8(*piVar3);' "$pseudo"
rg -Fq 'SingleMoCapInverseRelocator(*piVar3);' "$pseudo"
! rg -q 'PORTME: could not decompile' "$pseudo"

if [[ ${APF_MOCAP_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfMoCapTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/mocap_trace.txt" "$trace"
  cmp "$temporary/ghidra/mocap_focused_pseudo_c.c" "$pseudo"
  echo APF_MOCAP_GHIDRA_REGEN_PASS
fi

echo 'APF_MOCAP_VALIDATION_PASS resources=68 clips=67 alias=1 samples=6782 events=34 bones=144'
