#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
motion='reports/assets/nfl2k5_motion_inventory.json'
report='reports/assets/nfl_motion_sampler_inventory.json'
tsv='reports/assets/nfl_motion_sampler_roots.tsv'
trace='reports/assets/nfl_motion_sampler_ghidra/nfl_motion_sampler_trace.txt'
pseudo='reports/assets/nfl_motion_sampler_ghidra/nfl_motion_sampler_focused_pseudo_c.c'

for required in \
  "$index" "$xbe" "$xbe_header" "$motion" \
  tools/nfl_motion_sampler_inventory.py tools/nfl_outer.py \
  tools/nfl_motion_event_native_validate.py \
  tools/nfl_motion_pose_sample_native_validate.py \
  tools/nfl_packed_pose_native_validate.py \
  tools/nfl_trajectory_native_validate.py \
  tools/ghidra_scripts/NflMotionSamplerTrace.java \
  include/recovered/nfl2k5/motion_event.h \
  src/recovered/nfl2k5/motion_event.c tests/nfl_motion_event_test.c \
  include/recovered/nfl2k5/motion_pose_sample.h \
  src/recovered/nfl2k5/motion_pose_sample.c \
  tests/nfl_motion_pose_sample_test.c \
  include/recovered/nfl2k5/packed_pose.h \
  src/recovered/nfl2k5/packed_pose.c tests/nfl_packed_pose_test.c \
  include/recovered/nfl2k5/quaternion_interpolation.h \
  src/recovered/nfl2k5/quaternion_interpolation.c \
  src/recovered/nfl2k5/quaternion_interpolation_table.inc \
  include/recovered/nfl2k5/trajectory.h \
  src/recovered/nfl2k5/trajectory.c tests/nfl_trajectory_test.c \
  docs/research/nfl_motion_sampler.md \
  "$report" "$tsv" "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile \
  tools/nfl_motion_sampler_inventory.py \
  tools/nfl_motion_event_native_validate.py \
  tools/nfl_motion_pose_sample_native_validate.py \
  tools/nfl_packed_pose_native_validate.py \
  tools/nfl_trajectory_native_validate.py
temporary=$(mktemp -d /tmp/nfl-motion-sampler.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_motion_sampler_inventory.py "$index" \
  --motion-inventory "$motion" \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --json "$temporary/inventory.json" \
  --tsv "$temporary/roots.tsv"

cmp "$temporary/inventory.json" "$report"
cmp "$temporary/roots.tsv" "$tsv"
test "$(wc -l < "$tsv")" -eq 6069
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  6025e05201833e9222c05ba9a9c0c6f6ee9b27e054d37b372510b11290cf8f69
test "$(sha256sum "$tsv" | cut -d' ' -f1)" = \
  d5264a4f22a5d2fb92707c0b48956224bd8f5ef7e947e3f4916c84d35bfebf0d
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  8ff1078446978f13d3cb162dcfa5c99d27a7c200740cce1d854dcd42a67f3c10
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  38ceebe3cb09d1fcd653a3f28a15d59b1052924668f076b04739bbc34a54a453

python3 - "$report" "$tsv" "$xbe" "$xbe_header" "$trace" "$pseudo" <<'PY'
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, tsv_path, xbe_path, header_path, trace_path, pseudo_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_motion_sampler_inventory/v1"
assert report["summary"] == {
    "all_body_hashes_match": True,
    "all_event_streams_sentinel_terminated": True,
    "all_event_ticks_monotonic": True,
    "all_packed_quaternion_radicands_nonnegative": True,
    "auxiliary_packed_quaternion_count": 17311,
    "auxiliary_root_count": 171,
    "duration_gap_coordinate_maximum": "0.799999237",
    "duration_gap_coordinate_minimum": "-4.19616699e-05",
    "duration_within_final_sample_window_count": 6068,
    "event_count": 9024,
    "event_root_count": 1995,
    "events_after_clip_duration": 69,
    "main_packed_quaternion_count": 14073985,
    "maximum_quantized_three_square_sum": 382874,
    "quaternion_slack_all_zero_root_count": 4612,
    "quaternion_slack_bytes": 31404,
    "quaternion_slack_nonzero_bytes": 6549,
    "resource_count": 5198,
    "root_count": 6068,
    "roots_with_events_after_clip_duration": 63,
    "trajectory_record_count": 567075,
    "trajectory_slack_all_zero_root_count": 4766,
    "trajectory_slack_bytes": 3428,
    "trajectory_slack_nonzero_bytes": 2190,
}
domains = report["domains"]
assert domains["packed_quaternion_dwords_per_frame"] == {
    "1": 67, "2": 6, "3": 2, "4": 28, "10": 6,
    "15": 61, "21": 200, "23": 3566, "25": 126, "31": 2006,
}
assert domains["frame_count"] == {"minimum": 15, "maximum": 925, "unique_count": 186}
assert domains["flags"] == {
    "0x02": 1132, "0x06": 673, "0x08": 4127,
    "0x09": 8, "0x0a": 105, "0x0e": 23,
}
assert domains["sample_rate"] == {"12": 46, "15": 6022}
assert domains["header_byte_0d"] == {"0": 1064, "1": 5004}
assert domains["header_byte_0e"] == {"100": 6068}
assert domains["header_byte_0f"] == {"0": 6068}
assert domains["opaque_header_byte_01"] == {
    "minimum": 0, "maximum": 255, "unique_count": 256,
}
assert domains["opaque_word04_bits_08_31_unique_count"] == 1293
assert domains["runtime_mask_word08_unique_count"] == 38
assert domains["runtime_mask_word08_nonzero_count"] == 1866
assert domains["trajectory_stride"] == {"6": 4263, "8": 1805}
assert domains["quaternion_slack_length"] == {
    "0": 1738, "4": 1979, "8": 1181, "12": 1170,
}
assert domains["trajectory_slack_length"] == {"0": 4354, "2": 1714}
assert len(domains["event_id"]) == 59
assert sum(domains["event_id"].values()) == 9024
assert sum(domains["event_count_per_root"].values()) == 6068
assert sum(domains["packed_quaternion_omitted_component"].values()) == 14091296

assert report["executable_constants"] == {
    "event_tick_scale": {"raw": "0x37800000", "va": "0x004f24e0", "value": "1.52587891e-05"},
    "identity_channel_map": {
        "contract": "32 adjacent [index,index] signed-byte pairs",
        "sha256": "178505e1331407af55146fd1889a98544afec825cc9574356f3d9761c6d59957",
        "va": "0x004f24a0",
    },
    "quaternion_scale": {"raw": "0x3ab55fa3", "va": "0x004eea18", "value": "0.00138377061"},
    "trajectory_scale": {"raw": "0x3e000000", "va": "0x004f24e4", "value": "0.125"},
}
static = report["static_default_root"]
assert static["va"] == "0x007b2cfc"
assert static["packed_quaternion_dwords_per_frame"] == 21
assert static["frame_count"] == 35 and static["sample_rate"] == 15
assert static["flags"] == 2 and static["time_scale"] == "1"
assert static["duration"] == "2.25"
assert static["quaternion_bytes"] == 2940
assert static["trajectory_bytes"] == 280 and static["event_bytes"] == 8
assert static["pointer_targets"] == [
    "0x007b2180", "0x007b2068", "0x007b2060", "0x00000000",
]
assert all("PORTME:" in item for item in report["portme"])

with tsv_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 6068
assert Counter(int(row["packed_quaternion_dwords_per_frame"]) for row in rows) == {
    1: 67, 2: 6, 3: 2, 4: 28, 10: 6,
    15: 61, 21: 200, 23: 3566, 25: 126, 31: 2006,
}
assert Counter(int(row["trajectory_stride"]) for row in rows) == {6: 4263, 8: 1805}
assert sum(int(row["event_count"]) for row in rows) == 9024
assert sum(int(row["auxiliary_record_count"]) for row in rows) == 17311
assert sum(int(row["quaternion_bytes"]) // 4 for row in rows) == 14073985
for row in rows:
    frames = int(row["frame_count"])
    count = int(row["packed_quaternion_dwords_per_frame"])
    stride = int(row["trajectory_stride"])
    assert int(row["quaternion_bytes"]) == frames * count * 4
    assert int(row["quaternion_region_length"]) - int(row["quaternion_bytes"]) in (0, 4, 8, 12)
    assert int(row["trajectory_bytes"]) == frames * stride
    assert int(row["trajectory_region_length"]) - int(row["trajectory_bytes"]) in (0, 2)
    assert -0.00005 <= float(row["duration_gap"]) < 1.0

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
    (0x001685B0, 0x25): "474e2db5aa9abe9d469d53a089d67282513506c82902215f87fed2e19bfce2a9",
    (0x001B6B50, 0xF5): "7a8a6aee666fc177ee58353f56fb8040cd3f2bb9ad4ea6a810f5925eb45d64de",
    (0x002407D0, 0xC3): "143ae215e45d1ecba61f6ff611176e4efa8130ecbd8567e7c54745c245a460c3",
    (0x002408A0, 0xCF): "ff6796c68c797009ed7d89bf90947b327d675c3090a3bba1b7998ae09f431cd5",
    (0x000DED10, 0x118): "fd7acc9628dd7be8422dcb1ceea2ad2db87f208b236c5faff7cf81a382e52934",
    (0x000DEE30, 0x200): "260a3ae8bcf68d7e497aed99b57ff727d94e7dc11bac6bbfb5a5354acaceedec",
    (0x000DF030, 0x9B): "40a2eae8afc79452f5880d77f36b1576fb6a39ea6d06728baf10d7c9c8dd670a",
    (0x000DF8B0, 0xF5): "f284bc6bd648f595971667d8cdf3a81270b2d48e20fc4978b4aa5124a5bb396e",
    (0x000DF9B0, 0x9A): "ff077e38e19a1ed6ed61986793922272f15eb3acc4f59731ce84baa2a37fbd26",
    (0x0031B190, 0x24): "93a7c856398be8a551c49cf6cfc5ccbfd7c8fee8cfe0d603b2344a605e99b55d",
    (0x0031B910, 0x1A1): "8279f0cb422daa715da35a8bdfd808a0bdcac16117af542c5477c6b9f41cbca8",
    (0x0031C180, 0x2F3): "f9183d791868eff01a42b152a729865f296d262195e1b4150bb8ccb25dbf0ef3",
}
for key, digest in expected_hashes.items():
    assert hashlib.sha256(at(*key)).hexdigest() == digest

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "0x001685B0 PUSH ESI owner=0x001685B0:FUN_001685b0 refs=0x001B6C31",
    "0x000DED17 SHR ECX,0x14",
    "0x000DED1A AND ECX,0x3ff",
    "0x000DED20 SUB ECX,0x200",
    "0x000DED4B FMUL float ptr [0x004eea18]",
    "0x000DEDC0 SHR EAX,0x1e",
    "0x000DEE35 MOV ESI,dword ptr [EAX + 0x28]",
    "0x000DEE39 MOVZX EDI,byte ptr [EAX + 0xc]",
    "0x000DEE43 MOV CL,byte ptr [EAX + 0x4]",
    "0x000DEEB0 FMUL float ptr [0x004f24e4]",
    "0x000DF056 MOV ESI,dword ptr [ECX + 0x2c]",
    "0x000DF05B CMP ECX,-0x1",
    "0x000DF066 SHR EAX,0x8",
    "0x000DF079 FMUL float ptr [0x004f24e0]",
    "0x000DF0A5 AND ECX,0xff",
    "0x000DF902 MOVZX ESI,byte ptr [ECX]",
    "0x000DF905 MOV EDI,dword ptr [ECX + 0x24]",
    "0x000DF908 IMUL ESI,EAX",
    "0x000DF9E5 LEA ESI,[EBP + ECX*0x4]",
    "0x000DF9E9 CALL 0x000ded10",
    "0x0031B198 MOV EDX,dword ptr [EDX + 0x8]",
    "0x0031B1AB AND EAX,dword ptr [ESI + 0x8]",
    "0x004EEA18 length=4 bytes=a35fb53a",
    "0x004F24A0 length=64 bytes=00000101020203030404050506060707",
    "0x004F24E0 length=12 bytes=000080370000003ee5f27f3f",
    "0x007B2CFC length=52 bytes=1500230002000000010000000f016400",
):
    assert exact in trace

for address in (
    "001685B0", "001685E0", "001B6B50", "002407D0", "002408A0",
    "000DED10", "000DEE30", "000DF030", "000DF0D0", "000DF8B0",
    "000DF9B0", "0031B190", "0031B910", "0031C180",
):
    assert f"/* 0x{address}:" in pseudo
assert "// PORTME: could not decompile function at " not in pseudo
assert pseudo.count("/* 0x") == 36

print("NFL_MOTION_SAMPLER_JSON_XBE_GHIDRA_ASSERTIONS_PASS")
PY

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -Iinclude tests/nfl_packed_pose_test.c \
  src/recovered/nfl2k5/packed_pose.c -lm \
  -o "$temporary/nfl_packed_pose_native_test"
"$temporary/nfl_packed_pose_native_test"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -fPIC -shared -Iinclude src/recovered/nfl2k5/packed_pose.c -lm \
  -o "$temporary/libvc_nfl_packed_pose.so"
PYTHONPATH=tools python3 tools/nfl_packed_pose_native_validate.py \
  --index "$index" \
  --inventory "$motion" \
  --library "$temporary/libvc_nfl_packed_pose.so"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -Iinclude tests/nfl_trajectory_test.c \
  src/recovered/nfl2k5/trajectory.c \
  -o "$temporary/nfl_trajectory_native_test"
"$temporary/nfl_trajectory_native_test"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -fPIC -shared -Iinclude src/recovered/nfl2k5/trajectory.c \
  -o "$temporary/libvc_nfl_trajectory.so"
PYTHONPATH=tools python3 tools/nfl_trajectory_native_validate.py \
  --index "$index" \
  --inventory "$motion" \
  --library "$temporary/libvc_nfl_trajectory.so"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -Iinclude tests/nfl_motion_event_test.c \
  src/recovered/nfl2k5/motion_event.c -lm \
  -o "$temporary/nfl_motion_event_native_test"
"$temporary/nfl_motion_event_native_test"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -fPIC -shared -Iinclude src/recovered/nfl2k5/motion_event.c -lm \
  -o "$temporary/libvc_nfl_motion_event.so"
PYTHONPATH=tools python3 tools/nfl_motion_event_native_validate.py \
  --index "$index" \
  --inventory "$motion" \
  --library "$temporary/libvc_nfl_motion_event.so"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -Iinclude tests/nfl_motion_pose_sample_test.c \
  src/recovered/nfl2k5/motion_pose_sample.c \
  src/recovered/nfl2k5/packed_pose.c \
  src/recovered/nfl2k5/quaternion_interpolation.c -lm \
  -o "$temporary/nfl_motion_pose_sample_native_test"
"$temporary/nfl_motion_pose_sample_native_test"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -fPIC -shared -Iinclude \
  src/recovered/nfl2k5/motion_pose_sample.c \
  src/recovered/nfl2k5/packed_pose.c \
  src/recovered/nfl2k5/quaternion_interpolation.c -lm \
  -o "$temporary/libvc_nfl_motion_pose_sample.so"
PYTHONPATH=tools python3 tools/nfl_motion_pose_sample_native_validate.py \
  --index "$index" \
  --inventory "$motion" \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --library "$temporary/libvc_nfl_motion_pose_sample.so"

if [[ ${NFL_MOTION_SAMPLER_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflMotionSamplerTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_motion_sampler_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_motion_sampler_focused_pseudo_c.c" "$pseudo"
  echo NFL_MOTION_SAMPLER_GHIDRA_REGEN_PASS
fi

echo 'NFL_MOTION_SAMPLER_VALIDATION_PASS resources=5198 roots=6068 quaternions=14073985 composed_samples=18204 title_policy_samples=6068 events=9024'
