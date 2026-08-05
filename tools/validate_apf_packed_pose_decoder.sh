#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

inventory=${APF_MOCAP_INVENTORY:-reports/assets/apf_mocap_inventory.json}
corpus=${APF_MOCAP_CORPUS:-reports/assets/apf_mocap_corpus.bin}
report=reports/assets/apf_packed_pose_decoder_inventory.json
clips=reports/assets/apf_packed_pose_decoder_clips.tsv
trace=reports/assets/apf_packed_pose_decoder_ghidra/packed_pose_decoder_trace.txt
pseudo=reports/assets/apf_packed_pose_decoder_ghidra/packed_pose_decoder_focused_pseudo_c.c
vmx=reports/assets/apf_packed_pose_decoder_ghidra/packed_pose_decoder_vmx128.tsv
doc=docs/research/apf_packed_pose_decoder.md

for required in \
  "$inventory" "$corpus" "$report" "$clips" "$trace" "$pseudo" "$vmx" "$doc" \
  tools/apf_packed_pose_decoder.py tools/apf_packed_pose_vmx128_disasm.cpp \
  tools/ghidra_scripts/apf/ApfPackedPoseDecoderTrace.java \
  include/recovered/apf2k8/packed_pose.h \
  src/recovered/apf2k8/packed_pose.c tests/apf_packed_pose_test.c \
  tools/vendor/XenonRecomp/XenonUtils/disasm.cpp \
  tools/vendor/XenonRecomp/thirdparty/disasm/disasm.c \
  tools/vendor/XenonRecomp/thirdparty/disasm/ppc-dis.c; do
  test -f "$required"
done

test "$(sha256sum "$inventory" | cut -d' ' -f1)" = \
  adf7554d9fb1745048a044aa25462e9b11eb860ea788b9e6e1db82d346f0aa2b
test "$(sha256sum "$corpus" | cut -d' ' -f1)" = \
  ba6ddcddd018f579e4ddbe385d63b31b45cca3c2aaf450850cf0fce20344d15f
test "$(sha256sum tools/vendor/XenonRecomp/thirdparty/disasm/ppc-dis.c | cut -d' ' -f1)" = \
  352a4f17cdfe95fe284653c4ba343308557d4fb16b96bed3b136d6df54c16b58
test "$(git -C tools/vendor/XenonRecomp rev-parse HEAD)" = \
  ddd128bcca99fe8bfbb99bea583c972351fa6ace

python3 -m py_compile tools/apf_packed_pose_decoder.py
temporary=$(mktemp -d /tmp/apf-packed-pose-decoder.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

cc -std=c11 -O2 -w \
  -Itools/vendor/XenonRecomp/thirdparty/disasm \
  -c tools/vendor/XenonRecomp/thirdparty/disasm/disasm.c \
  -o "$temporary/disasm.o"
cc -std=c11 -O2 -w \
  -Itools/vendor/XenonRecomp/thirdparty/disasm \
  -c tools/vendor/XenonRecomp/thirdparty/disasm/ppc-dis.c \
  -o "$temporary/ppc-dis.o"
c++ -std=c++20 -O2 -Wall -Wextra -Wno-unused-function \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/disasm \
  tools/apf_packed_pose_vmx128_disasm.cpp \
  tools/vendor/XenonRecomp/XenonUtils/disasm.cpp \
  "$temporary/disasm.o" "$temporary/ppc-dis.o" \
  -o "$temporary/apf_packed_pose_vmx128_disasm"

"$temporary/apf_packed_pose_vmx128_disasm" "$trace" "$temporary/vmx.tsv"
cmp "$temporary/vmx.tsv" "$vmx"

python3 tools/apf_packed_pose_decoder.py \
  --inventory "$inventory" \
  --corpus "$corpus" \
  --trace "$trace" \
  --pseudo "$pseudo" \
  --vmx "$vmx" \
  --json "$temporary/inventory.json" \
  --clips-tsv "$temporary/clips.tsv"
cmp "$temporary/inventory.json" "$report"
cmp "$temporary/clips.tsv" "$clips"

test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  6eba188581d32a565fa5b9757fb0865ef20677eef7fdbe0ab8a1d21d2e8b15b7
test "$(sha256sum "$clips" | cut -d' ' -f1)" = \
  fcc867bb5b5998f4a18d4160ca090a291189b4cd082fa5b9a74ccce0724af6f3
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  4652c4a813c4456f7e1d06c24323afbd7d4bdc1d487a4112c7dad69b91d981a7
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  b735dbe49c677c8c3fd7dc482ff3ce16569a8391fb0bb4b9bb1238dc891ba913
test "$(sha256sum "$vmx" | cut -d' ' -f1)" = \
  94ca21c185ae71e261e4dc6fd2e1188f7cf019029cb25b70ad3e9eca14a80ccd

test "$(wc -l < "$clips")" -eq 68
test "$(wc -l < "$vmx")" -eq 977

python3 - "$report" "$clips" "$vmx" <<'PY'
import csv
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["schema"] == "apf_packed_pose_decoder/v1"
codec = report["proved_mode0_codec"]
assert codec["record_size_bytes"] == 8
assert codec["byte_order"] == "big-endian uint64"
assert codec["scale"] == {
    "binary_float": "0x1.7000000000000p-20",
    "decimal": "1.3709068298339844e-06",
    "derivation": (
        "vaddsws 11+12=23; vcfsx(...,5)=23/32; signed20 is shifted "
        "12 then vcfsx(...,31), giving signed20/2^19"
    ),
    "exact": "23/16777216",
}
assert codec["selector_to_output_lanes"] == {
    "0": ["packed_component_0", "packed_component_1", "packed_component_2", "reconstructed"],
    "1": ["packed_component_1", "packed_component_2", "reconstructed", "packed_component_0"],
    "2": ["packed_component_2", "reconstructed", "packed_component_0", "packed_component_1"],
    "3": ["reconstructed", "packed_component_0", "packed_component_1", "packed_component_2"],
}

corpus = codec["corpus"]
assert corpus["clip_count"] == 67
assert corpus["unit_count"] == 155642
assert corpus["packed_bytes"] == 1245136
assert corpus["selector4_distribution"] == {
    "0": 40821, "1": 2102, "2": 3148, "3": 109571
}
assert corpus["selector_upper_two_nonzero_count"] == 0
assert corpus["reconstructed_output_lane_distribution"] == {
    "0": 109571, "1": 3148, "2": 2102, "3": 40821
}
assert corpus["frame_group_distribution"] == [
    {
        "clip_count": 1,
        "count_bits_22_26": 0,
        "count_bits_27_31": 15,
        "units_per_frame": 15,
    },
    {
        "clip_count": 66,
        "count_bits_22_26": 6,
        "count_bits_27_31": 17,
        "units_per_frame": 23,
    },
]
assert corpus["maximum_unit"] == {
    "frame_index": 25,
    "maximum_scaled_three_square_sum": "0.70983026208961775",
    "maximum_signed_three_square_sum": 377692734386,
    "minimum_ideal_radicand": "0.29016973791038225",
    "packed_components_low_to_high": [322391, -345687, 392756],
    "packed_index": 14,
    "raw_be64": "0x35FE34AB9A94EB57",
    "resource": "frontend-fs190dqs_mirror",
    "selector4": 3,
    "unit_index": 589,
}
assert corpus["optional_packed_bytes_excluded_from_decoder_claim"] == 11328

interpolation = report["proved_interpolation"]
assert interpolation["classification"] == (
    "shortest-path polynomial SLERP with a linear near-equality fallback"
)
constants = {item["address"]: item["raw"] for item in interpolation["constants"]}
assert constants["0x82000BF0"] == "0xBAA57A2C"
assert constants["0x82000C0C"] == "0x3FC90FDA"
assert constants["0x82000C1C"] == "0x3FC90FDB"
assert constants["0x82000C2C"] == "0x3F7FF2E5"

mapping = report["proved_frame_and_output_mapping"]
assert mapping["flag_fields"] == {
    "mirror": "(flags>>6)&1",
    "packed_count_0": "(flags>>22)&0x1f",
    "packed_count_1": "(flags>>27)&0x1f",
    "sample_rate_hz": "(flags>>9)&0xff",
    "units_per_frame": "packed_count_0+packed_count_1",
}
assert mapping["default_map"] == [[0, index, index] for index in range(32)]
assert "lanes 2 and 3" in mapping["mode0_mirror"]
assert all("PORTME at 0x" in item for item in report["portme"])
assert report["export_status"].startswith("no glTF emitted")

with Path(sys.argv[2]).open("r", encoding="utf-8", newline="") as stream:
    clips = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(clips) == 67
assert sum(int(row["unit_count"]) for row in clips) == 155642
assert sum(int(row["packed_bytes"]) for row in clips) == 1245136
hand = [row for row in clips if row["name"] == "hand_pose"]
assert len(hand) == 1
assert (hand[0]["sample_rate_hz"], hand[0]["units_per_frame"], hand[0]["unit_count"]) == (
    "60", "15", "645"
)
assert all(row["units_per_frame"] == "23" for row in clips if row["name"] != "hand_pose")

with Path(sys.argv[3]).open("r", encoding="utf-8", newline="") as stream:
    vmx = {row["address"]: row for row in csv.DictReader(stream, dialect="excel-tab")}
assert vmx["0x84638488"]["mnemonic"] == "vupkd3d128"
assert vmx["0x84638488"]["operands"] == "v11,v11,24"
assert vmx["0x84639778"]["mnemonic"] == "vpkd3d128"
assert vmx["0x84639778"]["operands"] == "v13,v0,6,2,2"
assert vmx["0x8463A680"]["operands"] == "0x846385a8"
print("APF_PACKED_POSE_JSON_TSV_VMX_INVARIANTS_PASS")
PY

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -Iinclude tests/apf_packed_pose_test.c \
  src/recovered/apf2k8/packed_pose.c -lm \
  -o "$temporary/apf_packed_pose_native_test"
"$temporary/apf_packed_pose_native_test"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -fPIC -shared -Iinclude src/recovered/apf2k8/packed_pose.c -lm \
  -o "$temporary/libvc_apf_packed_pose.so"
PYTHONPATH=tools python3 - \
  "$inventory" "$corpus" "$temporary/libvc_apf_packed_pose.so" <<'PY'
import ctypes
import json
import math
from pathlib import Path
import sys

from apf_packed_pose_decoder import decode_reference


class NativePose(ctypes.Structure):
    _fields_ = [
        ("lanes", ctypes.c_float * 4),
        ("packed_components", ctypes.c_int32 * 3),
        ("ideal_radicand", ctypes.c_float),
        ("selector", ctypes.c_uint8),
    ]


inventory = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
corpus = Path(sys.argv[2]).read_bytes()
library = ctypes.CDLL(sys.argv[3])
decoder = library.vc_apf_mode0_decode_be_portable
decoder.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(NativePose)]
decoder.restype = ctypes.c_int

unit_count = 0
selectors: set[int] = set()
maximum_lane_error = 0.0
maximum_radicand_error = 0.0
for resource in inventory["resources"]:
    if resource["kind"] != "full_clip":
        continue
    region = next(
        item for item in resource["regions"] if item["role"] == "packed_motion"
    )
    start = int(resource["corpus_offset"]) + int(region["offset"])
    end = start + int(region["length"])
    assert (end - start) % 8 == 0
    for offset in range(start, end, 8):
        raw = corpus[offset : offset + 8]
        encoded = (ctypes.c_uint8 * 8).from_buffer_copy(raw)
        native = NativePose()
        assert decoder(encoded, ctypes.byref(native)) == 0
        selector, packed, lanes, radicand = decode_reference(
            int.from_bytes(raw, "big")
        )
        assert native.selector == selector
        assert list(native.packed_components) == packed
        maximum_lane_error = max(
            maximum_lane_error,
            *(abs(float(native.lanes[index]) - lanes[index]) for index in range(4)),
        )
        maximum_radicand_error = max(
            maximum_radicand_error,
            abs(float(native.ideal_radicand) - radicand),
        )
        assert all(math.isfinite(float(value)) for value in native.lanes)
        selectors.add(selector)
        unit_count += 1

assert unit_count == 155642
assert selectors == {0, 1, 2, 3}
assert maximum_lane_error < 2e-7
assert maximum_radicand_error < 2e-7
print(
    "APF_PACKED_POSE_NATIVE_FULL_CORPUS_PASS "
    f"units={unit_count} max_lane_error={maximum_lane_error:.9g} "
    f"max_radicand_error={maximum_radicand_error:.9g}"
)
PY

rg -q '^Program MD5: 217eea6084c3d03f0f1143802b1f5636$' "$trace"
rg -q '^Program language: PowerPC:BE:64:A2ALT-32addr$' "$trace"
rg -q '^MAP 31 0 31 31$' "$trace"
rg -q '^CONST_FLOAT 0x82000C2C raw=0x3F7FF2E5 ' "$trace"
rg -q '^RAW32 0x84638488 0x19785FF0$' "$trace"
rg -q '^RAW32 0x846385A8 0x152111D0$' "$trace"
rg -q '^RAW32 0x8463A680 0x4BFFDF29$' "$trace"

rg -Fq $'0x84638488\t0x19785FF0\tvupkd3d128\tv11,v11,24\t321' "$vmx"
rg -Fq $'0x84639778\t0x19BA0690\tvpkd3d128\tv13,v0,6,2,2\t313' "$vmx"
rg -Fq $'0x8463A394\t0x556856FE\trlwinm\tr8,r11,10,27,31\t833' "$vmx"
rg -Fq $'0x8463A39C\t0x55672EFE\trlwinm\tr7,r11,5,27,31\t833' "$vmx"

rg -Fq 'float scale = 23.0f / 16777216.0f;' "$pseudo"
rg -Fq 'static ApfPose4 apf_interpolate_mode0' "$pseudo"
rg -Fq 'if (mirror) *output = xor_float_sign_lanes_2_and_3(*output);' "$pseudo"
for address in 84638450 8463846C 846384D0 84638508 84638540 84638588 846385A8 846394D0 84639670 84639790 8463A328; do
  rg -q "PORTME: Ghidra truncated VMX128 function at 0x${address}" "$pseudo"
done
rg -Fq '// PORTME at 0x8463A4F0:' "$pseudo"
rg -Fq '// PORTME at 0x8463A52C:' "$pseudo"
rg -Fq '// PORTME at 0x8463A46C and 0x8463A684:' "$pseudo"

rg -Fq '## Worked, failed, and blocking' "$doc"
rg -Fq 'No bone-name meaning is inferred' "$doc"
rg -Fq 'no glTF' "$doc"

if [[ ${APF_PACKED_POSE_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" apf2k8 \
      -process default.xex -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts/apf" \
      -postScript ApfPackedPoseDecoderTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/packed_pose_decoder_trace.txt" "$trace"
  cmp "$temporary/ghidra/packed_pose_decoder_focused_pseudo_c.c" "$pseudo"
  "$temporary/apf_packed_pose_vmx128_disasm" \
    "$temporary/ghidra/packed_pose_decoder_trace.txt" \
    "$temporary/ghidra-vmx.tsv"
  cmp "$temporary/ghidra-vmx.tsv" "$vmx"
  echo APF_PACKED_POSE_GHIDRA_REGEN_PASS
fi

echo 'APF_PACKED_POSE_DECODER_VALIDATION_PASS clips=67 units=155642 bytes=1245136'
