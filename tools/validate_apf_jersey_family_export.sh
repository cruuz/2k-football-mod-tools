#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

source_0a='extracted/All-Pro Football 2K8 (USA)/0A'
expected_source='dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e'
temporary="$(mktemp -d /tmp/apf-jersey-family-export.XXXXXX)"
trap 'rm -rf "$temporary"' EXIT

before="$(sha256sum "$source_0a" | cut -d' ' -f1)"
test "$before" = "$expected_source"

export PYTHONDONTWRITEBYTECODE=1
PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  mod_editor/__main__.py \
  mod_editor/core/apf_export.py \
  mod_editor/gui/tkinter_app.py \
  tools/apf_jersey_family_export.py \
  tests/mod_editor/test_apf_export.py \
  tests/mod_editor/test_gui.py \
  tests/apf_jersey_family_export_test.py

python3 -m unittest -v \
  tests/mod_editor/test_apf_export.py \
  tests/mod_editor/test_gui.py
python3 -m unittest -v tests/apf_jersey_family_export_test.py

help="$(python3 -m mod_editor --help)"
rg -q -- '--export-apf-jersey NEW_OUTPUT_DIR' <<<"$help"
rg -q -- '--source-0a SOURCE_0A' <<<"$help"
if rg -q -- '--entry|--offset' <<<"$help"; then
  echo 'public editor exposed a raw APF archive selector' >&2
  exit 1
fi

python3 tools/apf_jersey_family_export.py \
  --source-0a "$source_0a" \
  --asset-index 6 \
  --output-dir "$temporary/asset6"

if python3 tools/apf_jersey_family_export.py \
    --source-0a "$source_0a" --asset-index 6 --entry 875 \
    --output-dir "$temporary/raw-entry" >/dev/null 2>&1; then
  echo 'exporter accepted a raw outer entry argument' >&2
  exit 1
fi
test ! -e "$temporary/raw-entry"

if python3 tools/apf_jersey_family_export.py \
    --source-0a "$source_0a" --asset-index 24 \
    --output-dir "$temporary/invalid-asset" >/dev/null 2>&1; then
  echo 'exporter accepted asset index 24' >&2
  exit 1
fi
test ! -e "$temporary/invalid-asset"

python3 - "$temporary/asset6" <<'PY'
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from PIL import Image

output = Path(sys.argv[1])
provenance_path = output / "provenance.json"
payload = provenance_path.read_bytes()
report = json.loads(payload)
assert payload == (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
assert report["schema"] == "apf2k8_jersey_family_export/v1"
assert report["scope"] == {
    "game": "All-Pro Football 2K8 (USA)",
    "operation": "read-only jersey PNG and mip preview export",
    "archive_opened_for_write": False,
    "archive_bytes_written": False,
    "emulator_launched": False,
}
source = report["source"]
assert source["sha256_before"] == source["sha256_after"] == \
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
assert source["size"] == 1140850688
assert source["opened_read_only"] is True
assert source["identity_rechecked"] is True
target = report["target"]
assert target["asset_index"] == 6
assert target["outer_name"] == "uniform_jersey_06.iff"
assert target["outer_table_index"] == 875
assert target["fixed_allocation"] == 32768
assert target["entry_sha256"] == \
    "9f4740ddbbcc86d1d7a880a50f12d9e2580e049633b9beb065fc193a78130ca2"
assert target["texture_sha256"] == \
    "027e49dc8b1445cba4ec73c9cdadada15360ac755f87b5c4b6db6f8772c95cdf"

selector = report["selector_inventory"]
assert selector["sha256"] == \
    "d112710582b223d32425a79eedf321a2d9f61a01152c1c9d03b74f250231d82b"
assert selector["bank_labels"] == ["bank 0", "bank 1"]
assert selector["home_away_orientation_proved"] is False
assert selector["affected_use_count"] == 2
assert [(row["team_name"], row["bank_label"]) for row in
        selector["affected_team_bank_uses"]] == [
    ("Americans", "bank 0"), ("Americans", "bank 1")
]

levels = report["mip_previews"]
assert [row["level"] for row in levels] == list(range(9))
assert [(row["width"], row["height"]) for row in levels] == [
    (1024, 1024), (512, 512), (256, 256), (128, 128), (64, 64),
    (32, 32), (16, 16), (8, 8), (4, 4),
]
assert [row["level"] for row in levels if row["packed_tail"]] == [6, 7, 8]
for row in levels:
    path = output / row["png"]
    data = path.read_bytes()
    assert len(data) == row["png_size"]
    assert hashlib.sha256(data).hexdigest() == row["png_sha256"]
    with Image.open(path) as image:
        image.load()
        assert image.format == "PNG" and image.mode == "RGBA"
        assert image.size == (row["width"], row["height"])
        assert hashlib.sha256(image.tobytes()).hexdigest() == \
            row["decoded_rgba_sha256"]

base = report["base_png"]
assert base["same_pixels_as_mip_level"] == 0
assert (output / base["png"]).read_bytes() == (output / levels[0]["png"]).read_bytes()
assert report["output_contract"] == {
    "png_file_count": 10,
    "mip_level_count": 9,
    "provenance_created_last": True,
    "contains_raw_archive_entry": False,
    "contains_bc3_payload": False,
    "derived_retail_pixels_are_local_only": True,
}
expected = {"jersey_base.png", "provenance.json"} | {row["png"] for row in levels}
assert {path.name for path in output.iterdir()} == expected
assert not any(path.suffix in {".iff", ".bin"} for path in output.iterdir())
PY

after="$(sha256sum "$source_0a" | cut -d' ' -f1)"
test "$after" = "$before"

echo 'APF_JERSEY_FAMILY_EXPORT_VALIDATION_PASS asset=6 pngs=10 mips=9 teams=1 banks=2 editor_cli_gui=true mocked_editor_export=true raw_selector_args=false source_unchanged=yes archive_written=false'
