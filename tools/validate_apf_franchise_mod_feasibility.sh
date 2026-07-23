#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/apf_franchise_mod_feasibility.py

python3 tools/apf_franchise_mod_feasibility.py \
  --ownership reports/assets/apf_franchise_runtime_ownership.json \
  --experiment reports/assets/apf_xenia_season_coachdesk_experiment.json \
  --texture-roundtrip reports/assets/apf_texture_roundtrip.json \
  --json-out "$temporary/report.json" \
  --tsv-out "$temporary/report.tsv" \
  --portme-c-out "$temporary/portme.c"

cmp reports/assets/apf_franchise_mod_feasibility.json "$temporary/report.json"
cmp reports/assets/apf_franchise_mod_feasibility.tsv "$temporary/report.tsv"
cmp reports/assets/apf_franchise_mod_feasibility_portme.c "$temporary/portme.c"

for compiler in gcc clang-18; do
  "$compiler" -std=c11 -Wall -Wextra -Werror -c \
    reports/assets/apf_franchise_mod_feasibility_portme.c \
    -o "$temporary/portme_${compiler//[^a-zA-Z0-9]/_}.o"
done

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path("reports/assets/apf_franchise_mod_feasibility.json").read_text())
assert report["schema"] == "vc_apf_franchise_mod_feasibility/v1"
assert report["classification"] == {
    "asset_mod_possible_without_decomp": True,
    "decomp_or_equivalent_code_reconstruction_required_for_full_mode_port": True,
    "mode_route_experiment_possible_without_native_port": True,
    "native_linux_port_required_for_asset_modding": False,
    "nfl2k5_franchise_direct_copy_possible": False,
    "short_answer": "Asset retheming is already possible for bounded targets; restoring or porting a playable franchise is not yet an ordinary mod and requires executable/state reconstruction.",
    "standalone_franchise_playable_proved": False,
}
assert report["scope"] == {
    "launches_game": False,
    "modifies_default_xex": False,
    "modifies_retail_volume": False,
    "produces_enabled_executable_patch": False,
    "uses_existing_validated_runtime_experiment": True,
}
assert report["proved_inventory"] == {
    "franchise_archive_request_call": "0x84A1FD6C",
    "franchise_inner_resource_count": 118,
    "mode_selector_global": "0x84F3FB28",
    "old_franchise_state_count": 9,
    "retail_season_main_target_site": "0x84E57408",
    "retail_season_old_gameplan_target_site": "0x84E55F10",
    "standalone_initializer": "0x849DF2F0",
}
assert len(report["initializer_calls"]) == 14
assert len(report["initializer_globals"]) == 5
assert [row["id"] for row in report["layers"]] == [
    "retained_asset_retheme",
    "retail_season_reuse",
    "descriptor_redirect_experiment",
    "standalone_franchise_entry",
    "full_franchise_loop",
    "nfl2k5_franchise_port",
]
assert report["layers"][0]["classification"] == "offline-writer-proved"
assert report["layers"][2]["public_gui"] == "disabled"
assert report["layers"][4]["mod_without_decomp"] is False
assert len(report["patch_surfaces"]) == 3
assert report["patch_surfaces"][0] == {
    "address": "0x84E55F10",
    "delivery": "external Xenia PatchDB word; retail default.xex unchanged",
    "experimental_be32": "0x820E0BC8",
    "meaning": "Season Coach's Gameplan target: old CoachGameplan -> old Coach's Desk",
    "retail_be32": "0x820E0B80",
    "ship_enabled": False,
    "status": "patch-applied-and-boot-safe; destination-not-dispatched",
}
assert all(row["ship_enabled"] is False for row in report["patch_surfaces"])
assert len(report["portme"]) == 7
assert report["source"]["xex_sha256"] == "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
assert report["source"]["volume_0a_sha256"] == "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
PY

test "$(sha256sum 'extracted/All-Pro Football 2K8 (USA)/default.xex' | cut -d' ' -f1)" = \
  "981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f"
test "$(sha256sum 'extracted/All-Pro Football 2K8 (USA)/0A' | cut -d' ' -f1)" = \
  "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"

printf '%s\n' \
  'APF_FRANCHISE_MOD_FEASIBILITY_VALIDATION_PASS layers=6 patch_surfaces=3 portme=7 enabled_patches=false runtime=false originals_unchanged=true'
