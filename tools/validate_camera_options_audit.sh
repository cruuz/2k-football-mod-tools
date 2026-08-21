#!/usr/bin/env bash
# Validate the camera-options audit and its read-only public projection.
#
# The audit is regenerated from the two executables and compared against the
# checked-in report, so a drifted binary or a changed decoder is caught here
# rather than in a panel. The projection is then checked for the two things it
# must never do: publish a raw executable address, or offer a writer.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export PYTHONDONTWRITEBYTECODE=1

report="reports/gameplay_tuning/camera_options_audit.json"
test -f "$report"

python3 -m py_compile \
  tools/camera_options_audit.py \
  mod_editor/core/camera_inspection.py \
  tests/mod_editor/test_camera_inspection.py

temporary="$(mktemp -d /tmp/camera-options-audit.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT

# Regenerate from the binaries when they are present and require byte identity.
# The XBE lives outside the repo on a lean checkout, so this half is skipped
# rather than failed when the disc is not on this machine.
xbe="extracted/ESPN NFL 2K5 (USA)/default.xbe"
pe="/tmp/apf.pe"
if test -f "$xbe" && test -f "$pe"; then
  python3 tools/camera_options_audit.py \
    --xbe "$xbe" --apf-pe "$pe" --output "$temporary/regenerated.json" >/dev/null
  cmp "$temporary/regenerated.json" "$report"
  echo "CAMERA_OPTIONS_AUDIT_REGENERATED_IDENTICAL"
else
  echo "CAMERA_OPTIONS_AUDIT_REGENERATION_SKIPPED game executables not present"
fi

python3 -m unittest -v tests.mod_editor.test_camera_inspection

python3 -m mod_editor --inspect-camera-options nfl2k5 > "$temporary/nfl.json"
python3 -m mod_editor --inspect-camera-options apf2k8 > "$temporary/apf.json"

python3 - "$temporary" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])
nfl = json.loads((root / "nfl.json").read_text())
apf = json.loads((root / "apf.json").read_text())

assert nfl["schema"] == apf["schema"] == "mod_editor_camera_options_inspection/v1"
assert nfl["setting_count"] == 7, nfl["setting_count"]
assert apf["setting_count"] == 9, apf["setting_count"]
assert nfl["preset_count"] == 6 and apf["preset_count"] == 6

# 2K5 exposes all six; APF hides exactly one, and it is the authored skycam.
assert nfl["presets_present_but_not_selectable"] == []
assert apf["presets_present_but_not_selectable"] == ["Blimp"]

# Neither product may ever offer a writer from this surface.
for value in (nfl, apf):
    assert value["read_only"] is True
    assert value["writer_available"] is False
    assert value["runtime_behaviour_proved"] is False
    assert value["archive_only_mod_possible"] is False
    assert value["why_read_only"]

# No raw executable address, and no internal field, may reach a user.
for name, value in (("nfl2k5", nfl), ("apf2k8", apf)):
    text = json.dumps(value)
    assert re.search(r"0x[0-9A-Fa-f]{6,}", text) is None, name
    for forbidden in ("virtual_address", "callbacks", "file_offset", "operand"):
        assert forbidden not in text, (name, forbidden)

# The replay-camera enum sits directly after the camera enum in both binaries;
# none of its names may be published as a gameplay camera preset.
replay = {"1st Person", "TV Broadcast", "In Stands", "On Field", "Realistic",
          "Quick", "Default"}
for name, value in (("nfl2k5", nfl), ("apf2k8", apf)):
    published = {preset["name"] for preset in value["presets"]}
    assert not (published & replay), (name, published & replay)
PY

echo 'CAMERA_OPTIONS_AUDIT_VALIDATION_PASS games=2 nfl_settings=7 apf_settings=9 presets=6 writers=0 raw_addresses=false runtime=false'
