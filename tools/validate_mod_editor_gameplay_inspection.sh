#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d /tmp/mod-editor-gameplay-inspection.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$temporary/pycache"

python3 -m py_compile \
  mod_editor/__main__.py \
  mod_editor/core/__init__.py \
  mod_editor/core/gameplay_inspection.py \
  tests/mod_editor/test_gameplay_inspection.py

test "$(wc -c < reports/gameplay_tuning/gameplay_tuning_ai_draft_audit.json)" = 54545
test "$(sha256sum reports/gameplay_tuning/gameplay_tuning_ai_draft_audit.json | cut -d' ' -f1)" = \
  '0c1c47c7f025f9fbb303b9a7d78e7aaf8e9d3c4d603a47bc7819d5ded43557ec'
test "$(wc -c < reports/gameplay_tuning/nfl_franchise_limit_feasibility.json)" = 17707
test "$(sha256sum reports/gameplay_tuning/nfl_franchise_limit_feasibility.json | cut -d' ' -f1)" = \
  '4d67e2d3009b7691a10eed4e1807371d3b80d6d0fafb5cb9cd62bcbf5cb8b4fd'
test "$(wc -c < reports/gameplay_tuning/nfl2k5_xbox_save_inventory.json)" = 31477
test "$(sha256sum reports/gameplay_tuning/nfl2k5_xbox_save_inventory.json | cut -d' ' -f1)" = \
  'e49d30bc9adb87faf1a592a9d3a529169659be8f926be9db9028c90009477e3c'
test "$(wc -c < reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json)" = 6581
test "$(sha256sum reports/gameplay_tuning/nfl2k5_ps2_fixture_availability.json | cut -d' ' -f1)" = \
  'f5fd78fecf5b4e3486a6aaed96b949b336507c3c3aa7ac9fed92b52d0074ee6b'

python3 -m unittest -v tests/mod_editor/test_gameplay_inspection.py

python3 -m mod_editor --inspect-gameplay-sliders nfl2k5 > "$temporary/nfl-sliders.json"
python3 -m mod_editor --inspect-gameplay-sliders apf2k8 > "$temporary/apf-sliders.json"
python3 -m mod_editor --inspect-draft-priority nfl2k5 > "$temporary/nfl-draft.json"
python3 -m mod_editor --inspect-draft-priority apf2k8 > "$temporary/apf-draft.json"
python3 -m mod_editor --inspect-nfl-franchise-limit all > "$temporary/franchise.json"
python3 -m mod_editor --inspect-nfl-save-inventory > "$temporary/save-inventory.json"

python3 - "$temporary" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
nfl = json.loads((root / "nfl-sliders.json").read_text())
apf = json.loads((root / "apf-sliders.json").read_text())
nfl_draft = json.loads((root / "nfl-draft.json").read_text())
apf_draft = json.loads((root / "apf-draft.json").read_text())
franchise = json.loads((root / "franchise.json").read_text())
save_inventory = json.loads((root / "save-inventory.json").read_text())

assert nfl["schema"] == "mod_editor_gameplay_slider_inspection/v1"
assert nfl["slider_count"] == apf["slider_count"] == 21
assert [row["name"] for row in nfl["sliders"]] == [row["name"] for row in apf["sliders"]]
assert nfl["stock_ui_range"] == {"minimum": 0.0, "maximum": 1.0, "step": 0.025}
assert nfl["save_or_profile_writer_available"] is False
assert nfl["observed_fixture_values_available"] is True
# 1.0, not 0.35 -- the save stores each slider vector in its globals' address
# order (Catching last), not the menu's display order (Catching fourth), so the
# old layout published Human Coverage's 0.35 under Human Catching's name.
assert nfl["sliders"][3]["observed_franchise1_value"] == 1.0
assert apf["out_of_range_runtime_safety_proved"] is False

assert nfl_draft["position_weight_count"] == apf_draft["position_weight_count"] == 17
assert nfl_draft["proof_status"]["cpu_selector_owner_proved"] is True
assert apf_draft["proof_status"]["cpu_selector_owner_proved"] is False
assert nfl_draft["safe_writer_available"] is False

assert franchise["schema"] == "mod_editor_nfl_franchise_matrix_inspection/v1"
assert franchise["target_count"] == 5
assert franchise["safe_writer_count"] == franchise["archive_only_fix_count"] == 0
assert franchise["pcsx2_patch_coordinates_available"] is False
assert franchise["pcsx2_target"]["serial"] == "SLUS-20919"
assert franchise["pcsx2_target"]["boot_elf_expected_name"] == "SLUS_209.19"
assert franchise["pcsx2_local_fixture_status"]["safe_patch_ready"] is False
assert len(franchise["pcsx2_limitation_status"]) == 4
assert all(row["xbox_address_reuse_allowed"] is False
           for row in franchise["pcsx2_limitation_status"])
assert all(row["current_writer_safe"] is False for row in franchise["targets"])
assert all(row["archive_only_fix"] is False for row in franchise["targets"])

assert save_inventory["schema"] == "mod_editor_nfl_save_inventory_inspection/v1"
assert save_inventory["container_count"] == 8
assert len(save_inventory["observed_slider_values"]) == 21
assert save_inventory["integrity_boundary"]["extra_size"] == 20
assert save_inventory["integrity_boundary"]["safe_writer_available"] is False

for path in root.glob("*.json"):
    text = path.read_text()
    assert re.search(r"0x[0-9a-f]+", text, re.IGNORECASE) is None, path
    assert "file_offset" not in text, path
    assert "virtual_address" not in text, path
PY

for target in draft trade salary-cap contracts super-bowl; do
  python3 -m mod_editor --inspect-nfl-franchise-limit "$target" \
    > "$temporary/franchise-$target.json"
done

if python3 -m mod_editor --inspect-gameplay-sliders offset:123 \
    > "$temporary/raw.stdout" 2> "$temporary/raw.stderr"; then
  echo 'public editor accepted a raw gameplay selector' >&2
  exit 1
fi
if python3 -m mod_editor --inspect-nfl-franchise-limit address:123 \
    > "$temporary/address.stdout" 2> "$temporary/address.stderr"; then
  echo 'public editor accepted a raw franchise selector' >&2
  exit 1
fi

help="$(python3 -m mod_editor --help)"
rg -q -- '--inspect-gameplay-sliders GAME' <<< "$help"
rg -q -- '--inspect-draft-priority GAME' <<< "$help"
rg -q -- '--inspect-nfl-franchise-limit TARGET' <<< "$help"
rg -q -- '--inspect-nfl-save-inventory' <<< "$help"
if rg -q -- '--gameplay-offset|--draft-address|--franchise-offset' <<< "$help"; then
  echo 'public editor exposed a raw gameplay/franchise offset' >&2
  exit 1
fi

rg -q 'evidence lookups, not settings readers or patch writers' \
  docs/research/mod_editor_gameplay_franchise_inspection.md
rg -q 'All five rows remain' \
  docs/research/mod_editor_gameplay_franchise_inspection.md
rg -q 'output contains no raw executable/file offsets' \
  docs/research/mod_editor_gameplay_franchise_inspection.md

echo 'MOD_EDITOR_GAMEPLAY_INSPECTION_VALIDATION_PASS tests=9 sliders=21 games=2 nfl_observed_save_values=true save_containers=8 draft_weights=17 nfl_draft_owner=true apf_draft_owner=false franchise_targets=5 pcsx2_target=SLUS-20919 pcsx2_fixture=false safe_writers=0 raw_offsets=false report_pins=4 writes=false'
