#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
export PYTHONDONTWRITEBYTECODE=1
chain_spec='reports/specs/nfl2k5_historical_xemu_hdd_chain.v1.json'
chain_spec_sha=9f017bda0ffb99dd5d9859b2a92fb7e82b30d901a684635449b37bcfe91cfe90

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_scorebug_shield_xemu_runtime_report.py \
  tools/nfl_qcow2_historical_chain_verify.py
python3 tools/nfl_scorebug_shield_xemu_runtime_report.py \
  --output "$temporary/runtime.json"
cmp reports/assets/nfl2k5_scorebug_shield_xemu_runtime.json \
  "$temporary/runtime.json"

python3 tools/nfl2k5_scorebug_mod_project.py verify \
  --project build/nfl2k5-scorebug-shield-workflow-20260712/project.json \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso \
    build/nfl2k5-scorebug-shield-workflow-20260712/ESPN-NFL-2K5-scorebug-shield-cyan.xiso.iso \
  --manifest build/nfl2k5-scorebug-shield-workflow-20260712/build.json \
  --artifact-dir build/nfl2k5-scorebug-shield-workflow-20260712/artifacts

python3 tools/nfl_qcow2_historical_chain_verify.py \
  --root "$ROOT" \
  --spec "$chain_spec" \
  --spec-sha256 "$chain_spec_sha" \
  --leaf scorebug_shield_runtime \
  >"$temporary/qcow-chain.json"

python3 - "$temporary/qcow-chain.json" <<'PY'
import json
from pathlib import Path
import sys

from PIL import Image


chain = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert chain["schema"] == "nfl2k5_historical_xemu_hdd_chain_verify/v1"
assert chain["leaf"] == "scorebug_shield_runtime"
assert chain["base_status"] == "missing"
assert chain["chain_complete"] is False
assert chain["guest_content_replayable"] is False
assert chain["historical_runtime_reexecuted"] is False
assert chain["missing_base_reconstructed"] is False
assert chain["substitution_allowed"] is False
assert [row["id"] for row in chain["layers"]] == [
    "scorebug_shield_runtime", "away_cacheclear",
    "jersey_tset_controller_base",
]
assert chain["layers"][-1]["pin"] is None


report_path = Path("reports/assets/nfl2k5_scorebug_shield_xemu_runtime.json")
raw = report_path.read_bytes()
report = json.loads(raw)
assert raw == (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
assert report["schema"] == "nfl2k5_scorebug_shield_xemu_runtime/v1"
assert report["claims"] == {
    "apf_scorebug_write_proved": False,
    "build_manifest_modified_for_runtime_result": False,
    "digital_font_runtime_visibility_proved": False,
    "live_user_hdd_selected": False,
    "live_user_xemu_config_selected": False,
    "original_xbox_hardware_tested": False,
    "patched_xiso_modified_during_runtime": False,
    "scorebug_behavior_patch_proved": False,
    "scorebug_scne_geometry_write_proved": False,
    "shield_espn_field_hud_ownership_proved": True,
    "shield_espn_non_field_side_effects_proved": False,
    "shield_espn_runtime_visibility_proved": True,
    "source_xiso_modified": False,
}
assert report["build_proof"]["target"] == {
    "all_other_xiso_bytes_identical": True,
    "changed_byte_count": 5320,
    "chunk_index": 26,
    "default_xbe_unchanged": True,
    "dimensions": [128, 64],
    "name": "shield_espn",
    "outer_index": 346,
    "span_size": 5952,
    "xdvdfs_tree_identical": True,
    "xiso_absolute_span_offset": 1741314128,
}
assert report["build_proof"]["builder_runtime_claim_was_false_at_build_time"] is True
assert report["build_proof"]["build_manifest_modified_for_runtime_result"] is False
build = json.loads(Path(
    "build/nfl2k5-scorebug-shield-workflow-20260712/build.json"
).read_bytes())
assert build["claims"]["runtime_visibility_proved"] is False
assert build["claims"]["title_executed"] is False
assert build["claims"]["xemu_started"] is False
assert report["runtime"]["route"].startswith("no-input natural Demo Mode")
assert report["runtime"]["game_input_sent"] is False
assert report["runtime"]["shutdown"] == {
    "forced_kill_used": False,
    "nested_display_stopped": True,
    "wm_delete_sent": True,
    "xemu_exit_code": 0,
}


def metrics(path):
    image = Image.open(path).convert("RGB")
    points = []
    for y in range(image.height):
        for x in range(image.width):
            red, green, blue = image.getpixel((x, y))
            if red <= 20 and green >= 230 and blue >= 230:
                points.append((x, y))
    box = None if not points else [
        min(x for x, _ in points),
        min(y for _, y in points),
        max(x for x, _ in points),
        max(y for _, y in points),
    ]
    return image.size, len(points), box


runtime = Path(
    "reports/assets/nfl2k5_scorebug_shield_xemu_runtime/shield-cyan-demo.png"
)
reporter = Path(
    "reports/assets/nfl2k5_scorebug_shield_xemu_runtime/"
    "shield-cyan-demo-reporter.png"
)
control = Path(
    "reports/assets/nfl2k5_jersey_tset_xemu_runtime/"
    "automatic-gameplay-packers-patriots.png"
)
fixture = Path(
    "reports/assets/nfl2k5_scorebug_fixtures/shield_espn_diagnostic.png"
)
assert metrics(runtime) == ((1280, 672), 4557, [193, 34, 351, 101])
assert metrics(reporter) == ((1280, 672), 4558, [193, 34, 351, 101])
assert metrics(control) == ((1280, 720), 0, None)
assert metrics(fixture) == ((128, 64), 8192, [0, 0, 127, 63])

config = Path(
    "reports/assets/nfl2k5_scorebug_shield_xemu_runtime/isolated-xemu-after.toml"
).read_text()
assert ".codex-tmp/nfl2k5-scorebug-shield-xemu-20260712/xbox_hdd.qcow2" in config
assert "ESPN-NFL-2K5-scorebug-shield-cyan.xiso.iso" in config

doc = " ".join(
    Path("docs/research/nfl_scorebug_shield_xemu_runtime.md")
    .read_text(encoding="utf-8")
    .split()
)
for phrase in (
    "positive runtime visibility and field-HUD ownership for `shield_espn` only",
    "4,557 exact-threshold cyan pixels",
    "No controller input was sent",
    "build-time `runtime_visibility_proved=false`",
    "Still unproved",
    "original-Xbox hardware parity",
):
    assert phrase in doc, phrase
PY

echo 'NFL2K5_SCOREBUG_SHIELD_XEMU_RUNTIME_VALIDATION_PASS target=shield_espn changed=5320 cyan=4557 fixture=8192 control=0 xemu=0.8.135 hardware=false retained_hdd_layers=2 chain_complete=false guest_content_replayable=false historical_runtime_reexecuted=false originals_unchanged=yes'
