#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

python3 -m py_compile \
  tools/nfl_outer.py \
  tools/nfl_txtr.py \
  tools/nfl_resource_scan.py \
  tools/nfl_all_texture_inventory.py

jq -e '
  .summary.outer_entry_count == 4323 and
  .summary.structured_prefix_entry_count == 4276 and
  .summary.resource_chunk_count == 86882 and
  .summary.txtr_chunk_count == 57208 and
  .summary.txtr_outer_entry_count == 3332 and
  .summary.padded_successor_count == 12355 and
  .summary.trailing_region_count == 46 and
  .summary.resource_kind_counts.SHAP == 1251 and
  .summary.resource_kind_counts.SCNE == 4616
' reports/assets/nfl2k5_resource_chunks_v2.json >/dev/null

jq -e '
  .selection.located_txtr_count == 57208 and
  .selection.validate_conversion == true and
  .selection.png_exports_base_mip_only == true and
  .summary.located_texture_count == 57208 and
  .summary.decoded_texture_count == 57208 and
  .summary.error_count == 0 and
  .summary.format_counts == {
    "A1R5G5B5": 4760,
    "A8R8G8B8": 2538,
    "DXT1": 1876,
    "P8": 47399,
    "VC_P8_LINEAR": 635
  } and
  .summary.conversion_status_counts == {"base_level_supported": 57208}
' reports/assets/nfl2k5_all_txtr_inventory_v2.json >/dev/null

test "$(wc -l < reports/assets/nfl2k5_all_txtr_inventory_v2.tsv)" -eq 57209
test "$(find assets/intermediate/nfl2k5/textures -type f -name '*.png' | wc -l)" -eq 57208

test "$(sha256sum assets/intermediate/nfl2k5/textures/outer_0024_f71cabe5/0000_00_teamlogo_00_h0.png | cut -d' ' -f1)" = \
  b9b5f420966deaecd532661257b7b909fc14d2d10448ee4154201ae3fa242d55
test "$(sha256sum assets/intermediate/nfl2k5/textures/outer_1198_900cfdaf/0000_h0002.png | cut -d' ' -f1)" = \
  7d480346c80db81265dbca16d9e9c60f89a5dec5fe62f71d1337e1f43a82317b
test "$(sha256sum assets/intermediate/nfl2k5/textures/outer_3613_341ecd96/0043_names.png | cut -d' ' -f1)" = \
  afa6067233a81961d0da317e6fc266f773941a03387d5cef938b08c7c65db154
test "$(sha256sum assets/intermediate/nfl2k5/textures/outer_3613_341ecd96/0045_bump_jersey.png | cut -d' ' -f1)" = \
  d530046ec0958db89fb9f72bfa1f2c1149f255bda0e108a4234843afcacc1ab1

python3 - <<'PY'
import json
import struct
from pathlib import Path

manifest = json.loads(
    Path("reports/assets/nfl2k5_all_txtr_inventory_v2.json").read_text(encoding="utf-8")
)
textures = manifest["textures"]
keys = {(item["outer_index"], item["chunk_index"]) for item in textures}
paths = [Path(item["png_path"]) for item in textures]
if len(keys) != 57208:
    raise SystemExit(f"non-unique outer/chunk identities: {len(keys)}")
if len({str(path) for path in paths}) != 57208:
    raise SystemExit("non-unique PNG output paths")

signature = b"\x89PNG\r\n\x1a\n"
for item, path in zip(textures, paths):
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != signature or header[12:16] != b"IHDR":
        raise SystemExit(f"invalid PNG header: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width != item["width"] or height != item["height"]:
        raise SystemExit(
            f"PNG dimensions differ from descriptor for {path}: "
            f"{width}x{height} vs {item['width']}x{item['height']}"
        )
    if "rgba_sha256" not in item:
        raise SystemExit(f"missing conversion hash: {path}")

print("NFL_TEXTURE_VALIDATION_PASS")
print(f"textures={len(textures)}")
print(f"pngs={len(paths)}")
PY
