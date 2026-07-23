#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

assets=assets/intermediate/nfl2k5/raw_skin_samples
manifest=reports/assets/nfl_raw_skin_gltf_manifest.json
transforms=reports/assets/nfl_transform_semantics_samples.tsv
influences=reports/assets/nfl_transform_semantics_influences.tsv
rest=reports/assets/nfl_rest_orientation.json

for required in \
  tools/nfl_raw_skin_gltf.py \
  tools/nfl_raw_skin_gltf_validate.py \
  docs/research/nfl_raw_skin_gltf.md \
  "$manifest" "$transforms" "$influences" "$rest" \
  "$assets/0003_0113_lo_body_raw_skin.gltf" \
  "$assets/0003_0113_lo_body_raw_skin.bin" \
  "$assets/0346_0109_referee_raw_skin.gltf" \
  "$assets/0346_0109_referee_raw_skin.bin" \
  "$assets/0348_0000_coach_raw_skin.gltf" \
  "$assets/0348_0000_coach_raw_skin.bin"; do
  test -f "$required"
done

temporary=$(mktemp -d /tmp/nfl-raw-skin-gltf.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tools/nfl_raw_skin_gltf.py tools/nfl_raw_skin_gltf_validate.py

python3 tools/nfl_raw_skin_gltf.py \
  --model-dir assets/intermediate/nfl2k5/models \
  --transforms "$transforms" \
  --influences "$influences" \
  --rest-report "$rest" \
  --output-dir "$temporary/assets" \
  --manifest "$temporary/manifest.json"

cmp "$temporary/manifest.json" "$manifest"
python3 - "$manifest" "$temporary/assets" "$assets" <<'PY'
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
print("NFL_RAW_SKIN_GLTF_REGEN_PASS files=6")
PY

test "$(sha256sum "$manifest" | cut -d' ' -f1)" = \
  ff619543fe03768b27ace896e7b38c954d5db832589209d9df243da6f9580bdf
test "$(sha256sum "$assets/0003_0113_lo_body_raw_skin.gltf" | cut -d' ' -f1)" = \
  7e9a241245c89bc224026c8dc0d3dce9a908319787e5cb1b196bf64ccf1844af
test "$(sha256sum "$assets/0346_0109_referee_raw_skin.gltf" | cut -d' ' -f1)" = \
  ed5c4b3314679b991e5f87015dbd12ba8d1fc3d4ff7d331411511e573a3d4daf
test "$(sha256sum "$assets/0348_0000_coach_raw_skin.gltf" | cut -d' ' -f1)" = \
  c048faa0281fa0976ec9d36912a7f1832f242ffc89508256a287ecc716e91394

python3 tools/nfl_raw_skin_gltf_validate.py \
  --manifest "$manifest" \
  --asset-dir "$assets" \
  --transforms "$transforms" \
  --influences "$influences" \
  --workspace "$root"

echo 'NFL_RAW_SKIN_GLTF_VALIDATION_PASS scenes=3 skins=5 joints=125 vertices=11730 primitives=157'
