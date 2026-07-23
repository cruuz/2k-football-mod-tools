#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

apf_inventory=${APF_MOCAP_INVENTORY:-reports/assets/apf_mocap_inventory.json}
apf_corpus=${APF_MOCAP_CORPUS:-reports/assets/apf_mocap_corpus.bin}
nfl_sampler=${NFL_MOTION_SAMPLER_INVENTORY:-reports/assets/nfl_motion_sampler_inventory.json}
nfl_motion=${NFL_MOTION_INVENTORY:-reports/assets/nfl2k5_motion_inventory.json}
nfl_index=${NFL_INDEX:-extracted/ESPN NFL 2K5 (USA)/vc_53450030/0}
apf_pseudo=${APF_MOCAP_PSEUDO:-reports/assets/apf_mocap_ghidra/mocap_focused_pseudo_c.c}
nfl_pseudo=${NFL_MOTION_SAMPLER_PSEUDO:-reports/assets/nfl_motion_sampler_ghidra/nfl_motion_sampler_focused_pseudo_c.c}
report=reports/assets/motion_lineage_inventory.json
pairs=reports/assets/motion_lineage_pairs.tsv
packed=reports/assets/motion_lineage_apf_packed.tsv
doc=docs/research/motion_lineage.md

for required in \
  tools/motion_lineage.py tools/validate_motion_lineage.sh \
  "$apf_inventory" "$apf_corpus" "$nfl_sampler" "$nfl_motion" "$nfl_index" \
  "$apf_pseudo" "$nfl_pseudo" "$report" "$pairs" "$packed" "$doc"; do
  test -f "$required"
done

python3 -m py_compile tools/motion_lineage.py
temporary=$(mktemp -d /tmp/motion-lineage.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/motion_lineage.py \
  --apf-inventory "$apf_inventory" \
  --apf-corpus "$apf_corpus" \
  --nfl-sampler-inventory "$nfl_sampler" \
  --nfl-motion-inventory "$nfl_motion" \
  --nfl-index "$nfl_index" \
  --apf-pseudo "$apf_pseudo" \
  --nfl-pseudo "$nfl_pseudo" \
  --json "$temporary/inventory.json" \
  --pairs-tsv "$temporary/pairs.tsv" \
  --apf-packed-tsv "$temporary/apf-packed.tsv"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/pairs.tsv" "$pairs"
cmp "$temporary/apf-packed.tsv" "$packed"

test "$(sha256sum "$apf_inventory" | cut -d' ' -f1)" = \
  e477214f818be01891253683d731551c98a06bf3da0b396dc9de968b031dfb69
test "$(sha256sum "$apf_corpus" | cut -d' ' -f1)" = \
  ba6ddcddd018f579e4ddbe385d63b31b45cca3c2aaf450850cf0fce20344d15f
test "$(sha256sum "$nfl_sampler" | cut -d' ' -f1)" = \
  6025e05201833e9222c05ba9a9c0c6f6ee9b27e054d37b372510b11290cf8f69
test "$(sha256sum "$nfl_motion" | cut -d' ' -f1)" = \
  7b1af7c95d3c2774c2129f2832c4a760c3c9df8330ed38c00ed5e00646210c1e
test "$(sha256sum "$apf_pseudo" | cut -d' ' -f1)" = \
  329e4f8070b7c3b49138c2c78756b654377cc6d4a6431586a1a39769d5063940
test "$(sha256sum "$nfl_pseudo" | cut -d' ' -f1)" = \
  38ceebe3cb09d1fcd653a3f28a15d59b1052924668f076b04739bbc34a54a453
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  a7231d984918df907ef7c2fff949dd81c4b8026b29756296f40ee8f2841c2d4b
test "$(sha256sum "$pairs" | cut -d' ' -f1)" = \
  cf345cc187dc79f7270817c714abe2ad8329aafd881d0cc7cca695ba1340473c
test "$(sha256sum "$packed" | cut -d' ' -f1)" = \
  374e825356eada5a39ec2e387af78623abe3ad49722586214a378105c729df21

test "$(wc -l < "$pairs")" -eq 8
test "$(wc -l < "$packed")" -eq 68

python3 - "$report" "$pairs" "$packed" <<'PY'
import csv
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "cross_title_motion_lineage/v1"
assert len(report["normalized_root_field_lineage"]) == 9
assert report["shared_runtime_contracts"] == {
    "events": (
        "event_id=word&0xff; tick=word>>8; seconds=tick/65536/time_scale; "
        "0xffffffff terminator"
    ),
    "frame_coordinate": "sample_rate * seconds * time_scale",
    "relative_pointer_family": (
        "one-based field-local signed relative pointers; byte order and field offsets differ"
    ),
    "trajectory": (
        "three signed platform-endian int16 components, linear interpolation, "
        "each scaled by exactly 0.125"
    ),
}

full = report["full_corpus"]
assert full["apf"]["normal_clip_count"] == 67
assert full["apf"]["sample_rate_distribution"] == {"15": 66, "60": 1}
assert full["apf"]["trajectory_stride_distribution"] == {"6": 67}
assert full["apf"]["duration_window"] == {
    "all_within_final_sample_window": True,
    "clip_count": 67,
    "gap_maximum": "0.749999523163",
    "gap_minimum": "-9.53674316406e-06",
}
assert full["nfl"]["root_count"] == 6068
assert full["nfl"]["sample_rate_distribution"] == {"12": 46, "15": 6022}
assert full["nfl"]["trajectory_stride_distribution"] == {"6": 4263, "8": 1805}

packed_summary = report["apf_packed_pose_candidate"]
assert packed_summary == {
    "candidate_conservative_scale": "1.34869915235e-06",
    "candidate_maximum_scaled_square_sum": "0.687019081644",
    "candidate_unit_count": 155642,
    "candidate_unit_size": 8,
    "candidate_units_per_sample_distribution": {"15": 1, "23": 66},
    "clip_count": 67,
    "maximum_signed20_three_square_sum": 377692734386,
    "nfl_10bit_direct_test": {
        "big_endian_invalid_count": 50704,
        "big_endian_valid_count": 260580,
        "dword_count": 311284,
        "interpretation": (
            "both byte orders produce invalid radicands, so APF is not the NFL "
            "three-signed-10-bit dword codec"
        ),
        "little_endian_invalid_count": 35785,
        "little_endian_valid_count": 275499,
    },
    "optional_bytes_per_sample_distribution": {"16": 6},
    "packed_bytes": 1245136,
    "packed_bytes_per_sample_distribution": {"120": 1, "184": 66},
    "reserved_high_two_nonzero_count": 0,
    "selector_distribution": {"0": 40821, "1": 2102, "2": 3148, "3": 109571},
    "signed20_component_maximum": [515449, 511045, 515300],
    "signed20_component_minimum": [-513821, -514908, -515213],
    "status": (
        "8-byte frame-major pose-unit grammar proved; 2+2+20+20+20 "
        "smallest-three-like interpretation remains a candidate without APF decoder proof"
    ),
}

assert report["flag_lineage"]["apf"]["mirror"] == "flags & 0x40"
assert report["flag_lineage"]["nfl"]["mirror"] == "flags byte & 0x04"
assert report["event_id_domain_comparison"]["shared_observed_ids"] == [156]

pair_summary = report["pair_summary"]
assert pair_summary == {
    "all_counts_rates_time_scales_equal": True,
    "byte_identical_packed_stream_count": 0,
    "combined_trajectory_best_transform": {
        "permutation": [0, 1, 2],
        "signs": [1, 1, 1],
        "total_absolute_difference": 50731,
    },
    "combined_trajectory_runner_up_transform": {
        "permutation": [0, 1, 2],
        "signs": [-1, 1, 1],
        "total_absolute_difference": 657779,
    },
    "duration_raw_delta_distribution": {"-1": 5, "0": 2},
    "interpretation": (
        "the clips retain the same sampling grid and component order, but revised values "
        "and incompatible packed-pose widths preclude interchangeability"
    ),
    "pair_count": 7,
    "paired_frame_count": 2591,
    "sentinel_only_event_pair_count": 7,
}

names = ["es213bk", "es263bl", "es264bl", "es267bl", "es268bl", "es269bl", "es270bl"]
pairs = report["exact_name_pairs"]
assert [item["name"] for item in pairs] == names
assert [item["frame_count"] for item in pairs] == [925, 129, 509, 114, 482, 171, 261]
assert [item["apf_minus_nfl_duration_raw"] for item in pairs] == [-1, 0, -1, -1, -1, -1, 0]
assert [item["trajectory_exact_record_count"] for item in pairs] == [6, 0, 0, 0, 0, 0, 0]
assert all(item["apf_packed_bytes_per_frame"] == 184 for item in pairs)
assert all(item["apf_candidate_8byte_units_per_frame"] == 23 for item in pairs)
assert all(item["nfl_packed_quaternion_dwords_per_frame"] == 15 for item in pairs)
assert all(item["trajectory_best_transform"]["permutation"] == [0, 1, 2] for item in pairs)
assert all(item["trajectory_best_transform"]["signs"] == [1, 1, 1] for item in pairs)

decision = report["compatibility_decision"]
assert decision["shared_semantic_lineage"] is True
assert decision["byte_compatible_roots"] is False
assert decision["byte_compatible_packed_pose_codec"] is False
assert decision["safe_interchange_without_decode_and_reencode"] is False
assert all("PORTME:" in value for value in report["portme"])

def rows(path):
    with Path(path).open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, dialect="excel-tab"))

pair_rows = rows(sys.argv[2])
packed_rows = rows(sys.argv[3])
assert len(pair_rows) == 7 and [item["name"] for item in pair_rows] == names
assert len(packed_rows) == 67
assert sum(item["candidate_units_per_sample"] == "23" for item in packed_rows) == 66
assert sum(item["candidate_units_per_sample"] == "15" for item in packed_rows) == 1
assert {item["name"] for item in packed_rows if item["candidate_units_per_sample"] == "15"} == {
    "hand_pose"
}
assert all(item["reserved_high_two_nonzero"] == "0" for item in packed_rows)
assert sum(item["optional_bytes_per_sample"] == "16" for item in packed_rows) == 6
print("MOTION_LINEAGE_JSON_TSV_INVARIANTS_PASS")
PY

rg -q '^# NFL 2K5 to APF 2K8 motion lineage$' "$doc"
rg -q '155,642 eight-byte units' "$doc"
rg -q '50,704 invalid radicands' "$doc"
rg -q '35,785 after byte swapping' "$doc"
rg -q 'identity L1 difference is 50,731' "$doc"
rg -q '^// PORTME: recover the APF 8-byte packed pose decoder' "$doc"

echo 'MOTION_LINEAGE_VALIDATION_PASS pairs=7 paired_frames=2591 apf_units=155642'
