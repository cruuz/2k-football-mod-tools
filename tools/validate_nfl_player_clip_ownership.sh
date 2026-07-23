#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
xbe_header='reports/headers/nfl2k5_xbe_header.json'
motion='reports/assets/nfl2k5_motion_inventory.json'
sampler='reports/assets/nfl_motion_sampler_inventory.json'
sampler_tsv='reports/assets/nfl_motion_sampler_roots.tsv'
pose='reports/assets/nfl_pose_matrix_apply.json'
pool='reports/assets/nfl_motion_object_pools.json'
bone='reports/assets/nfl_bone_binding.json'
player_pose='reports/assets/nfl_player_pose_native.json'
player_92140='reports/assets/nfl_player_92140_native.json'
post='reports/assets/nfl_player_postprocess.json'
root_report='reports/assets/nfl_referee_root_trajectory.json'
scne='reports/assets/nfl2k5_scne_inventory.json'
raw_skin='reports/assets/nfl_raw_skin_gltf_manifest.json'
meter_skin='reports/assets/nfl_meter_skin_gltf_manifest.json'
meter_skin_dir='assets/intermediate/nfl2k5/meter_skin_samples'
report='reports/assets/nfl_player_clip_ownership.json'
selectors='reports/assets/nfl_player_clip_ownership_selectors.tsv'
path_tsv='reports/assets/nfl_player_clip_ownership_path.tsv'
trace='reports/assets/nfl_player_clip_ownership_ghidra/nfl_player_clip_ownership_trace.txt'
pseudo='reports/assets/nfl_player_clip_ownership_ghidra/nfl_player_clip_ownership_focused_pseudo_c.c'
doc='docs/research/nfl_player_clip_ownership.md'

for required in \
  "$index" "$xbe" "$xbe_header" "$motion" "$sampler" "$sampler_tsv" \
  "$pose" "$pool" "$bone" "$player_pose" "$player_92140" "$post" \
  "$root_report" "$scne" "$raw_skin" "$meter_skin" \
  "$meter_skin_dir/0003_0113_lo_body_meter_skin.gltf" \
  "$meter_skin_dir/0003_0113_lo_body_meter_skin.bin" \
  "$report" "$selectors" "$path_tsv" "$trace" "$pseudo" "$doc" \
  tools/nfl_outer.py tools/nfl_player_clip_ownership.py \
  tools/ghidra_scripts/NflPlayerClipOwnershipTrace.java; do
  test -f "$required"
done

test "$(sha256sum tools/nfl_player_clip_ownership.py | cut -d' ' -f1)" = \
  39984445f271f49aa2ace463b9e2684824476bcad06067d8a03dd2217c492bd7
test "$(sha256sum tools/ghidra_scripts/NflPlayerClipOwnershipTrace.java | cut -d' ' -f1)" = \
  edf3b2be60c1dbfd45544d673d8eb2ef4f86caf8e12a9264e44b0e471e7968fc
test "$(sha256sum "$report" | cut -d' ' -f1)" = \
  d29a730121d08508b08419fa4861e7edc4d45318917a8d185d53c4ac135aa82e
test "$(sha256sum "$selectors" | cut -d' ' -f1)" = \
  a8031ddd134d4d01f4c487e4420654a08cc3652544c5fac13b9b7ce5e38601ac
test "$(sha256sum "$path_tsv" | cut -d' ' -f1)" = \
  26236feafb65450259ba55550c6897be269b367fc129be3096d65fa6052c054b
test "$(sha256sum "$trace" | cut -d' ' -f1)" = \
  c8d2793e8564ba8e1454b2da968f3ada9ec91c6eca0302cb86801c21136c6a23
test "$(sha256sum "$pseudo" | cut -d' ' -f1)" = \
  eaf23282ef61e36198fc6b9d42c87ff8e99287d328e4ab787d1541993798eb63
test "$(sha256sum "$doc" | cut -d' ' -f1)" = \
  742768c9612af803a8a145aaf8606a6520f1c7ddf6dbc44c3ccabe2c668f49b5

python3 -m py_compile tools/nfl_player_clip_ownership.py
temporary=$(mktemp -d /tmp/nfl-player-clip-ownership.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_player_clip_ownership.py "$index" \
  --motion-inventory "$motion" \
  --sampler-report "$sampler" \
  --sampler-tsv "$sampler_tsv" \
  --pose-report "$pose" \
  --pool-report "$pool" \
  --bone-report "$bone" \
  --player-pose-report "$player_pose" \
  --player-92140-report "$player_92140" \
  --player-postprocess-report "$post" \
  --root-report "$root_report" \
  --scne-report "$scne" \
  --raw-skin-report "$raw_skin" \
  --meter-skin-report "$meter_skin" \
  --meter-skin-dir "$meter_skin_dir" \
  --xbe "$xbe" \
  --xbe-header "$xbe_header" \
  --json "$temporary/report.json" \
  --selectors-tsv "$temporary/selectors.tsv" \
  --path-tsv "$temporary/path.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/selectors.tsv" "$selectors"
cmp "$temporary/path.tsv" "$path_tsv"
test "$(wc -l < "$selectors")" -eq 38
test "$(wc -l < "$path_tsv")" -eq 17

python3 - "$report" "$selectors" "$path_tsv" "$xbe" "$xbe_header" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

report_path, selectors_path, path_path, xbe_path, header_path, trace_path, pseudo_path, doc_path = map(Path, sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_player_clip_ownership/v1"
clip = report["selected_clip"]
assert clip["name"] == "ANM_CELEBRATE_USER_34"
assert (clip["outer_index"], clip["outer_id"], clip["chunk_index"], clip["chunk_offset"]) == (3092, "0xdaddb151", 163, 4151936)
assert clip["decoded_sha256"] == "a86c827b09db69990c4070cbb59d5c989db420a9d03427acd814823361a82e52"
assert clip["decoded_size"] == clip["stored_size"] == 9456
assert clip["root_offset"] == 76 and clip["pointer_targets"] == [888, 144, 128]
assert clip["packed_quaternion_dwords_per_frame"] == 23
assert clip["frame_count"] == 93 and clip["sample_rate_hz"] == 15
assert clip["flags"] == 2 and not clip["looping"] and not clip["mirrored"]
assert clip["duration_raw"] == "0x40c2aaab"
assert clip["quaternion_bytes"] == 8556 and clip["quaternion_region_bytes"] == 8568
assert clip["quaternion_slack_bytes"] == 12
assert clip["quaternion_slack_sha256"] == "15ec7bf0b50732b49f8228e07d24365338f9e3ab994b00af08e5a3bffe55fd8b"
assert clip["trajectory_stride"] == 8 and clip["trajectory_bytes"] == 744
assert clip["event_count"] == 3 and clip["event_bytes"] == 16
assert clip["selector_index"] == 2 and clip["selector_left_pointer_is_null"] is True
assert clip["selector_right_pointer_field_va"] == "0x0050cfe4"

selector = report["selector_table"]
assert selector["row_count"] == 37 and selector["nonempty_name_count"] == 70
assert selector["unique_name_count"] == 70 and selector["reused_name_count"] == 0
assert selector["all_nonempty_names_resolve_to_outer_3092"] is True
assert selector["selected_row_side_is_forced_right_because_left_is_null"] is True
assert selector["dynamic_index_2_producer_proved"] is False

runtime = report["runtime_ownership"]
assert runtime["namespace_name"] == "CELEBRATE"
assert runtime["channel_map_va"] == "0x0051cd70"
assert runtime["enabled_packed_channels"] == 23 and runtime["logical_channels"] == 25
assert runtime["disabled_callback_completed_channels"] == [16, 21]
assert runtime["player_pool_head_va"] == "0x00e60268" and runtime["player_pool_max_count"] == 22
assert runtime["selector_index_2_path_is_conditional"] is True
assert runtime["concrete_state_plus_a0_equals_one_proved"] is False

render = report["render_target_join"]
assert render["conditional_on_selector_index_2_and_playback_mode_1"] is True
assert render["lo_body_LO_res_reached"] is True
assert render["hi_body_HI_res_matrix_path_reached"] is True
assert render["hi_body_exact_skin_attachment_reached"] is False
assert render["local_postprocess_0x00092140_runs"] is True
assert render["hierarchy_wrapper_0x00093800_runs"] is True
assert render["current_postprocess_0x00093850_runs"] is True
calls = {row["callsite"]: row for row in render["current_postprocess_calls"]}
assert calls["0x0028e99d"]["mask_source"] == "EDX immediate 0x01ffe7ff"
assert calls["0x001dfadf"]["mask_source"] == "EDX immediate 0x00001800"
assert all(row["context_source"] == "ECX = *(actor+0x3c)" for row in calls.values())
assert render["current_postprocess_live_inputs"]["concrete_profile_and_scalar_values_proved"] is False

frame = report["frame_and_external_root"]
assert frame["raw_clip_root_may_be_flattened_directly"] is False
assert frame["live_external_transform"] == "actor+0x18"
assert frame["concrete_initial_actor_transform_proved"] is False
pipeline = report["portable_player_pipeline"]
assert pipeline["ordered_helper_calls"] == 127
assert pipeline["main_mask"] == "0x01ffe7ff" and pipeline["late_neck_head_mask"] == "0x00001800"
assert pipeline["masks_cover_all_25_channels_without_overlap"] is True
assert pipeline["current_postprocess_validation"] == {
    "cases": 116,
    "mask_cases": 29,
    "maximum_abs_difference": 3.81469727e-06,
    "validator": "tools/nfl_player_current_postprocess_native_validate.py",
}
assert pipeline["bit_identity_claimed"] is False

assets = report["mapped_player_assets"]
assert assets["lo_body"]["resource"] == [3, 113]
assert assets["lo_body"]["shape_name"] == "LO_res"
assert assets["lo_body"]["transform_count"] == 25
assert assets["lo_body"]["vertex_count"] == 5065
assert assets["lo_body"]["primitive_count"] == 111
assert assets["lo_body"]["skin_attachment_proved"] is True
assert assets["lo_body"]["canonical_gltf_sha256"] == "79a76bd011540ade1bbd68dc2aced1a0973a212bb08fcbff47e8956f6804c240"
assert assets["hi_body"]["resource"] == [3, 114]
assert assets["hi_body"]["shape_name"] == "HI_res"
assert assets["hi_body"]["transform_count"] == 62
assert assets["hi_body"]["primitive_count"] == 86
assert assets["hi_body"]["skin_attachment_proved"] is False
assert report["export_decision"]["animated_gltf_emitted"] is False
assert len(report["export_decision"]["required_before_emit"]) == 4
assert len(report["portme"]) == 7
assert all(item.startswith("// PORTME(") for item in report["portme"])

for pin in report["source_pins"].values():
    pinned = Path(pin["path"])
    assert hashlib.sha256(pinned.read_bytes()).hexdigest() == pin["sha256"], pinned

with selectors_path.open(encoding="utf-8", newline="") as stream:
    rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(rows) == 37
row2 = rows[2]
assert row2["row_va"] == "0x0050cfe0"
assert row2["left_name"] == "" and row2["left_match_count"] == "0"
assert row2["right_name"] == "ANM_CELEBRATE_USER_34"
assert row2["right_name_string_va"] == "0x00e8480c"
assert row2["right_outer_index"] == "3092" and row2["right_chunk_index"] == "163"
assert row2["opaque_s32"] == "21"
names = []
for row in rows:
    for side in ("left", "right"):
        if row[f"{side}_name"]:
            names.append(row[f"{side}_name"])
            assert row[f"{side}_match_count"] == "1"
            assert row[f"{side}_outer_index"] == "3092"
assert len(names) == len(set(names)) == 70

with path_path.open(encoding="utf-8", newline="") as stream:
    paths = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(paths) == 16
assert [int(row["step"]) for row in paths] == list(range(1, 17))
assert paths[0]["confidence"] == "exact_static_conditional_on_index_2"
assert paths[12]["confidence"] == "instruction_exact_runtime_initial_state_unproved"
assert paths[-1]["confidence"] == "instruction_exact_low_skin_exact_high_skin_unproved"

xbe = xbe_path.read_bytes()
header = json.loads(header_path.read_text(encoding="utf-8"))
assert hashlib.md5(xbe).hexdigest() == "444064a9ec984dd29d2c05a43f5c96e8"
def at(va, size):
    for section in header["sections"]:
        start = section["virtual_address"]
        if start <= va and va + size <= start + section["raw_size"]:
            offset = section["raw_address"] + va - start
            return xbe[offset:offset + size]
    raise AssertionError(hex(va))
for item in report["executable"]["ranges"]:
    start = int(item["start"], 16)
    end = int(item["end_exclusive"], 16)
    assert end - start == item["size"]
    assert hashlib.sha256(at(start, end - start)).hexdigest() == item["sha256"]

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for exact in (
    "Program MD5: 444064a9ec984dd29d2c05a43f5c96e8",
    "0x001685B5 MOV EDX,0x44434d53",
    "0x001B6BD7 LEA EAX,[EAX + EAX*0x2]",
    "0x001B6C1F MOV dword ptr [0x00be50c4],ECX",
    "0x001B6C27 MOV ECX,0xe8470c",
    "0x001B6C31 CALL 0x001685b0",
    "0x001B7511 MOV EDX,dword ptr [0x00be50c4]",
    "0x001B78DE CALL 0x002d6b70",
    "0x00217E12 MOV EDI,dword ptr [0x00e60268]",
    "0x00217E69 MOV dword ptr [ESI + 0x18],0x51cd70",
    "0x00217E77 MOV dword ptr [ESI + 0x30],0x91890",
    "0x0011A89D CALL 0x002180d0",
    "0x0011A8A2 CALL 0x0028ecf0",
    "0x0011A8B6 CALL 0x001dfaa0",
    "0x0028E4C2 MOV ESI,dword ptr [EDI + 0x18]",
    "0x0028E98C CALL 0x00093800",
    "0x0028E99D CALL 0x00093850",
    "0x001DFADF CALL 0x00093850",
    "0x0050CFC8 length=444 bytes=",
    "0x0051CD70 length=50 bytes=",
):
    assert exact in trace, exact
assert pseudo.count("// PORTME: could not decompile function at") == 2
assert "// PORTME: could not decompile function at 0x002DDB10" in pseudo
assert "// PORTME: could not decompile function at 0x002DE170" in pseudo
assert "/* 0x001B6B50:FUN_001b6b50 */" in pseudo
assert "/* 0x0028E360:FUN_0028e360 */" in pseudo
assert "/* 0x00092140:FUN_00092140 */" in pseudo
assert "/* 0x00093850:FUN_00093850 */" in pseudo

doc = doc_path.read_text(encoding="utf-8")
for phrase in (
    "it reaches both matrix",
    "Yes, in this exact player frame path.",
    "Why no animated glTF was emitted",
    "state+0xA0",
    "0x01FFE7FF",
    "0x00001800",
    "HI_res skin/palette ownership",
):
    assert phrase in doc, phrase
PY

# Re-run every portable component whose result is cited by the ownership join.
tools/validate_nfl_player_pose_native.sh
tools/validate_nfl_player_92140.sh
tools/validate_nfl_player_postprocess.sh

mode=normal
if [[ "${NFL_PLAYER_CLIP_OWNERSHIP_GHIDRA:-0}" == 1 ]]; then
  ghidra='tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless'
  test -x "$ghidra"
  test -d ghidra_projects/nfl2k5.rep
  mkdir -p "$temporary/ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    "$ghidra" "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflPlayerClipOwnershipTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_player_clip_ownership_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_player_clip_ownership_focused_pseudo_c.c" "$pseudo"
  mode=full
fi

echo "NFL_PLAYER_CLIP_OWNERSHIP_VALIDATION_COMPLETE mode=$mode selector_rows=37 path_steps=16 gltf_emitted=0"
