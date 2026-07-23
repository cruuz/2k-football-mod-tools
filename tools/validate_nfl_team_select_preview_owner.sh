#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/nfl-team-select-preview-owner.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

generator="$root/tools/nfl_team_select_preview_owner.py"
report="$root/reports/assets/nfl2k5_team_select_preview_owner.json"
doc="$root/docs/research/nfl_team_select_preview_owner.md"
trace_dir="$root/reports/assets/nfl2k5_team_select_preview_owner"
trace="$trace_dir/nfl_team_select_preview_owner_trace.txt"
pseudo="$trace_dir/nfl_team_select_preview_owner_pseudo_c.c"

test -f "$generator"
test -f "$report"
test -f "$doc"
test -f "$trace"
test -f "$pseudo"
test -f "$root/extracted/ESPN NFL 2K5 (USA)/default.xbe"
test -f "$root/ghidra_projects/nfl2k5.gpr"

PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile "$generator"
python3 "$generator" --root "$root" --output "$tmp/report.json"
cmp "$tmp/report.json" "$report"

python3 - "$report" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "nfl2k5_team_select_preview_owner/v1"
conclusion = report["conclusion"]
assert conclusion["classification"] == "standalone_pre_rendered_txtr_cards_bound_to_team_select_scne_quads"
assert conclusion["live_player_09A0_iff_is_not_the_team_select_preview_owner"] is True
assert conclusion["selected_detroit_uniform_card"] == "unif_a09_0"
assert conclusion["selected_detroit_helmet_card"] == "helm_a09_0"
assert conclusion["selected_card_outer_index"] == 3102
visual = report["runtime_visual_join"]
assert visual["team_select_frames"] == 13
assert visual["diagnostic_visible_in_team_select"] is False
assert visual["diagnostic_visible_on_live_coin_toss_players"] is True
assert visual["uniform_frame_00"]["stats"]["ransac_inliers"] >= 70
assert visual["uniform_frame_00"]["stats"]["mean_gradient_correlation"] > 0.97
assert visual["helmet_frame_06"]["stats"]["ransac_inliers"] >= 30
assert visual["helmet_frame_06"]["stats"]["mean_gradient_correlation"] > 0.95
assert visual["helmet_frame_06"]["same_name_128_control_stats"]["mean_gradient_correlation"] < 0.85
assert len(report["scene_inventory"]) == 3
assert len(report["dynamic_material_submeshes"]) == 10
assert len(report["static_limits_and_portmes"]) == 4
PY

grep -Fq 'standalone, pre-rendered `TXTR` cards' "$doc"
grep -Fq '`unif_a09_0`' "$doc"
grep -Fq '`helm_a09_0`' "$doc"
grep -Fq 'material record `+0x30`' "$doc"
grep -Fq 'PORTME(scene-return)' "$doc"
grep -Fq 'PORTME(context)' "$doc"
grep -Fq 'PORTME(pointer)' "$doc"
grep -Fq 'PORTME(text-logo)' "$doc"
grep -Fq '0x0031F2C5 68782cea00 PUSH 0xea2c78' "$trace"
grep -Fq '0x0031F486 e805f6ffff CALL 0x0031ea90' "$trace"
grep -Fq '0x0031F90C e8bff8ffff CALL 0x0031f1d0' "$trace"
grep -Fq 'DAT_00a83a1c' "$pseudo"
grep -Fq '*(int *)(in_EAX + 0x30) = param_1' "$pseudo"

if [[ "${NFL_TEAM_SELECT_PREVIEW_OWNER_GHIDRA:-0}" == 1 ]]; then
  ghidra="$root/tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless"
  test -x "$ghidra"
  mkdir -p "$tmp/ghidra"
  "$ghidra" "$root/ghidra_projects" nfl2k5 \
    -process default.xbe -readOnly -noanalysis \
    -scriptPath "$root/tools/ghidra_scripts" \
    -postScript NflTeamSelectPreviewOwnerTrace.java "$tmp/ghidra"
  cmp "$tmp/ghidra/nfl_team_select_preview_owner_trace.txt" "$trace"
  cmp "$tmp/ghidra/nfl_team_select_preview_owner_pseudo_c.c" "$pseudo"
fi

echo "NFL 2K5 Team Select preview-owner validation passed"
