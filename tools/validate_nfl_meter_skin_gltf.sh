#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

raw=assets/intermediate/nfl2k5/raw_skin_samples
meter=assets/intermediate/nfl2k5/meter_skin_samples
manifest=reports/assets/nfl_meter_skin_gltf_manifest.json

for required in \
  tools/nfl_meter_skin_gltf.py \
  tools/nfl_meter_skin_gltf_validate.py \
  docs/research/nfl_meter_skin_gltf.md \
  "$manifest" \
  "$meter/0003_0113_lo_body_meter_skin.gltf" \
  "$meter/0003_0113_lo_body_meter_skin.bin" \
  "$meter/0346_0109_referee_meter_skin.gltf" \
  "$meter/0346_0109_referee_meter_skin.bin" \
  "$meter/0348_0000_coach_meter_skin.gltf" \
  "$meter/0348_0000_coach_meter_skin.bin"; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/nfl-meter-skin-gltf.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_meter_skin_gltf.py tools/nfl_meter_skin_gltf_validate.py

python3 tools/nfl_meter_skin_gltf.py \
  --raw-dir "$raw" \
  --output-dir "$temporary/assets" \
  --manifest "$temporary/manifest.json"

cmp "$temporary/manifest.json" "$manifest"
python3 - "$manifest" "$temporary/assets" "$meter" <<'PY'
import json
from pathlib import Path
import sys

manifest, regenerated, canonical = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
report = json.loads(manifest.read_text(encoding="utf-8"))
for output in report["outputs"]:
    for key in ("output_gltf", "output_bin"):
        name = output[key]
        if (regenerated / name).read_bytes() != (canonical / name).read_bytes():
            raise SystemExit(f"regenerated output differs: {name}")
print("NFL_METER_SKIN_GLTF_REGEN_PASS files=6")
PY

test "$(sha256sum "$manifest" | cut -d' ' -f1)" = \
  8369a117504de328fc41a9380e589b3e5c30d15a494d769be80c13b6dfbc35eb
test "$(sha256sum "$meter/0003_0113_lo_body_meter_skin.gltf" | cut -d' ' -f1)" = \
  79a76bd011540ade1bbd68dc2aced1a0973a212bb08fcbff47e8956f6804c240
test "$(sha256sum "$meter/0346_0109_referee_meter_skin.gltf" | cut -d' ' -f1)" = \
  8e18741ba6e512bc98017ce6d7cea4f399db6720e1a9edc55c7217d8b56e0ebe
test "$(sha256sum "$meter/0348_0000_coach_meter_skin.gltf" | cut -d' ' -f1)" = \
  db99788453bb7dd350353e6c5c00d730f116b1b1ac691620e18c64c9eb4a4961

python3 tools/nfl_meter_skin_gltf_validate.py \
  --manifest "$manifest" \
  --raw-dir "$raw" \
  --meter-dir "$meter"

echo 'NFL_METER_SKIN_GLTF_VALIDATION_PASS scenes=3 skins=5 joints=125 positions=12790 animations=0'
