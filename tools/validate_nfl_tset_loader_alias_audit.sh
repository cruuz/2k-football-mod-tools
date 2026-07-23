#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

temporary=$(mktemp -d /tmp/nfl-tset-loader-alias.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

python3 -m py_compile tools/nfl_tset_loader_alias_audit.py
PYTHONPATH=tools python3 tools/nfl_tset_loader_alias_audit.py \
  --output "$temporary/report.json" >/dev/null
cmp "$temporary/report.json" reports/assets/nfl2k5_tset_loader_alias_audit.json

python3 - <<'PY'
from __future__ import annotations

import json
from pathlib import Path

report = json.loads(
    Path("reports/assets/nfl2k5_tset_loader_alias_audit.json").read_text()
)
assert report["schema"] == "nfl2k5_tset_loader_alias_audit/v1"
assert report["scope"] == {
    "case_count": 4,
    "disc_images_modified": False,
    "game_binary_modified": False,
    "game_or_emulator_started": False,
    "mode": "local_offline_static_and_emulated_loader_layout",
}
assert report["source_pins"]["retail_xiso"]["sha256"] == \
    "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
assert report["source_pins"]["retail_xbe"]["sha256"] == \
    "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"

loader = report["recovered_loader_semantics"]
assert loader["symbols"]["source_start"] == "base + D + A - S"
assert loader["collision_free_equation"] == \
    "A >= max_nonfinal_tokens(S - D + dst_endpoint - next_unread_src)"

cases = {case["case_id"]: case for case in report["cases"]}
assert set(cases) == {
    "retail_09H0", "retail_01A0_donor", "png_09H0_home", "png_09A0_away"
}
assert cases["retail_09H0"]["current_loader_alias"]["safe"]
assert cases["retail_01A0_donor"]["current_loader_alias"]["safe"]
assert cases["retail_09H0"]["alias_requirement"]["exact_minimum_scratch_bytes"] == 16
assert cases["retail_01A0_donor"]["alias_requirement"]["exact_minimum_scratch_bytes"] == 3

home = cases["png_09H0_home"]
away = cases["png_09A0_away"]
assert not home["current_loader_alias"]["safe"]
assert not away["current_loader_alias"]["safe"]
assert home["reference_decode"]["consumed_bytes"] == 22_285
assert away["reference_decode"]["consumed_bytes"] == 22_285
assert home["alias_requirement"]["exact_minimum_scratch_bytes"] == 52_392
assert away["alias_requirement"]["exact_minimum_scratch_bytes"] == 56_792
assert home["alias_requirement"]["repair_scratch_bytes"] == 52_416
assert away["alias_requirement"]["repair_scratch_bytes"] == 56_816

home_collision = home["current_loader_alias"]["first_unread_source_collision"]
away_collision = away["current_loader_alias"]["first_unread_source_collision"]
assert (
    home_collision["output_cursor_before"],
    home_collision["next_unread_source_absolute"],
    home_collision["next_unread_source_relative"],
    home_collision["first_overwrite_absolute"],
    home_collision["first_overwrite_source_relative"],
) == (116_664, 116_669, 14_301, 116_681, 14_313)
assert (
    away_collision["output_cursor_before"],
    away_collision["next_unread_source_absolute"],
    away_collision["next_unread_source_relative"],
    away_collision["first_overwrite_absolute"],
    away_collision["first_overwrite_source_relative"],
) == (111_632, 111_639, 13_687, 111_649, 13_697)

expected = "f5ed9101fa5c8bb742168b18fac698f57185c6b6a0190545ecafc1bb1b99c30e"
for case in (home, away):
    assert case["reference_decode"]["decoded_sha256"] == expected
    assert case["sufficient_scratch_probe"]["safe"]
    assert case["sufficient_scratch_probe"]["output_sha256"] == expected
    assert case["sufficient_scratch_probe"]["source_start"] == 154_752
    assert not case["sufficient_scratch_probe"]["wrapper_or_input_file_modified"]

assert report["conclusions"][2]["claim"].endswith(
    "but not the retail-donor negative."
)
assert all(item.startswith("PORTME:") for item in report["portme"])

doc = Path("docs/research/nfl_tset_loader_alias_audit.md").read_text()
flat = " ".join(doc.split())
for phrase in (
    "base + D + A - S",
    "Exact first collisions",
    "52,392",
    "56,792",
    "`52416` (`0xCCC0`)",
    "`56816` (`0xDDF0`)",
    "does **not** explain the exact retail `01A0` donor negative",
):
    assert phrase in flat, phrase
PY

echo 'NFL_TSET_LOADER_ALIAS_AUDIT_VALIDATION_PASS cases=4 retail_safe=2 png_unsafe=2 home_collision=116681 home_min=52392 home_fix=52416 away_collision=111649 away_min=56792 away_fix=56816 originals_unchanged=yes runtime=no'
