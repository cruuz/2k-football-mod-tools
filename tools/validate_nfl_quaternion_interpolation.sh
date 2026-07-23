#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
report='reports/assets/nfl_quaternion_interpolation.json'
table='reports/assets/nfl_quaternion_interpolation_sine_table.tsv'
vectors='reports/assets/nfl_quaternion_interpolation_vectors.tsv'
trace='reports/assets/nfl_quaternion_interpolation_ghidra/nfl_quaternion_interpolation_trace.txt'
pseudo='reports/assets/nfl_quaternion_interpolation_ghidra/nfl_quaternion_interpolation_focused_pseudo_c.c'
native_table='src/recovered/nfl2k5/quaternion_interpolation_table.inc'

for required in \
  "$xbe" "$xbe_header" "$report" "$table" "$vectors" "$trace" "$pseudo" \
  tools/nfl_quaternion_interpolation.py \
  tools/nfl_quaternion_interpolation_native_validate.py \
  tools/ghidra_scripts/NflQuaternionInterpolationTrace.java \
  include/recovered/nfl2k5/quaternion_interpolation.h \
  src/recovered/nfl2k5/quaternion_interpolation.c "$native_table" \
  tests/nfl_quaternion_interpolation_test.c \
  docs/research/nfl_quaternion_interpolation.md; do
  test -f "$required"
done

python3 -m py_compile \
  tools/nfl_quaternion_interpolation.py \
  tools/nfl_quaternion_interpolation_native_validate.py

temporary=$(mktemp -d /tmp/nfl-quaternion-interpolation.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 tools/nfl_quaternion_interpolation.py \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --json "$temporary/report.json" \
  --table-tsv "$temporary/table.tsv" \
  --vectors-tsv "$temporary/vectors.tsv" \
  --native-table-inc "$temporary/table.inc"

cmp "$temporary/report.json" "$report"
cmp "$temporary/table.tsv" "$table"
cmp "$temporary/vectors.tsv" "$vectors"
cmp "$temporary/table.inc" "$native_table"

test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  fed3e47373f3458f891fecb69356d59e01c44065c10f0f9335286cdd6b9b4412
test "$(sha256sum "$table" | cut -d' ' -f1)" = \
  fedf4019d039e1e605559777a3c2f219732013bada2f536a739eb6606eb8a9c7
test "$(sha256sum "$vectors" | cut -d' ' -f1)" = \
  8a60b9df750e0cf0a0306c6545e70a3fed41707b6169ca5505b146652277af17
test "$(sha256sum "$native_table" | cut -d' ' -f1)" = \
  3e3cf811ee863e73ead2721bf0764f7d9dc0ac15b00e06d6289de3487760a0e2
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  aca2c24dcacf66cd978826e14cf3502bce1a5d43cd284bc8e544c4f3105a6592
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  c2348843de17c074f732bed248a09adb01610edecceca2c1b57bd5d5ec9b8970

python3 - "$report" "$table" "$vectors" "$xbe" "$xbe_header" \
  "$trace" "$pseudo" "$native_table" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys

(
    report_path, table_path, vectors_path, xbe_path, header_path,
    trace_path, pseudo_path, native_table_path,
) = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_quaternion_interpolation/v1"
assert report["source"] == {
    "md5": "444064a9ec984dd29d2c05a43f5c96e8",
    "path": "extracted/ESPN NFL 2K5 (USA)/default.xbe",
}

function = report["function"]
assert function["entry_va"] == "0x003ca270"
assert function["call_site_count"] == 8
assert function["caller_function_count"] == 7
assert function["abi"] == {
    "callee_stack_pop_bytes": 8,
    "destination": "ECX: float[4]",
    "left": "EDX: const float[4]",
    "return": "void",
    "right": "stack+0x04: const float[4]",
    "t": "stack+0x08: float",
}
expected_functions = [
    ("0x00020b20", 9, "ae4a39f1f86ea5a10dc0f01ad19c2ede2c9ddf1aed58b048c690bc9f8fdebf83"),
    ("0x00020bc0", 25, "90a5b1475c2de02ca1952145e969543e7739cbf62f5b4505d4c940162c1c8a8d"),
    ("0x00020c00", 155, "ef4bbf2cca17dfd2d1dcfbb5159563b8064fcb4bb7558bc28516f6c2cd82ba86"),
    ("0x00021390", 119, "ea42325d019bb78b1f4d7aac6a6e3352c063601bb4a3435366201c4a985bbd54"),
    ("0x003c9d10", 9, "ae4a39f1f86ea5a10dc0f01ad19c2ede2c9ddf1aed58b048c690bc9f8fdebf83"),
    ("0x003c9d80", 36, "8d59c1b5c9eaaaadefa2f44e39a05113b915845345f86059cc726ccbeee68df8"),
    ("0x003ca270", 351, "eea9c9847d72a7b18b5581201d53c5021fdaa5c1e11f90a429f9b4583e74f65a"),
]
assert [(row["va"], row["size"], row["sha256"])
        for row in function["functions"]] == expected_functions
assert [row["call_va"] for row in function["call_sites"]] == [
    "0x0005cd16", "0x000df569", "0x000df6df", "0x000df80f",
    "0x000df887", "0x001c73f0", "0x001cd315", "0x001df680",
]
assert {row["owner_va"] for row in function["call_sites"]} == {
    "0x0005cc20", "0x000df450", "0x000df6a0", "0x000df700",
    "0x001c71d0", "0x001ccfa0", "0x001df430",
}

constants = report["constants"]
assert constants["linear_threshold"] == {
    "raw": "0x3f7ff2e5",
    "va": "0x004f24e8",
    "value": "0.99980002641677856",
}
assert constants["quarter_turn_units"]["raw"] == "0x46800000"
assert constants["half_turn_units"]["raw"] == "0x47000000"
assert constants["numerator_constant_1"]["raw"] == "0x4622f7e2"
assert constants["numerator_constant_2"]["raw"] == "0xc612150c"

sine = report["sine_table"]
assert sine == {
    "entry_count": 256,
    "entry_layout": "float32 base; float32 slope",
    "evaluation": "base[angle>>8] + uint16(angle) * slope[angle>>8]",
    "exhaustive_angle_count": 65536,
    "maximum_absolute_error_vs_sin": "3.7680100457904153e-05",
    "maximum_error_actual": "0.9998870217386866",
    "maximum_error_angle_units": 16512,
    "maximum_error_ideal": "0.9999247018391445",
    "rms_error_vs_sin": "1.81870735432979e-05",
    "sha256": "51f388051e96e2ba5a159303a9204614c0454b4badd4674f932830a89b441b9c",
    "size": 2048,
    "va": "0x004e53e8",
}
angle = report["angle_helper"]
assert angle["full_turn_units"] == 65536
assert angle["threshold_angle_units"] == 209
assert angle["sample_count"] == 65537
assert angle["binary64_model_mismatch_count_vs_ideal_rounded_acos"] == 177
assert angle["maximum_unit_error_vs_ideal_rounded_acos"] == 1
assert angle["maximum_radian_error_vs_ideal_acos"] == "4.8582300540944701e-05"

semantics = report["proved_semantics"]
assert "lane 0 is scalar" in semantics["component_convention"]
assert "world-axis names remain unproved" in semantics["component_convention"]
assert "only the right weight is negated" in semantics["shortest_path"]
assert "equality uses fixed slerp" in semantics["branch"]
assert "not normalized" in semantics["linear_weights"]
assert "low uint16" in semantics["angle_wrap"]
assert all(item.startswith("PORTME") for item in report["portme"])

reference = {row["id"]: row for row in report["reference_vectors"]}
assert len(reference) == 9
assert reference["identity"]["branch"] == "linear"
assert reference["antipodal"]["shortest_path_negated"] is True
assert reference["orthogonal_half"]["theta_units"] == 16384
assert reference["orthogonal_half"]["step_units"] == 8192
assert reference["threshold_equal"]["branch"] == "fixed_slerp"
assert reference["threshold_equal"]["theta_units"] == 209
assert reference["threshold_equal"]["step_units"] == 105
assert reference["threshold_above"]["branch"] == "linear"
assert reference["extrapolate_negative"]["step_units"] == -4096
assert reference["extrapolate_high"]["step_units"] == 20480

with table_path.open(encoding="utf-8", newline="") as stream:
    table_rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(table_rows) == 256
assert table_rows[0] == {
    "index": "0", "va": "0x004e53e8", "base_raw": "0x34f80a77",
    "base": "4.620121387688414e-07", "slope_raw": "0x38c90ab0",
    "slope": "9.5864175818860531e-05",
}
assert table_rows[-1]["va"] == "0x004e5be0"
assert table_rows[-1]["base_raw"] == "0xc0c90ab1"
assert table_rows[-1]["slope_raw"] == "0x38c90ab0"

with vectors_path.open(encoding="utf-8", newline="") as stream:
    vector_rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(vector_rows) == 9
assert [row["id"] for row in vector_rows] == list(reference)
assert vector_rows[4]["branch"] == "fixed_slerp"
assert vector_rows[5]["branch"] == "linear"

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

assert at(0x004F24E8, 4) == bytes.fromhex("e5f27f3f")
assert hashlib.sha256(at(0x004E53E8, 0x800)).hexdigest() == sine["sha256"]
for row in function["functions"]:
    assert hashlib.sha256(at(int(row["va"], 16), row["size"])).hexdigest() == row["sha256"]
for row in function["call_sites"]:
    call = int(row["call_va"], 16)
    encoded = at(call, 5)
    assert encoded.hex() == row["bytes"] and encoded[0] == 0xE8
    assert call + 5 + struct.unpack_from("<i", encoded, 1)[0] == 0x003CA270

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "0x00021390 PUSH ECX owner=0x00021390:FUN_00021390",
    "0x003C9D10 CVTTSS2SI EAX,dword ptr [ESP + 0x4]",
    "0x003C9D80 MOVZX EAX,word ptr [ESP + 0x4] owner=0x003C9D80:nfl_fixed_sine_table_eval",
    "0x003CA270 PUSH EBX owner=0x003CA270:FUN_003ca270",
    "0x003CA2B8 FCOMP float ptr [0x004f24e8]",
    "0x003CA2C3 JP 0x003ca37d",
    "0x003CA2CE CALL 0x00021390",
    "0x003CA305 CALL 0x003c9d10",
    "0x003CA317 SUB EDX,EAX",
    "0x003CA38F FCHS",
    "0x003CA3CC RET 0x8",
    "CALL_SITE 0x000DF80F owner=0x000DF700:FUN_000df700",
    "CALL_SITE 0x001DF680 owner=0x001DF430:FUN_001df430",
    "0x004F24E8 length=4 bytes=e5f27f3f",
    "0x004E53E8 length=2048 entries=256 sha256=51f388051e96e2ba5a159303a9204614c0454b4badd4674f932830a89b441b9c",
    "table[255] va=0x004E5BE0 base_raw=0xC0C90AB1 slope_raw=0x38C90AB0",
):
    assert exact in trace
assert trace.count("CALL_SITE ") == 8
assert "0x004E53E8 refs=" not in trace
assert "// PORTME: could not decompile function at " not in pseudo
assert pseudo.count("/* 0x") == 14
assert "float10 nfl_fixed_sine_table_eval(ushort param_1)" in pseudo
assert "void __fastcall FUN_003ca270" in pseudo

native_table = native_table_path.read_text(encoding="utf-8")
assert native_table.count("{UINT32_C(") == 256
assert "0x34F80A77" in native_table and "0xC0C90AB1" in native_table
print("NFL_QUATERNION_INTERPOLATION_JSON_XBE_GHIDRA_ASSERTIONS_PASS")
PY

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -Iinclude tests/nfl_quaternion_interpolation_test.c \
  src/recovered/nfl2k5/quaternion_interpolation.c -lm \
  -o "$temporary/native_test"
"$temporary/native_test"

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror \
  -fPIC -shared -Iinclude \
  src/recovered/nfl2k5/quaternion_interpolation.c -lm \
  -o "$temporary/libvc_nfl_quaternion_interpolation.so"
PYTHONPATH=tools python3 tools/nfl_quaternion_interpolation_native_validate.py \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --library "$temporary/libvc_nfl_quaternion_interpolation.so"

if [[ ${NFL_QUATERNION_INTERPOLATION_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflQuaternionInterpolationTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_quaternion_interpolation_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_quaternion_interpolation_focused_pseudo_c.c" "$pseudo"
  echo NFL_QUATERNION_INTERPOLATION_GHIDRA_REGEN_PASS
fi

echo 'NFL_QUATERNION_INTERPOLATION_VALIDATION_PASS vectors=65546 callers=7 table_angles=65536'
