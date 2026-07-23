#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

python3 - "$root" <<'PY'
import hashlib
import json
from pathlib import Path
import sys


root = Path(sys.argv[1])
report = json.loads(
    (root / "reports/assets/apf_xenia_season_coachdesk_experiment.json").read_text()
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


assert report["schema"] == "apf_xenia_season_coachdesk_experiment/v1"
static = report["static_precondition"]
assert static["guest_word_address"] == "0x84E55F10"
assert static["retail_be32_value"] == "0x820E0B80"
assert static["experimental_be32_value"] == "0x820E0BC8"

patch = report["patch"]
patch_path = root / patch["path"]
assert digest(patch_path) == patch["sha256"]
patch_text = patch_path.read_text()
for exact in (
    'title_id = "54540807"',
    'hash = "5447E5428AA2D52A"',
    "is_enabled = true",
    "address = 0x84e55f10",
    "value = 0x820e0bc8",
):
    assert exact in patch_text
assert patch["xex_modified"] is False
assert patch["game_volume_modified_by_experiment"] is False

runtime = report["runtime"]
assert runtime["patch_database_titles_loaded"] == 1
assert runtime["patch_apply_log_seen"] is True
assert runtime["window_title_patches_applied_seen"] is True
assert runtime["module_launched"] is True
assert runtime["title_screen_rendered"] is True
assert runtime["patch_boot_safe"] is True
assert digest(root / "extracted/All-Pro Football 2K8 (USA)/default.xex") == runtime[
    "source_default_xex_sha256_after"
]
assert digest(root / "extracted/All-Pro Football 2K8 (USA)/0A") == runtime[
    "source_0a_sha256_after"
]

control = report["control_and_blocker"]
assert control["unpatched_full_license_control_started"] is True
assert control["profile_autologin_proved"] is True
assert control["first_run_team_creator_forced"] is True
assert control["season_row_reached_in_control"] is False
assert control["season_row_reached_with_patch"] is False

outcome = report["outcome"]
assert outcome["classification"] == "patch_loaded_and_boot_safe_target_route_navigation_blocked"
assert outcome["coachdesk_menu_visible"] is False
assert outcome["no_op_proved"] is False
assert outcome["crash_proved"] is False
assert outcome["pointer_effect_proved"] is False
assert outcome["hidden_franchise_mode_proved"] is False

for artifact in report["artifacts"].values():
    assert digest(root / artifact["path"]) == artifact["sha256"]

excerpt = (root / report["artifacts"]["patch_log_excerpt"]["path"]).read_text()
assert "PatchDB: Loaded patches for 1 titles" in excerpt
assert "Season Coach Gameplan to Coach's Desk descriptor experiment" in excerpt
assert "KernelState: Launching module" in excerpt
window_title = (root / report["artifacts"]["window_title"]["path"]).read_text()
assert "[Patches Applied]" in window_title

doc = (root / "docs/research/apf_xenia_season_coachdesk_experiment.md").read_text()
for phrase in (
    "## Worked", "## Failed or unproved", "## Blocking",
    "0x84E55F10", "first-run team creation", "not classified as a menu",
    "APF_XENIA_SEASON_COACHDESK_EXPERIMENT_PASS",
):
    assert phrase in doc, phrase

print(
    "APF_XENIA_SEASON_COACHDESK_EXPERIMENT_PASS "
    "patch_loaded=yes boot_safe=yes season_reached=no pointer_effect=unproved"
)
PY
