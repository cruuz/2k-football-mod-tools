#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

inventory=reports/assets/nfl2k5_create_team_field_art_inventory.json
table=reports/assets/nfl2k5_create_team_field_art_inventory.tsv
fixture=reports/assets/nfl2k5_create_team_field_art_fixture_256x128.png
plan=reports/assets/nfl2k5_create_team_field_art_proof_plan.json
workflow=build/nfl2k5-create-team-field-art-workflow-20260712/workflow.json
output=build/nfl2k5-create-team-field-art-workflow-20260712/ESPN-NFL-2K5-ct67D-live-field-art.xiso.iso
source='ESPN NFL 2K5 (USA).xiso.iso'
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT

verify_mode=()
if [[ ! -e "$output" && ! -L "$output" ]]; then
  verify_mode=(--virtual-output)
fi

python3 tools/nfl_create_team_field_art_inventory.py \
  --json "$temporary/inventory.json" --tsv "$temporary/inventory.tsv" >/dev/null
cmp "$temporary/inventory.json" "$inventory"
cmp "$temporary/inventory.tsv" "$table"

python3 tools/nfl_create_team_field_art_png_import.py \
  --logo-code 67 --weather D --texture endzone_north_middle \
  --png "$fixture" --output-dir "$temporary/compressed" >/dev/null
python3 tools/nfl_create_team_field_art_png_import.py \
  --logo-code 72 --weather D --texture endzone_north_left \
  --png "$fixture" --output-dir "$temporary/raw" >/dev/null

python3 tools/nfl_create_team_field_art_xiso_verify.py \
  --source-xiso "$source" --output-xiso "$output" \
  "${verify_mode[@]}" --manifest "$workflow" >/dev/null

python3 - "$inventory" "$table" "$fixture" "$plan" "$workflow" \
  "$temporary/compressed/import.json" "$temporary/raw/import.json" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import sys

inventory_path, table_path, fixture_path, plan_path, workflow_path, compressed_path, raw_path = map(Path, sys.argv[1:])
inventory = json.loads(inventory_path.read_text())
rows = list(csv.DictReader(table_path.open(), delimiter="\t"))
plan = json.loads(plan_path.read_text())
workflow = json.loads(workflow_path.read_text())
compressed = json.loads(compressed_path.read_text())
raw = json.loads(raw_path.read_text())

assert inventory["schema"] == "nfl2k5_create_team_field_art_inventory/v1"
assert inventory["summary"]["package_count"] == 126
assert inventory["summary"]["logo_code_count"] == 42
assert inventory["summary"]["weather_variant_count"] == 3
assert inventory["summary"]["texture_count"] == 1134
assert inventory["summary"]["compressed_texture_count"] == 1125
assert inventory["summary"]["raw_texture_count"] == 9
assert inventory["summary"]["format_counts"] == {"P8": 1134}
assert len(rows) == 1134
assert {row["weather_suffix"] for row in rows} == {"D", "R", "S"}
assert {row["name"] for row in rows} == {
    "center_logo", "endzone_north_left", "endzone_north_middle",
    "endzone_north_right", "endzone_south_left", "endzone_south_middle",
    "endzone_south_right", "pad_north", "pad_south",
}
assert inventory["selector_space"]["logo_codes"] == [33, *range(50, 86), *range(95, 100)]
assert inventory["selector_space"]["weather_suffixes"] == {
    "D": "dry", "R": "rain", "S": "snow"
}
owner = inventory["xbe_runtime_owner"]
assert owner["selector"]["filename_format"] == "ct%s%c.iff"
assert owner["selector"]["active_team_logo_code_field_offset"] == "0x14"
assert owner["resource_registration"]["resource_label"] == "CTGRAPHIC"
assert owner["live_field_owner"]["field_object_name"] == "field"
assert len(owner["live_field_owner"]["field_material_binding_table"]) == 7
ranges = {row["name"]: row for row in owner["function_ranges"]}
assert ranges["goalpost_pad_texture_binder"] == {
    "end_exclusive": "0x0009856d",
    "name": "goalpost_pad_texture_binder",
    "sha256": "85166dafd74a489484dc057fac7319d71ef5210fd35fa8eb4e3710c6f0cb4406",
    "size": 845,
    "start": "0x00098220",
}
assert ranges["field_material_texture_binder"] == {
    "end_exclusive": "0x0009c66b",
    "name": "field_material_texture_binder",
    "sha256": "08783d9fde6cd5caa90390f210125f5187ed0a8c295051651012dff9a61071cc",
    "size": 141,
    "start": "0x0009c5de",
}
assert owner["live_field_owner"]["field_material_binding_loop"] == {
    "end_exclusive": "0x0009c66b",
    "material_texture_pointer_field": "+0x30",
    "start": "0x0009c5de",
    "table_end_exclusive": "0x004f00c8",
    "table_start": "0x004f0090",
    "texture_lookup_fourcc": "TXTR",
    "texture_pointer_store": "0x0009c659",
}
assert owner["live_field_owner"]["goalpost_pad_owner"]["resources"] == [
    "pad_north", "pad_south"
]
assert owner["live_field_owner"]["goalpost_pad_owner"]["scene_name"] == "goalpost"
assert owner["live_field_owner"]["goalpost_pad_owner"]["material_name"] == "pad"
assert owner["live_field_owner"]["goalpost_pad_owner"]["texture_pointer_store"] == \
    "0x00098409"
assert inventory["claims"]["static_live_field_owner_proved"] is True
assert inventory["claims"]["menu_or_team_select_imagery"] is False
assert inventory["claims"]["runtime_visibility_proved"] is False

fixture = fixture_path.read_bytes()
assert hashlib.sha256(fixture).hexdigest() == "60e11ffe36ace2c8c35cd96c2178238537ead5680d18d58e51284b34c9a38eff"
assert plan["schema"] == "nfl2k5_create_team_field_art_plan/v1"
assert plan["edits"] == [{
    "logo_code": 67,
    "png": str(fixture_path.resolve()),
    "texture": "endzone_north_middle",
    "weather": "D",
}]

assert compressed["target"]["selector"] == "67:D:endzone_north_middle"
assert compressed["target"]["outer_index"] == 402
assert compressed["target"]["outer_id"] == "0x537b555d"
assert compressed["compression"]["mode"] == "vc_lz_fixed_span"
assert compressed["compression"]["fixed_span_fit"] is True
assert compressed["rebuild"]["changed_byte_count"] == 38156
assert compressed["rebuild"]["system_bytes_preserved"] is True
assert compressed["claims"]["runtime_visibility_proved"] is False
assert raw["target"]["selector"] == "72:D:endzone_north_left"
assert raw["compression"]["mode"] == "raw"
assert raw["rebuild"]["system_bytes_preserved"] is True

assert workflow["schema"] == "nfl2k5_create_team_field_art_xiso_workflow/v1"
assert len(workflow["edits"]) == 1
assert workflow["edits"][0]["selector"] == "67:D:endzone_north_middle"
assert workflow["edits"][0]["replacement_span_sha256"] == compressed["rebuild"]["span_sha256"]
assert workflow["patch"]["actual_changed_byte_count"] == 38156
assert workflow["patch"]["all_other_xiso_bytes_identical"] is True
assert workflow["output"]["xiso_sha256"] == "a698055f9da7809f039e8569b963f6803c30ed2e6657b6c9ad1f20193296d441"
assert workflow["xdvdfs"]["tree_identical_after_patch"] is True
assert workflow["xdvdfs"]["all_sector_extents_preserved"] is True
assert workflow["claims"]["runtime_visibility_proved"] is False
assert workflow["claims"]["xemu_started"] is False
assert workflow["claims"]["title_executed"] is False
PY

# The importer and plan parser must fail closed on symlinks and bool-as-int.
ln -s "$root/$fixture" "$temporary/fixture-link.png"
ln -s "$root/$plan" "$temporary/plan-link.json"
if python3 tools/nfl_create_team_field_art_png_import.py \
  --logo-code 67 --weather D --texture endzone_north_middle \
  --png "$temporary/fixture-link.png" --output-dir "$temporary/symlink-output" \
  >"$temporary/symlink.stdout" 2>"$temporary/symlink.stderr"; then
  echo 'symlink PNG was accepted' >&2
  exit 1
fi
rg -q 'non-symlink regular file' "$temporary/symlink.stderr"

python3 - "$temporary/bad-plan.json" <<'PY'
import json
from pathlib import Path
import sys
value = {
    "edits": [{
        "logo_code": True,
        "png": "/tmp/does-not-matter.png",
        "texture": "endzone_north_middle",
        "weather": "D",
    }],
    "purpose": "type refusal",
    "schema": "nfl2k5_create_team_field_art_plan/v1",
}
Path(sys.argv[1]).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
PY
python3 - "$temporary/bad-plan.json" "$temporary/plan-link.json" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, "tools")
from nfl_create_team_field_art_xiso_workflow import read_plan, WorkflowError
for path, expected in ((Path(sys.argv[1]), "fields/types"),
                       (Path(sys.argv[2]), "non-symlink regular file")):
    try:
        read_plan(path)
    except (OSError, WorkflowError) as exc:
        assert expected in str(exc)
    else:
        raise SystemExit(f"invalid plan was accepted: {path}")
PY

test "$(sha256sum "$source" | cut -d' ' -f1)" = \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9
test "$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' | cut -d' ' -f1)" = \
  34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d
test "$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/default.xbe' | cut -d' ' -f1)" = \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9
if [[ -e "$output" ]]; then
  test "$(sha256sum "$output" | cut -d' ' -f1)" = \
    a698055f9da7809f039e8569b963f6803c30ed2e6657b6c9ad1f20193296d441
else
  test "${verify_mode[*]}" = '--virtual-output'
fi

echo 'NFL_CREATE_TEAM_FIELD_ART_PIPELINE_VALIDATION_PASS packages=126 textures=1134 compressed=1125 raw=9 target=67:D:endzone_north_middle changed=38156 xdvdfs_identical=true runtime=false xemu_started=false originals_unchanged=yes'
