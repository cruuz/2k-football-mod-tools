#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
chain_spec='reports/specs/nfl2k5_historical_xemu_hdd_chain.v1.json'
chain_spec_sha=9f017bda0ffb99dd5d9859b2a92fb7e82b30d901a684635449b37bcfe91cfe90

python3 -m py_compile \
  tools/nfl_scorebug_xemu_runtime_report.py \
  tools/nfl_qcow2_historical_chain_verify.py
python3 tools/nfl_scorebug_xemu_runtime_report.py \
  --output "$temporary/runtime.json"
cmp reports/assets/nfl2k5_scorebug_xemu_runtime.json "$temporary/runtime.json"

python3 tools/nfl_scorebug_xiso_verify.py \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso \
    build/nfl2k5-scorebug-workflow-20260712/ESPN-NFL-2K5-scorebug-magenta.xiso.iso \
  --manifest build/nfl2k5-scorebug-workflow-20260712/workflow.json \
  --preview build/nfl2k5-scorebug-workflow-20260712/preview.png \
  --target score_buga \
  --png reports/assets/nfl2k5_scorebug_fixtures/score_buga_diagnostic.png

python3 tools/nfl_qcow2_historical_chain_verify.py \
  --root "$ROOT" \
  --spec "$chain_spec" \
  --spec-sha256 "$chain_spec_sha" \
  --leaf scorebug_runtime \
  >"$temporary/qcow-chain.json"

python3 - "$temporary/qcow-chain.json" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
from PIL import Image

chain = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert chain["schema"] == "nfl2k5_historical_xemu_hdd_chain_verify/v1"
assert chain["leaf"] == "scorebug_runtime"
assert chain["base_status"] == "missing"
assert chain["chain_complete"] is False
assert chain["guest_content_replayable"] is False
assert chain["historical_runtime_reexecuted"] is False
assert chain["missing_base_reconstructed"] is False
assert chain["substitution_allowed"] is False
assert [row["id"] for row in chain["layers"]] == [
    "scorebug_runtime", "away_cacheclear", "jersey_tset_controller_base"
]
assert chain["layers"][-1]["pin"] is None

report_path = Path("reports/assets/nfl2k5_scorebug_xemu_runtime.json")
raw = report_path.read_bytes()
report = json.loads(raw)
assert raw == (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
assert report["schema"] == "nfl2k5_scorebug_xemu_runtime/v1"
assert report["claims"] == {
    "apf_scorebug_write_proved": False,
    "digital_font_runtime_visibility_proved": False,
    "live_user_hdd_selected": False,
    "live_user_xemu_config_selected": False,
    "original_xbox_hardware_tested": False,
    "patched_xiso_modified_during_runtime": False,
    "score_buga_field_hud_ownership_proved": True,
    "score_buga_runtime_visibility_proved": True,
    "scorebug_behavior_patch_proved": False,
    "scorebug_scne_geometry_write_proved": False,
    "shield_espn_runtime_visibility_proved": False,
    "source_xiso_modified": False,
}
assert report["build_proof"]["target"] == {
    "all_other_xiso_bytes_identical": True,
    "changed_byte_count": 2169,
    "chunk_index": 53,
    "default_xbe_unchanged": True,
    "name": "score_buga",
    "outer_index": 346,
    "xdvdfs_tree_identical": True,
    "xiso_absolute_span_offset": 1741540432,
}
assert report["runtime"]["route"].startswith("no-input attract/demo mode")
assert report["runtime"]["game_input_sent"] is False
assert report["runtime"]["shutdown"] == {
    "forced_kill_used": False,
    "nested_display_stopped": True,
    "virtual_gamepad_log_ended_with_bye": True,
    "wm_delete_sent": True,
    "xemu_exit_code": 0,
}

def metrics(path):
    image = Image.open(path).convert("RGB")
    points = []
    for y in range(image.height):
        for x in range(image.width):
            r, g, b = image.getpixel((x, y))
            if r >= 220 and g <= 60 and b >= 180:
                points.append((x, y))
    box = None if not points else [
        min(x for x, _ in points), min(y for _, y in points),
        max(x for x, _ in points), max(y for _, y in points),
    ]
    return image.size, len(points), box

runtime = Path("reports/assets/nfl2k5_scorebug_xemu_runtime/score_buga-magenta-demo.png")
control = Path("reports/assets/nfl2k5_jersey_tset_xemu_runtime/automatic-gameplay-packers-patriots.png")
fixture = Path("reports/assets/nfl2k5_scorebug_fixtures/score_buga_diagnostic.png")
assert metrics(runtime) == ((1280, 672), 17233, [211, 70, 441, 188])
assert metrics(control) == ((1280, 720), 0, None)
assert metrics(fixture) == ((64, 64), 4096, [0, 0, 63, 63])

doc = " ".join(Path("docs/research/nfl_scorebug_xemu_runtime.md").read_text().split())
for phrase in (
    "positive runtime visibility for `score_buga` only",
    "17,233 pixels",
    "No controller input was sent",
    "Still unproved",
    "original-Xbox hardware parity",
):
    assert phrase in doc, phrase
PY

echo 'NFL2K5_SCOREBUG_XEMU_RUNTIME_VALIDATION_PASS target=score_buga changed=2169 magenta=17233 control=0 xemu=0.8.135 hardware=false retained_hdd_layers=2 chain_complete=false guest_content_replayable=false historical_runtime_reexecuted=false originals_unchanged=yes'
