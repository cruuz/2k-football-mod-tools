#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p .codex-tmp
TMP="$(mktemp -d "$ROOT/.codex-tmp/nfl-live-face-validate.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
export PYTHONPATH="$ROOT/tools"

check_hash() {
  local path="$1" expected="$2" actual
  actual="$(sha256sum "$path" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || {
    echo "hash mismatch: $path" >&2
    exit 1
  }
}

expect_fail() {
  local label="$1"
  shift
  if "$@" >"$TMP/$label.log" 2>&1; then
    echo "negative test unexpectedly succeeded: $label" >&2
    exit 1
  fi
}

check_hash "ESPN NFL 2K5 (USA).xiso.iso" \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
check_hash "extracted/ESPN NFL 2K5 (USA)/default.xbe" \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9
check_hash "extracted/ESPN NFL 2K5 (USA)/vc_53450030/0" \
  34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
check_hash "extracted/ESPN NFL 2K5 (USA)/vc_53450030/2" \
  21e00e0f41b3e016e416c44f3e1f3a07f9d5d7fdb5b9fe586685fadceb335886
check_hash "extracted/ESPN NFL 2K5 (USA)/vc_53450030/3" \
  921a139a9fd1a9470cc77f78455a6282e426376d4c201635b97a512d1f947aa7
check_hash reports/assets/nfl2k5_live_face_texture_compatibility.json \
  812db90df6b50b4491d8701a0ceb13b54a26ea7afadc2fbd86c4715b15aa9e09
check_hash reports/assets/nfl2k5_live_face_texture_compatibility.tsv \
  a16a4579227cfd944803a8a6e5823a6a1ab6b2408daf109ff14d6e4aab03666a
check_hash assets/fixtures/nfl2k5/live_face/live_face_fixture.png \
  1639b839a54fbfd7707e73f72147ca7c98ebf75522813d50a2bd0abc6622b682

python3 -m py_compile \
  tools/nfl_dxt1.py \
  tools/nfl_live_face_texture_compatibility.py \
  tools/nfl_live_face_texture_targets.py \
  tools/nfl_live_face_texture_png_import.py \
  tools/nfl_live_face_texture_fixture.py \
  tools/nfl_live_face_texture_xiso_workflow.py \
  tools/nfl_live_face_texture_xiso_verify.py

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_nfl_live_face_texture_virtual_xiso_verify

python3 tools/nfl_live_face_texture_compatibility.py \
  --json "$TMP/compatibility.json" --tsv "$TMP/compatibility.tsv"
cmp reports/assets/nfl2k5_live_face_texture_compatibility.json "$TMP/compatibility.json"
cmp reports/assets/nfl2k5_live_face_texture_compatibility.tsv "$TMP/compatibility.tsv"

python3 - <<'PY'
from pathlib import Path
from nfl_dxt1 import encode_dxt1_opaque
from nfl_live_face_texture_targets import select_target
from nfl_tset_png_import import decode_rgba_png
from nfl_txtr import decode_dxt1

payload = Path("assets/fixtures/nfl2k5/live_face/live_face_fixture.png").read_bytes()
width, height, rgba = decode_rgba_png(payload, (256, 256))
first, first_info = encode_dxt1_opaque(rgba, width, height)
second, second_info = encode_dxt1_opaque(rgba, width, height)
assert first == second and first_info == second_info and len(first) == 32768
decoded = decode_dxt1(first, width, height)
assert len(decoded) == len(rgba) and all(decoded[index] == 255
                                         for index in range(3, len(decoded), 4))
for family in "fhn":
    _, _, _, target = select_target("0124", family)
    assert target.resource_name == family + "0124"
PY

for family in f h n; do
  python3 tools/nfl_live_face_texture_png_import.py \
    --face-id 0124 --family "$family" \
    --png assets/fixtures/nfl2k5/live_face/live_face_fixture.png \
    --output-dir "$TMP/import-$family"
done

python3 - "$TMP" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
expected = {"f": (43872, 6, "raw_fixed_span"),
            "h": (None, 1, "vc_lz_fixed_span"),
            "n": (None, 1, "vc_lz_fixed_span")}
for family, (span_size, mips, mode) in expected.items():
    path = root / f"import-{family}"
    value = json.loads((path / "import.json").read_bytes())
    replacement = (path / "replacement.txtr.bin").read_bytes()
    assert value["target"]["resource_name"] == family + "0124"
    assert len(replacement) == value["target"]["span_size"]
    if span_size is not None:
        assert len(replacement) == span_size
    assert value["mips"]["level_count"] == mips
    assert value["rebuild"]["mode"] == mode
    assert value["claims"]["runtime_visibility_proved"] is False
    assert value["claims"]["xemu_started"] is False
PY

VALIDATE_TMP="$TMP" python3 - <<'PY'
import os
from pathlib import Path
from nfl_txtr import encode_rgba_png

root = Path(os.environ["VALIDATE_TMP"])
root.joinpath("wrong-size.png").write_bytes(
    encode_rgba_png(8, 8, bytes((1, 2, 3, 255)) * 64))
root.joinpath("transparent.png").write_bytes(
    encode_rgba_png(256, 256, bytes((1, 2, 3, 0)) * 256 * 256))
PY
ln -s "$ROOT/assets/fixtures/nfl2k5/live_face/live_face_fixture.png" \
  "$TMP/symlink.png"
ln -s "$ROOT/reports/assets/nfl2k5_live_face_texture_compatibility.json" \
  "$TMP/compatibility-link.json"
ln -s "$ROOT/assets/fixtures/nfl2k5/live_face/face_0124_all_texture_families_plan.json" \
  "$TMP/plan-link.json"
expect_fail wrong_size python3 tools/nfl_live_face_texture_png_import.py \
  --face-id 0124 --family f --png "$TMP/wrong-size.png" \
  --output-dir "$TMP/negative-wrong-size"
expect_fail transparent python3 tools/nfl_live_face_texture_png_import.py \
  --face-id 0124 --family h --png "$TMP/transparent.png" \
  --output-dir "$TMP/negative-transparent"
expect_fail symlink python3 tools/nfl_live_face_texture_png_import.py \
  --face-id 0124 --family n --png "$TMP/symlink.png" \
  --output-dir "$TMP/negative-symlink"
expect_fail compatibility_symlink python3 tools/nfl_live_face_texture_png_import.py \
  --compatibility "$TMP/compatibility-link.json" \
  --face-id 0124 --family n \
  --png assets/fixtures/nfl2k5/live_face/live_face_fixture.png \
  --output-dir "$TMP/negative-compatibility-symlink"
expect_fail bad_selector python3 tools/nfl_live_face_texture_png_import.py \
  --face-id 124 --family f \
  --png assets/fixtures/nfl2k5/live_face/live_face_fixture.png \
  --output-dir "$TMP/negative-selector"

python3 - "$TMP/bad-plan.json" <<'PY'
import json
from pathlib import Path
import sys
value = {
    "edits": [{
        "face_id": "0124",
        "family": True,
        "png": "/tmp/does-not-matter.png",
    }],
    "purpose": "type refusal",
    "schema": "nfl2k5_live_face_texture_plan/v1",
}
Path(sys.argv[1]).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY
python3 - "$TMP/bad-plan.json" "$TMP/plan-link.json" <<'PY'
from pathlib import Path
import sys
from nfl_live_face_texture_xiso_workflow import read_plan, WorkflowError
for path, expected in ((Path(sys.argv[1]), "fields/types"),
                       (Path(sys.argv[2]), "non-symlink regular file")):
    try:
        read_plan(path)
    except (OSError, WorkflowError) as exc:
        assert expected in str(exc)
    else:
        raise SystemExit(f"invalid plan was accepted: {path}")
PY

PROOF="$ROOT/.codex-tmp/nfl-live-face-xiso-proof-20260712"
: > "$TMP/present-output.xiso.iso"
ln -s "$ROOT/ESPN NFL 2K5 (USA).xiso.iso" "$TMP/symlink-output.xiso.iso"
for hostile_output in present-output.xiso.iso symlink-output.xiso.iso; do
  expect_fail "virtual_${hostile_output%%.*}" \
    python3 tools/nfl_live_face_texture_xiso_verify.py \
      --virtual-output \
      --source-xiso "ESPN NFL 2K5 (USA).xiso.iso" \
      --output-xiso "$TMP/$hostile_output" \
      --manifest "$PROOF/workflow.json" \
      --preview-dir "$PROOF/previews" \
      --plan assets/fixtures/nfl2k5/live_face/face_0124_all_texture_families_plan.json
done
python3 tools/nfl_live_face_texture_xiso_verify.py \
  --virtual-output \
  --source-xiso "ESPN NFL 2K5 (USA).xiso.iso" \
  --output-xiso "$PROOF/nfl2k5-live-face-proof.xiso.iso" \
  --manifest "$PROOF/workflow.json" \
  --preview-dir "$PROOF/previews" \
  --plan assets/fixtures/nfl2k5/live_face/face_0124_all_texture_families_plan.json

check_hash "ESPN NFL 2K5 (USA).xiso.iso" \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9

echo "NFL_LIVE_FACE_TEXTURE_VALIDATION_PASS selectors=624 textures=1872 shapes=624 xiso_edits=3 changed=97048 source_unchanged=true runtime=false xemu_started=false"
