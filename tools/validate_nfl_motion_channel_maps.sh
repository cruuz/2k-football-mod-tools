#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
report='reports/assets/nfl_motion_channel_maps.json'
tsv='reports/assets/nfl_motion_channel_maps.tsv'
trace='reports/assets/nfl_motion_channel_maps_ghidra/motion_channel_map_trace.txt'
pseudo='reports/assets/nfl_motion_channel_maps_ghidra/motion_channel_map_focused_pseudo_c.c'

for required in \
  "$xbe" "$xbe_header" \
  tools/nfl_motion_channel_maps.py tools/nfl_motion_sampler_inventory.py \
  tools/ghidra_scripts/NflMotionChannelMapTrace.java \
  docs/research/nfl_motion_channel_maps.md \
  "$report" "$tsv" "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile \
  tools/nfl_motion_channel_maps.py tools/nfl_motion_sampler_inventory.py
temporary=$(mktemp -d /tmp/nfl-motion-channel-maps.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_motion_channel_maps.py \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --json "$temporary/channel_maps.json" \
  --tsv "$temporary/channel_maps.tsv"

cmp "$temporary/channel_maps.json" "$report"
cmp "$temporary/channel_maps.tsv" "$tsv"
test "$(wc -l < "$tsv")" -eq 51
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  7d0fcb8d3d391c718308a61a20729f4fd2fb006430e0d5bbc0bc0e4e3ae4d4ae
test "$(sha256sum "$tsv" | cut -d' ' -f1)" = \
  fc4a6717d6deaa134db7a6e5e442865dabf7b15c5c2b7bb253e1dc75325c4242
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  0cd07b364fb3dad8a4990475735e7727209d5f45c2a6ea9b7e3221a28efde3f9
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  9def693ed4019d5b164cd08afae4b03ecf9423766b7c2a86f0176bcf4dd31d6a

python3 - "$report" "$tsv" "$xbe" "$xbe_header" "$trace" "$pseudo" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, tsv_path, xbe_path, header_path, trace_path, pseudo_path = map(
    Path, sys.argv[1:]
)
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_motion_channel_maps/v1"
assert report["executable_md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert report["summary"] == {
    "all_12_post_profile_bytes_zero": True,
    "all_14_post_map_bytes_zero": True,
    "all_mirror_relations_involutions": True,
    "all_packed_domains_dense": True,
    "logical_channel_count": 25,
    "map_count": 2,
    "object_group_a_enabled_channels": 23,
    "object_groups_b_c_enabled_channels": 21,
}
contract = report["controller_contract"]
assert contract["active_logical_channels"] == list(range(25))
assert contract["controller_low_mask"] == "0x000001ff"
assert contract["controller_high_mask"] == "0x01fffe00"
assert contract["controller_low_mask_offset"] == 8
assert contract["controller_high_mask_offset"] == 4
assert contract["channel_map_pointer_offset"] == 0x20
assert contract["adjacent_channel_profile_pointer_offset"] == 0x24
assert contract["channel_profile_consumer"] == "0x0031bd40 -> 0x0031bba0"
assert contract["sampler_function"] == "0x000df9b0"
assert contract["common_state_initializer"] == "0x00217d00"
assert contract["top_level_initializer"] == "0x00218090"

expected_functions = {
    "0x000df9b0": (0x9A, "ff077e38e19a1ed6ed61986793922272f15eb3acc4f59731ce84baa2a37fbd26"),
    "0x00217d00": (0x101, "9a960c22f5b0d69f9dff3596de7b7508c97b87c29b38a66060eb7eb6f9b98b35"),
    "0x00217e10": (0x9A, "af2e563d0ada69f608f78bc44b329b8327705f8ca76d7de08748b78046c9b460"),
    "0x00217eb0": (0x6F, "c58daedb47eead40708b3edcc5904b5c704769a7a509185322944cb34aca73fe"),
    "0x00217f20": (0x6F, "229362ded28d90e505317da57306fec0d660440910cd644484145fd1520c13d5"),
    "0x00218090": (0x35, "e21522523cf5432bf007832f0fd6912a17dd759d434d908f4042ff656a72d470"),
    "0x0031bba0": (0x8D, "d14dc11b89d99c90bd1b65bf79b80c948dd0b605dfb7f41db2f09ed8eeb7636e"),
    "0x0031bd40": (0x14A, "1c7add3843f5defa243582ea947912745e4b3b5338b95ece93ea029cae77a791"),
}
assert {
    key: (value["size"], value["sha256"])
    for key, value in report["function_hashes"].items()
} == expected_functions

maps = report["maps"]
assert len(maps) == 2
expected_maps = (
    {
        "name": "object_group_a",
        "va": "0x0051cd70",
        "initializers": ["0x00217e10"],
        "channel_profile_va": "0x0051cfa0",
        "profile_sha256": "6d5cef473c8f3c5d1e0860e154cfda696bd7ac7497537cc8d06af79c6d4404bf",
        "sha256": "9d1b0670498bde0a18ee06d0270c1a3e54793638f3671b050b4168636240a0d3",
        "enabled": 23,
        "disabled": [16, 21],
        "self": [0, 9, 10, 11, 12],
        "pairs": [[1, 5], [2, 6], [3, 7], [4, 8], [13, 18], [14, 19], [15, 20], [17, 22], [23, 24]],
    },
    {
        "name": "object_groups_b_c",
        "va": "0x0051d010",
        "initializers": ["0x00217eb0", "0x00217f20"],
        "channel_profile_va": "0x0051d240",
        "profile_sha256": "e233fa6ada7c8b5ddd9f84f24858d13943ab7a4b40e5063bd7d1a9db39678e8c",
        "sha256": "39a441532daab4cdbe4ff777641021bc179da9a5a69d43a94cdcb45fcc21e435",
        "enabled": 21,
        "disabled": [15, 17, 21, 23],
        "self": [0, 9, 10, 11, 12],
        "pairs": [[1, 5], [2, 6], [3, 7], [4, 8], [13, 19], [14, 20], [16, 22], [18, 24]],
    },
)
for item, expected in zip(maps, expected_maps):
    assert item["name"] == expected["name"]
    assert item["va"] == expected["va"]
    assert item["initializers"] == expected["initializers"]
    assert item["channel_profile_va"] == expected["channel_profile_va"]
    profile = item["channel_profile"]
    assert profile["float_count"] == 25
    assert profile["sha256"] == expected["profile_sha256"]
    assert profile["zero_tail_length"] == 12
    assert len(profile["values"]) == 25
    assert all(0.0 <= float(value) <= 1.0 for value in profile["values"])
    assert "callee does not read that stack argument" in profile["semantic_status"]
    assert item["sha256"] == expected["sha256"]
    assert item["enabled_channel_count"] == expected["enabled"]
    assert item["disabled_logical_channels"] == expected["disabled"]
    assert item["self_mirrored_logical_channels"] == expected["self"]
    assert item["bilateral_logical_channel_pairs"] == expected["pairs"]
    assert item["zero_tail_length_to_64_bytes"] == 14
    enabled = [entry for entry in item["entries"] if entry["enabled"]]
    assert len(item["entries"]) == 25
    assert sorted(entry["normal_packed_index"] for entry in enabled) == list(range(expected["enabled"]))
    assert sorted(entry["mirrored_packed_index"] for entry in enabled) == list(range(expected["enabled"]))
    partner = {entry["logical_channel"]: entry["mirror_logical_partner"] for entry in enabled}
    assert all(partner[other] == logical for logical, other in partner.items())
assert all("PORTME:" in value for value in report["portme"])

with tsv_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 50
assert [int(row["logical_channel"]) for row in rows[:25]] == list(range(25))
assert [int(row["logical_channel"]) for row in rows[25:]] == list(range(25))
assert sum(row["enabled"] == "True" for row in rows[:25]) == 23
assert sum(row["enabled"] == "True" for row in rows[25:]) == 21

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

assert at(0x0051CD70, 50).hex() == maps[0]["raw_hex"]
assert at(0x0051D010, 50).hex() == maps[1]["raw_hex"]
assert at(0x0051CD70 + 50, 14) == bytes(14)
assert at(0x0051D010 + 50, 14) == bytes(14)
for item in maps:
    profile_va = int(item["channel_profile_va"], 16)
    profile_raw = at(profile_va, 100)
    assert profile_raw.hex() == item["channel_profile"]["raw_hex"]
    assert hashlib.sha256(profile_raw).hexdigest() == item["channel_profile"]["sha256"]
    assert at(profile_va + 100, 12) == bytes(12)
for key, (size, digest) in expected_functions.items():
    assert hashlib.sha256(at(int(key, 16), size)).hexdigest() == digest

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "MAP_0051CD70=00000105020603070408050106020703080409090a0a0b0b0c0c0d110e120f13ffff1014110d120e130fffff1410151616150000000000000000000000000000",
    "MAP_0051D010=00000105020603070408050106020703080409090a0a0b0b0c0c0d110e12ffff0f13ffff1014110d120effff130fffff14100000000000000000000000000000",
    "CHANNEL_PROFILE_0051CFA0=0000803f3333733f0000403f9a99993e9a99193e3333733f0000403f9a99993e9a99193e9a99193f0000003fcdcc4c3ecdcccc3d0000003fcdcccc3e9a99993ecdcccc3dcdcc4c3d0000003fcdcccc3e9a99993ecdcccc3dcdcc4c3dcdcccc3dcdcccc3d000000000000000000000000",
    "CHANNEL_PROFILE_0051D240=0000803f6666663f3333333f9a99993ecdcc4c3e6666663f3333333f9a99993ecdcc4c3e6666663f3333333fcdcccc3e9a99993ecdcc4c3f3333333f9a99193f0000003f9a99993ecdcc4c3ecdcc4c3f3333333f9a99193f0000003f9a99993ecdcc4c3e000000000000000000000000",
    "0x000DF9D6 INC EDI owner=0x000DF9B0:FUN_000df9b0",
    "0x000DF9DC MOV AL,byte ptr [EDI] owner=0x000DF9B0:FUN_000df9b0",
    "0x000DFA00 ADD EDI,0x2 owner=0x000DF9B0:FUN_000df9b0",
    "0x00217E55 MOV dword ptr [ESI + -0x4],0x1fffe00 owner=0x00217E10:FUN_00217e10",
    "0x00217E5C MOV dword ptr [ESI],0x1ff owner=0x00217E10:FUN_00217e10",
    "0x00217E69 MOV dword ptr [ESI + 0x18],0x51cd70 owner=0x00217E10:FUN_00217e10",
    "0x00217E70 MOV dword ptr [ESI + 0x1c],0x51cfa0 owner=0x00217E10:FUN_00217e10",
    "0x00217EF6 MOV dword ptr [ESI + 0x18],0x51d010 owner=0x00217EB0:FUN_00217eb0",
    "0x00217EFD MOV dword ptr [ESI + 0x1c],0x51d240 owner=0x00217EB0:FUN_00217eb0",
    "0x00217F66 MOV dword ptr [ESI + 0x18],0x51d010 owner=0x00217F20:FUN_00217f20",
    "0x00217F6D MOV dword ptr [ESI + 0x1c],0x51d240 owner=0x00217F20:FUN_00217f20",
    "0x002180AF CALL 0x00217e10 owner=0x00218090:FUN_00218090",
    "0x002180B4 CALL 0x00217eb0 owner=0x00218090:FUN_00218090",
    "0x002180B9 CALL 0x00217f20 owner=0x00218090:FUN_00218090",
    "0x0031BDA4 MOV EDX,dword ptr [EBP + 0x24] owner=0x0031BD40:FUN_0031bd40",
    "0x0031BDAC PUSH EDX owner=0x0031BD40:FUN_0031bd40",
    "0x0031BDB2 CALL 0x0031bba0 owner=0x0031BD40:FUN_0031bd40",
    "0x0031BC2A RET 0x4 owner=0x0031BBA0:FUN_0031bba0",
):
    assert exact in trace, exact
for address in ("000DF9B0", "00217D00", "00217E10", "00217EB0", "00217F20", "00218090", "0031BBA0", "0031BD40"):
    assert f"/* 0x{address}:" in pseudo
assert pseudo.count("/* 0x") == 8
assert "// PORTME: could not decompile function at " not in pseudo
assert "puVar1[6] = &DAT_0051cd70;" in pseudo
assert pseudo.count("puVar1[6] = &DAT_0051d010;") == 2

print("NFL_MOTION_CHANNEL_MAPS_JSON_XBE_GHIDRA_ASSERTIONS_PASS")
PY

if [[ ${NFL_MOTION_CHANNEL_MAPS_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflMotionChannelMapTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/motion_channel_map_trace.txt" "$trace"
  cmp "$temporary/ghidra/motion_channel_map_focused_pseudo_c.c" "$pseudo"
  echo NFL_MOTION_CHANNEL_MAPS_GHIDRA_REGEN_PASS
fi

echo 'NFL_MOTION_CHANNEL_MAPS_VALIDATION_PASS maps=2 logical=25 enabled=23/21'
