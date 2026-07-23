#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

index='extracted/All-Pro Football 2K8 (USA)/0A'
canonical='assets/intermediate/apf2k8/cut_content/audio_test'
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

before="$(sha256sum "$index" | cut -d' ' -f1)"
PYTHONPYCACHEPREFIX="$tmp/pycache" python3 -m py_compile tools/apf_scene.py

for spec in \
    '1 glowball' \
    '2 speaker_ls' \
    '3 speaker_lf' \
    '4 speaker_lfe' \
    '5 speaker_rf' \
    '6 orange_cursor' \
    '7 speaker_c' \
    '9 speaker_rs'; do
  set -- $spec
  inner="$1"
  name="$2"
  mkdir -p "$tmp/$name"
  python3 tools/apf_scene.py "$index" \
    --select "137:$inner" \
    --output "$tmp/$name/report.json" \
    --gltf-dir "$tmp/$name" \
    --max-decompressed 1048576 >/dev/null
  diff -r "$canonical/$name" "$tmp/$name"
done

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path("assets/intermediate/apf2k8/cut_content/audio_test")
expected = {
    "glowball": (1, 4, 2),
    "speaker_ls": (1, 358, 322),
    "speaker_lf": (1, 340, 322),
    "speaker_lfe": (1, 302, 285),
    "speaker_rf": (1, 340, 322),
    "orange_cursor": (1, 4, 2),
    "speaker_c": (1, 340, 322),
    "speaker_rs": (1, 354, 322),
}
totals = {"meshes": 0, "vertices": 0, "triangles": 0}
for name, values in expected.items():
    directory = root / name
    manifest = json.loads((directory / "manifest.json").read_text())
    report = json.loads((directory / "report.json").read_text())
    assert manifest["schema"] == "apf_static_gltf_manifest/v1"
    assert report["schema"] == "apf_scene_inventory/v1"
    assert report["summary"]["scne_parsed"] == 1
    assert report["summary"]["scne_failures"] == 0
    summary = manifest["summary"]
    actual = (summary["mesh_count"], summary["vertex_count"], summary["triangle_count"])
    assert actual == values, (name, actual, values)
    assert summary["skipped_mesh_count"] == 0
    assert summary["withheld_scene_count"] == 0
    export = manifest["exports"][0]
    gltf_path = directory / export["gltf"]
    bin_path = directory / export["bin"]
    gltf = json.loads(gltf_path.read_text())
    assert gltf["asset"]["version"] == "2.0"
    assert len(gltf["meshes"]) == 1
    assert gltf["buffers"][0]["uri"] == bin_path.name
    assert hashlib.sha256(gltf_path.read_bytes()).hexdigest() == export["gltf_sha256"]
    assert hashlib.sha256(bin_path.read_bytes()).hexdigest() == export["bin_sha256"]
    totals["meshes"] += actual[0]
    totals["vertices"] += actual[1]
    totals["triangles"] += actual[2]
assert totals == {"meshes": 8, "vertices": 2042, "triangles": 1899}, totals
PY

after="$(sha256sum "$index" | cut -d' ' -f1)"
test "$before" = "$after"

echo 'APF_AUDIO_TEST_GLTF_VALIDATION_PASS scenes=8 meshes=8 vertices=2042 triangles=1899 blender_gltf=true materials=false source=unchanged'
