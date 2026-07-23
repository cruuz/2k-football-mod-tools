#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
resource_scan='reports/assets/nfl2k5_resource_chunks_v2.json'
scne_inventory='reports/assets/nfl2k5_scne_inventory.json'
source_textures='reports/assets/nfl2k5_scne_embedded_textures.tsv'
source_materials='reports/assets/nfl2k5_scne_material_textures.tsv'
asset_dir='assets/intermediate/nfl2k5/scne_textures'
logical_root='assets/intermediate/nfl2k5/scne_textures'
manifest='reports/assets/nfl2k5_scne_texture_png_manifest.json'
occurrences='reports/assets/nfl2k5_scne_texture_png_occurrences.tsv'
materials='reports/assets/nfl2k5_scne_texture_png_materials.tsv'
pngs='reports/assets/nfl2k5_scne_texture_pngs.tsv'

for required in \
  "$index" "$resource_scan" "$scne_inventory" "$source_textures" \
  "$source_materials" "$asset_dir" "$manifest" "$occurrences" "$materials" \
  "$pngs" reports/assets/nfl2k5_scne_texture_png.sha256 \
  tools/nfl_scne_embedded_texture_png.py \
  tools/nfl_scne_embedded_texture_png_validate.py \
  docs/research/nfl_scne_embedded_texture_png.md; do
  test -e "$required"
done

python3 -m py_compile \
  tools/nfl_scne_embedded_texture_png.py \
  tools/nfl_scne_embedded_texture_png_validate.py

test "$(wc -l < "$occurrences")" -eq 37390
test "$(wc -l < "$materials")" -eq 55906
test "$(wc -l < "$pngs")" -eq 5352
test "$(find "$asset_dir/by_rgba_sha256" -type f -name '*.png' | wc -l)" -eq 5351
test "$(sha256sum "$manifest" | cut -d' ' -f1)" = \
  aed638e2db18e89b7305a7130518fcac351c46a0bf03aeb0c32255f4f01227f0
test "$(sha256sum "$occurrences" | cut -d' ' -f1)" = \
  29ca8301e5044f3ed91e9ab6e778a78a8d06a3265097224f938f807cd276db3a
test "$(sha256sum "$materials" | cut -d' ' -f1)" = \
  bd04bd7a01c7bdf81cc2e21299b86115d1fde1f40126e4bf7e8d019f9ee11c27
test "$(sha256sum "$pngs" | cut -d' ' -f1)" = \
  5b640fc561ba9b73c5f9d0edde4e8903c241630d523f9c5edc1979277795e61c
(cd reports/assets && sha256sum -c nfl2k5_scne_texture_png.sha256)
grep -Fxq \
  '# logical_png_tree_sha256=720e6a2c0513e83abe8ab977cef3b8a8a8158dde39111207f4624e3d18c70fa0' \
  reports/assets/nfl2k5_scne_texture_png.sha256

python3 - "$manifest" "$occurrences" "$materials" "$pngs" <<'PY'
import csv
import json
from pathlib import Path
import sys

manifest_path, occurrence_path, material_path, png_path = map(Path, sys.argv[1:])
report = json.loads(manifest_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_scne_embedded_texture_png/v1"
assert report["asset_root"] == "assets/intermediate/nfl2k5/scne_textures"
assert report["format"] == {
    "bit_depth": 8,
    "channels": "RGBA",
    "color_type": 6,
    "container": "PNG",
    "deduplication_key": "SHA-256 of decoded width*height*4 RGBA bytes",
    "idat_zlib_level": 9,
    "interlace": 0,
    "path_template": "by_rgba_sha256/{sha256[0:2]}/{sha256}.png",
    "row_filter": 0,
    "signature": "89504e470d0a1a0a",
}
summary = report["summary"]
assert summary == {
    "all_material_occurrence_links_preserved": True,
    "all_material_pointer_fields_replayed": True,
    "all_source_descriptors_replayed": True,
    "all_source_rgba_hashes_match": True,
    "all_unique_png_ihdrs_match": True,
    "all_unique_png_rgba_hashes_match": True,
    "deduplicated_occurrence_count": 32038,
    "mapped_material_count": 45413,
    "material_row_count": 55905,
    "minimum_free_space_bytes": 10737418240,
    "occurrence_dimension_counts": {
        "128x128": 13053, "128x256": 8, "128x64": 1515,
        "16x16": 82, "256x128": 2505, "256x256": 2729,
        "256x32": 2, "32x32": 1347, "512x256": 35,
        "512x512": 35, "64x128": 64, "64x32": 173,
        "64x64": 15829, "8x8": 12,
    },
    "p8_occurrence_count": 37389,
    "png_count": 5351,
    "png_tree_has_no_missing_or_extra_files": True,
    "represented_scene_count": 4007,
    "scene_count": 4616,
    "texture_occurrence_count": 37389,
    "total_png_bytes": 58969124,
    "unique_png_dimension_counts": {
        "128x128": 1978, "128x256": 5, "128x64": 180,
        "16x16": 17, "256x128": 641, "256x256": 437,
        "256x32": 1, "32x32": 183, "512x256": 14,
        "512x512": 35, "64x128": 29, "64x32": 50,
        "64x64": 1780, "8x8": 1,
    },
    "unique_rgba_count": 5351,
    "unmapped_material_count": 10492,
    "unreferenced_texture_occurrence_count": 157,
}
assert report["evidence"] == {
    "material_texture_pointer": "SCNE material record +0x30",
    "palette_storage": "BGRA8 converted to RGBA8",
    "pixel_layout": "Xbox 2D swizzle decoded by verified nfl_txtr.unswizzle_2d",
    "semantic_limit": "mapping proves material occurrence -> descriptor, not shader slot or baseColor use",
    "texture_descriptor_stride": 32,
    "xbox_format": "P8 (0x0B)",
}
assert len(report["occurrences"]) == 37389
assert len(report["materials"]) == 55905
assert len(report["pngs"]) == 5351
assert all(item.startswith("PORTME:") for item in report["portme"])

with occurrence_path.open(encoding="utf-8", newline="") as stream:
    occurrence_rows = list(csv.DictReader(stream, dialect="excel-tab"))
with material_path.open(encoding="utf-8", newline="") as stream:
    material_rows = list(csv.DictReader(stream, dialect="excel-tab"))
with png_path.open(encoding="utf-8", newline="") as stream:
    png_rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(occurrence_rows) == 37389
assert len(material_rows) == 55905
assert len(png_rows) == 5351
assert sum(row["mapping_status"] == "mapped_embedded_texture" for row in material_rows) == 45413
assert sum(row["mapping_status"] == "unmapped" for row in material_rows) == 10492
assert sum(int(row["mapped_material_count"]) == 0 for row in occurrence_rows) == 157
assert all(row["format_name"] == "P8" for row in occurrence_rows)
assert all(row["conversion_status"] == "base_level_supported" for row in occurrence_rows)
assert all(row["rgba_sha256"] == Path(row["png_path"]).stem for row in png_rows)
print("NFL_SCNE_EMBEDDED_TEXTURE_PNG_MANIFEST_ASSERTIONS_PASS")
PY

PYTHONPATH=tools python3 tools/nfl_scne_embedded_texture_png_validate.py \
  --manifest "$manifest" \
  --occurrences "$occurrences" \
  --materials "$materials" \
  --pngs "$pngs" \
  --source-textures "$source_textures" \
  --source-materials "$source_materials" \
  --asset-dir "$root/$asset_dir" \
  --minimum-free-gib 10 | tee /tmp/nfl-scne-texture-png-validation.out
grep -Fq \
  'tree_sha256=720e6a2c0513e83abe8ab977cef3b8a8a8158dde39111207f4624e3d18c70fa0' \
  /tmp/nfl-scne-texture-png-validation.out
rm -f /tmp/nfl-scne-texture-png-validation.out

if [[ ${NFL_SCNE_TEXTURE_PNG_FULL_REGEN:-0} == 1 ]]; then
  temporary=$(mktemp -d "$root/.nfl-scne-texture-png-regen.XXXXXX")
  trap 'rm -rf "$temporary"' EXIT
  python3 tools/nfl_scne_embedded_texture_png.py \
    "$index" \
    --resource-scan "$resource_scan" \
    --scne-inventory "$scne_inventory" \
    --textures "$source_textures" \
    --materials "$source_materials" \
    --asset-dir "$temporary/assets" \
    --logical-asset-root "$logical_root" \
    --manifest-json "$temporary/manifest.json" \
    --occurrences-tsv "$temporary/occurrences.tsv" \
    --materials-tsv "$temporary/materials.tsv" \
    --pngs-tsv "$temporary/pngs.tsv" \
    --minimum-free-gib 10 \
    --progress-every 500
  cmp "$temporary/manifest.json" "$manifest"
  cmp "$temporary/occurrences.tsv" "$occurrences"
  cmp "$temporary/materials.tsv" "$materials"
  cmp "$temporary/pngs.tsv" "$pngs"
  diff -qr "$temporary/assets/by_rgba_sha256" "$asset_dir/by_rgba_sha256"
  PYTHONPATH=tools python3 tools/nfl_scne_embedded_texture_png_validate.py \
    --manifest "$temporary/manifest.json" \
    --occurrences "$temporary/occurrences.tsv" \
    --materials "$temporary/materials.tsv" \
    --pngs "$temporary/pngs.tsv" \
    --source-textures "$source_textures" \
    --source-materials "$source_materials" \
    --asset-dir "$temporary/assets" \
    --minimum-free-gib 10
  echo NFL_SCNE_EMBEDDED_TEXTURE_PNG_FULL_REGEN_PASS
fi

echo 'NFL_SCNE_EMBEDDED_TEXTURE_PNG_GATE_PASS occurrences=37389 unique_png=5351 materials=55905'
