#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
resource_scan='reports/assets/nfl2k5_resource_chunks_v2.json'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
report='reports/assets/nfl_bone_binding.json'
tsv='reports/assets/nfl_bone_binding.tsv'
trace='reports/assets/nfl_bone_binding_ghidra/nfl_bone_binding_trace.txt'
pseudo='reports/assets/nfl_bone_binding_ghidra/nfl_bone_binding_focused_pseudo_c.c'

for required in \
  "$index" "$resource_scan" "$xbe" "$xbe_header" \
  tools/nfl_bone_binding.py tools/nfl_motion_channel_maps.py \
  tools/nfl_motion_sampler_inventory.py tools/nfl_scne_inventory.py \
  tools/nfl_scene_probe.py tools/nfl_outer.py \
  tools/ghidra_scripts/NflBoneBindingTrace.java \
  docs/research/nfl_bone_binding.md \
  "$report" "$tsv" "$trace" "$pseudo"; do
  test -f "$required"
done

python3 -m py_compile \
  tools/nfl_bone_binding.py tools/nfl_motion_channel_maps.py \
  tools/nfl_motion_sampler_inventory.py tools/nfl_scne_inventory.py \
  tools/nfl_scene_probe.py tools/nfl_outer.py

temporary=$(mktemp -d /tmp/nfl-bone-binding.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_bone_binding.py "$index" \
  --resource-scan "$resource_scan" \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --json "$temporary/bone_binding.json" \
  --tsv "$temporary/bone_binding.tsv"

cmp "$temporary/bone_binding.json" "$report"
cmp "$temporary/bone_binding.tsv" "$tsv"
test "$(wc -l < "$tsv")" -eq 51
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  241b7742f6217d0f736f101c9375a335ec1411a34c35e46599360907e291f350
test "$(sha256sum "$tsv" | cut -d' ' -f1)" = \
  008330222f5a344762baf86002fa259fc9e02a51485b35ea9ace40b9acf5075c
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  a5ab052d195b8dad960bd7e7066b6c117c055a39465e8355044bb70b00a8d45e
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  04579cf72d51708db26a724b6572c16460d08c420051fb6a3966897981cfba01

python3 - "$report" "$tsv" "$trace" "$pseudo" <<'PY'
import csv
import json
from pathlib import Path
import sys

report_path, tsv_path, trace_path, pseudo_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_bone_binding/v1"
assert report["executable_md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert report["summary"] == {
    "all_disabled_channels_are_bilateral_transform_pairs": True,
    "all_enabled_mirror_partners_match_named_transforms": True,
    "all_non_root_parent_entries_match": True,
    "coach_scene_count": 36,
    "coach_transform_copy_count": 72,
    "logical_channel_count": 25,
    "named_binding_count": 50,
    "player_transform_copy_count": 1,
    "referee_transform_copy_count": 2,
    "shared_transform_copy_count": 74,
    "skeleton_family_count": 2,
}

families = report["skeleton_families"]
assert [item["name"] for item in families] == [
    "player_lo_body", "referee_coach_body"
]
player_names = [
    "root", "lfemur", "ltibia", "lfoot", "ltoes",
    "rfemur", "rtibia", "rfoot", "rtoes", "waist",
    "thorax", "neck", "head", "lcollar", "lhumerus",
    "lelbow", "lwrist", "lhand", "rcollar", "rhumerus",
    "relbow", "rwrist", "rhand", "lshoulderpad", "rshoulderpad",
]
player_parents = [
    -1, 0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11,
    10, 13, 14, 15, 16, 10, 18, 19, 20, 21, 10, 10,
]
shared_names = [
    "root", "lfemur", "ltibia", "lfoot", "ltoes",
    "rfemur", "rtibia", "rfoot", "rtoes", "waist",
    "thorax", "neck", "head", "lcollar", "lhumerus",
    "ltwist", "lelbow", "lwrist", "lhand", "rcollar",
    "rhumerus", "rtwist", "relbow", "rwrist", "rhand",
]
shared_parents = [
    -1, 0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11,
    10, 13, 14, 15, 16, 17, 10, 19, 20, 21, 22, 23,
]
for family, names, parents in zip(
    families, (player_names, shared_names), (player_parents, shared_parents)
):
    transforms = family["transforms"]
    assert [item["index"] for item in transforms] == list(range(25))
    assert [item["name"] for item in transforms] == names
    assert [item["parent_index"] for item in transforms] == parents
    bindings = family["bindings"]
    assert [item["logical_channel"] for item in bindings] == list(range(25))
    assert [item["transform_index"] for item in bindings] == list(range(25))
    assert [item["bone_name"] for item in bindings] == names
    assert all(item["logical_channel"] == item["transform_index"] for item in bindings)
    assert all(item["mirror_evidence"] in {
        "enabled_map_partner_matches_transform_name_partner",
        "both_transform_name_partners_disabled",
    } for item in bindings)

assert families[0]["channel_map_va"] == "0x0051cd70"
assert families[0]["parent_table_va"] == "0x0051cda8"
assert families[1]["channel_map_va"] == "0x0051d010"
assert families[1]["parent_table_va"] == "0x0051d048"
assert [item["logical_channel"] for item in families[0]["bindings"] if not item["enabled"]] == [16, 21]
assert [item["logical_channel"] for item in families[1]["bindings"] if not item["enabled"]] == [15, 17, 21, 23]
assert [item["logical_channel"] for item in families[0]["bindings"] if item["direct_callback_slot_witness"]] == [16, 17, 21, 22]
assert [item["logical_channel"] for item in families[1]["bindings"] if item["direct_callback_slot_witness"]] == [14, 15, 17, 20, 21, 23]

player_copies = families[0]["source_copies"]
assert [(x["outer_index"], x["chunk_index"], x["scene_name"], x["shape_name"])
        for x in player_copies] == [(3, 113, "lo_body", "LO_res")]
referee_copies = families[1]["referee_source_copies"]
assert [(x["outer_index"], x["chunk_index"], x["scene_name"], x["shape_name"])
        for x in referee_copies] == [
    (346, 109, "referee", "ref_high"),
    (346, 109, "referee", "ref_low"),
]
coach_copies = families[1]["coach_source_copies"]
assert len(coach_copies) == 72
assert {x["outer_index"] for x in coach_copies} == set(range(348, 384))
assert {x["shape_name"] for x in coach_copies} == {"coachBodyGrp1", "coachLodGrp1"}
assert all(x["scene_name"] == "coach" and x["transform_count"] == 25
           for x in coach_copies)

contract = report["executable_contract"]
parents = contract["parent_tables"]
assert parents["player"]["sha256"] == "5229c0bcd410de993a90ff714c1fb9380a71e0ac80036281989394a44723a14c"
assert parents["referee_coach"]["sha256"] == "36f2e261ebe9eed9b486a153da5e7df968bad9f41ea60c1e35ed792f8c1d9bed"
assert parents["player"]["values"] == [0 if x < 0 else x for x in player_parents]
assert parents["referee_coach"]["values"] == [0 if x < 0 else x for x in shared_parents]
lookups = contract["transform_lookup_string_tables"]
assert [x["value"] for x in lookups["player"]["entries"]] == ["head", "lhand", "rhand"]
assert [x["value"] for x in lookups["coach"]["entries"]] == ["ltwist", "lwrist", "rtwist", "rwrist"]
assert [x["value"] for x in lookups["referee"]["entries"]] == ["ltwist", "lwrist", "rtwist", "rwrist"]

expected_functions = {
    "0x00021930": (0x04, "916ae10aa3fd76a4d5b25b2fb66e9df0fd04957c7ab10930268d1ed7808be689"),
    "0x00023690": (0x13, "1f469b6ea101dcb58c02337b751871e99a4e2671be71120c480625f3aa112e23"),
    "0x000236b0": (0x46, "73f4b47bd1f01a64b01b913a9e0a9b0f607a0e543e9ce65ae3f6bc03fbaf71fe"),
    "0x00023710": (0x1B, "bb938b552a12938da861355e9d474546ebbc7f91ebca15de9dc7ff76911d4315"),
    "0x00023730": (0x04, "071446420e131004120ac73567fa906ee67b4bde7cc93d64e2c51edf3b6b7fed"),
    "0x000901e0": (0x67, "5e74fa8a692df69e4890c6c47e103601c1d610d92ff96472e3b332e08cbbe7f4"),
    "0x00090570": (0xC6E, "9bf061b0ef8f48bba8601fd88bcffcb7c4f547cafd1ea121a04a168182f8e732"),
    "0x00091890": (0x1A, "b4e5af75639cfb7ee5e2717e77d0617a9e355aa471b56473c0c93c7d2b9e9b81"),
    "0x00095b40": (0x69, "2a4f32a92673b5ab4a89295daeed0180b8b610acfee8568551af267205740483"),
    "0x00095d40": (0x23E, "335c497e90042aadde80cd43186b8322f6dd4f5a76eb92a46b73290413bfed2b"),
    "0x00095fb0": (0x57, "f5c64113fb11905e4ec2e40ba068d53e6e78608f726b49ca704ea7f4f5ada86d"),
    "0x00096590": (0x69, "706352162195a2010e200a6daad38054983bfc04b248253b8368342b663fc645"),
    "0x00096600": (0x415, "90f3cd425b8d47e8eb352e996e977c3600cc29cf0803f6783724e31291b309f9"),
    "0x00096a80": (0x4C, "22c79b223bd234a8f51a1f50dfcf23ec79f2ae2c601fd4fd6476e97003f93c70"),
    "0x000df700": (0x1A5, "5dce74744c2ede4ab231d61753c73909c634c8c85f9474699b5f6588bedc48d9"),
    "0x002176d0": (0xC3, "d17b0dd1e4f7334949be84c5e984812614ae63c48e215f04a3af7ca6050660ae"),
}
assert {key: (value["size"], value["sha256"])
        for key, value in contract["function_hashes"].items()} == expected_functions
assert all("PORTME:" in line for line in report["portme"])

with tsv_path.open(newline="", encoding="utf-8") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 50
assert [(int(row["logical_channel"]), row["bone_name"])
        for row in rows[:25]] == list(enumerate(player_names))
assert [(int(row["logical_channel"]), row["bone_name"])
        for row in rows[25:]] == list(enumerate(shared_names))

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "PLAYER_TRANSFORM_NAMES_004EEAD4[1]=0x00E63EB4:lhand",
    "COACH_TRANSFORM_NAMES_004EFE8C[2]=0x00E65864:rtwist",
    "REFEREE_TRANSFORM_NAMES_004EFF34[3]=0x00E65D10:rwrist",
    "PLAYER_SKEL_NAME=skeleton",
    "PLAYER_SCNE_NAME=lo_body",
    "COACH_SCNE_NAME=coach",
    "REFEREE_SCNE_NAME=referee",
    "REFEREE_SHAPE_NAME=ref_low",
    "0x0002369A IMUL EAX,EAX,0x70 owner=0x00023690:FUN_00023690",
    "0x000236C5 MOV ECX,dword ptr [EAX + EBX*0x1 + 0x60] owner=0x000236B0:FUN_000236b0",
    "0x000DF82D ADD EDI,0x10 owner=0x000DF700:FUN_000df700",
    "0x00217755 MOV ESI,dword ptr [ESI*0x4 + 0x51cda8] owner=0x002176D0:FUN_002176d0",
    "0x0021775E MOV ESI,dword ptr [ESI*0x4 + 0x51d048] owner=0x002176D0:FUN_002176d0",
):
    assert exact in trace, exact
for address in (
    "00021930", "00023690", "000236B0", "00023710", "00023730",
    "000901E0", "00090570", "00091890", "00095B40", "00095D40",
    "00095FB0", "00096590", "00096600", "00096A80", "000DF700",
    "002176D0",
):
    assert f"/* 0x{address}:" in pseudo
assert pseudo.count("/* 0x") == 16
assert "// PORTME: could not decompile function at " not in pseudo
assert "// PORTME: recover transform record +0x00..+0x5f semantics." in pseudo

print("NFL_BONE_BINDING_JSON_CORPUS_XBE_GHIDRA_ASSERTIONS_PASS")
PY

if [[ ${NFL_BONE_BINDING_GHIDRA:-0} == 1 ]]; then
  env HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflBoneBindingTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_bone_binding_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_bone_binding_focused_pseudo_c.c" "$pseudo"
  echo NFL_BONE_BINDING_GHIDRA_REGEN_PASS
fi

echo 'NFL_BONE_BINDING_VALIDATION_PASS families=2 channels=25 named=50 shared_copies=74'
