#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

SCHEMA='reports/specs/nfl2k5_group36_xemu_runtime_result.v1.schema.json'
REPORT='reports/assets/nfl2k5_group36_s42_xemu_runtime_partial.v1.json'
DOC='docs/research/nfl_group36_xemu_runtime_result.md'
TOOL='tools/nfl_group36_xemu_runtime_result.py'
TEST='tests/test_nfl_group36_xemu_runtime_result.py'

test "$(wc -c < "$SCHEMA")" = 6934
test "$(sha256sum "$SCHEMA" | cut -d' ' -f1)" = \
  ca553ac95199813fec740a6eca305f4860daf21f062303ce2d98c689af3854b1
test "$(wc -c < "$REPORT")" = 4353
test "$(sha256sum "$REPORT" | cut -d' ' -f1)" = \
  a606e8ef4a1030d1e2dca5202204e401eace7cc0a5b9ce0ff3443198e634bc6d
test "$(sha256sum "$DOC" | cut -d' ' -f1)" = \
  df3f85b774959fc2a134fe8617b5d4cc106d6204f309bc05d739b10492e11368
test "$(sha256sum "$TOOL" | cut -d' ' -f1)" = \
  3d1d6bff68f000f86f72f52db83613cef06053d0daf9d3b1e7df449843129f1f
test "$(sha256sum "$TEST" | cut -d' ' -f1)" = \
  e449e3da9d525e59e6601df1f4f1ac53f9ed6e1b6f24169eebe23066466ab444

PYTHONPATH=tools python3 -m unittest \
  tests.test_nfl_group36_xemu_runtime_result >/dev/null

result=$(python3 "$TOOL" \
  --result "$REPORT" \
  --control-state observed \
  --control-outcome selector_skip_negative \
  --control-xiso-path build/nfl2k5-stadium-group36-geometry-xiso-20260713/ESPN-NFL-2K5-s42-dispatch-control.xiso.iso \
  --control-xiso-size 6300499968 \
  --control-xiso-sha256 32a4f45e5d3d53f1ee1780165d9ffdaa36995a154a62e39c313e0e467b63b9a5 \
  --control-config-path .codex-tmp/nfl2k5-group36-geometry-xemu-20260713/xemu-control.toml \
  --control-config-size 932 \
  --control-config-sha256 af934acc09c49755ac817aec5322ac945df4ecf15b311f562652ccdbdcef1ea0 \
  --control-hdd-path .codex-tmp/nfl2k5-group36-geometry-xemu-20260713/xbox_hdd-control-dispatch.qcow2 \
  --control-hdd-size 589824 \
  --control-hdd-sha256 b2969beea4aeb1db384558390cce7cc9c1ce0c8aca42fe215b52075e2ece6938 \
  --control-screenshot-path selector_after=.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/logs/control-target-selection.png \
  --control-screenshot-size selector_after=282353 \
  --control-screenshot-sha256 selector_after=c71e2ff0e1ea715190ecd1ab81e7a0978306e9e0c13b691612372856182c80de \
  --control-screenshot-path selector_before=.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/logs/control-team-options-initial.png \
  --control-screenshot-size selector_before=281754 \
  --control-screenshot-sha256 selector_before=ab8ce5ef0c9921c676a1d64903e4cf741c7f59cf011cdfa63489ea3a334234ee \
  --control-screenshot-path selector_intermediate=.codex-tmp/nfl2k5-group36-geometry-xemu-20260713/logs/control-time-step1.png \
  --control-screenshot-size selector_intermediate=283932 \
  --control-screenshot-sha256 selector_intermediate=108081fd37b36f3c7f726d20caa7b1a50d090e2edcef089d09607cfa375fdffc \
  --expanded-state unobserved)

test "$result" = \
  'NFL_GROUP36_XEMU_RUNTIME_RESULT_PASS status=selector_skip_negative boot=false selector_skip=true control_visible=false expanded_visible=false geometry_visible=false hardware=false production=false'

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(Path(
    "reports/assets/nfl2k5_group36_s42_xemu_runtime_partial.v1.json"
).read_bytes())
schema = json.loads(Path(
    "reports/specs/nfl2k5_group36_xemu_runtime_result.v1.schema.json"
).read_bytes())
doc = Path("docs/research/nfl_group36_xemu_runtime_result.md").read_text()

assert schema["$id"] == "urn:nfl2k5-group36-xemu-runtime-result:v1"
assert schema["$defs"]["outcome"]["properties"]["kind"]["enum"] == [
    "boot_acceptance", "selector_skip_negative", "target_visible"
]
assert report["status"] == "selector_skip_negative"
assert report["runs"]["control"]["observation_status"] == "observed"
assert [row["kind"] for row in report["runs"]["control"]["outcomes"]] == [
    "selector_skip_negative"
]
expanded = report["runs"]["expanded_wall"]
assert expanded["observation_status"] == "unobserved"
assert expanded["artifacts"] == {
    "config": None, "hdd": None, "screenshots": [], "xiso": None
}
assert expanded["outcomes"] == []
claims = report["claims"]
assert claims["control_selector_skip_negative_observed"] is True
assert claims["s42_index18_quick_game_skip_observed"] is True
assert all(claims[key] is False for key in claims if key not in {
    "control_selector_skip_negative_observed",
    "s42_index18_quick_game_skip_observed",
})
assert "s42 causes record 18 to" in doc
assert "disappear from Quick Game cycling" in doc
assert "does **not** prove" in doc
assert "normal gate intentionally omits `--verify-files`" in doc
PY

echo 'NFL_GROUP36_XEMU_RUNTIME_RESULT_VALIDATION_PASS outcome=selector_skip_negative control=observed expanded=unobserved xiso_pin=exact config_pin=exact hdd_pin=exact screenshots=3 boot=false target_loaded=false control_visible=false expanded_visible=false geometry_visible=false hardware=false production=false emulator_launched=false live_artifacts_read=false'
