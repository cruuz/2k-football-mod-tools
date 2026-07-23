#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"

index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
inventory='reports/assets/nfl2k5_resource_chunks_v2.json'
xbe='extracted/ESPN NFL 2K5 (USA)/default.xbe'
header='reports/headers/nfl2k5_xbe_header.json'
trace='reports/assets/nfl_main_menu_font_ghidra/nfl_main_menu_font_trace.txt'
pseudo='reports/assets/nfl_main_menu_font_ghidra/nfl_main_menu_font_pseudo_c.c'
java='tools/ghidra_scripts/NflMainMenuFontTrace.java'
assets='assets/intermediate/nfl2k5/fonts'
report='reports/assets/nfl_main_menu_font.json'
fonts='reports/assets/nfl_main_menu_fonts.tsv'
glyphs='reports/assets/nfl_main_menu_font_glyphs.tsv'
doc='docs/research/nfl_main_menu_font.md'

for required in "$index" "$inventory" "$xbe" "$header" "$trace" "$pseudo" \
  "$java" "$report" "$fonts" "$glyphs" "$doc" \
  tools/nfl_main_menu_font.py; do
  test -f "$required"
done

python3 -m py_compile tools/nfl_main_menu_font.py
temporary=$(mktemp -d /tmp/nfl-main-menu-font.XXXXXX)
trap 'rm -rf "$temporary"' EXIT

PYTHONPATH=tools python3 tools/nfl_main_menu_font.py "$index" \
  --inventory "$inventory" \
  --xbe "$xbe" \
  --xbe-header "$header" \
  --trace "$trace" \
  --pseudo "$pseudo" \
  --ghidra-script "$java" \
  --assets-dir "$temporary/assets" \
  --json "$temporary/report.json" \
  --fonts-tsv "$temporary/fonts.tsv" \
  --glyphs-tsv "$temporary/glyphs.tsv"

cmp "$temporary/report.json" "$report"
cmp "$temporary/fonts.tsv" "$fonts"
cmp "$temporary/glyphs.tsv" "$glyphs"
test "$(find "$assets" -maxdepth 1 -type f -name '*.png' | wc -l)" -eq 10
test "$(find "$assets" -maxdepth 1 -type f -name '*.palette_tail.bin' | wc -l)" -eq 10
for regenerated in "$temporary"/assets/*; do
  cmp "$regenerated" "$assets/$(basename "$regenerated")"
done
test "$(wc -l < "$fonts")" -eq 11
test "$(wc -l < "$glyphs")" -eq 944

python3 - "$report" "$fonts" "$glyphs" "$assets" "$trace" "$pseudo" "$doc" <<'PY'
import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

report_path, fonts_path, glyphs_path, assets, trace_path, pseudo_path, doc_path = (
    Path(value) for value in sys.argv[1:])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "nfl2k5_main_menu_font/v1"
result = report["result"]
assert result == {
    "all_atlases_exported_as_png": True,
    "all_opaque_palette_tails_retained": True,
    "font_resources": 10,
    "glyph_records": 943,
    "main_menu_font_name": "font7",
    "main_menu_font_png": "assets/intermediate/nfl2k5/fonts/font7.png",
    "main_menu_font_slot": 6,
    "original_title_main_menu_execution_proved": False,
}

executable = report["executable"]
assert executable["md5"] == "444064a9ec984dd29d2c05a43f5c96e8"
assert executable["font_names"] == [
    "font1", "font2", "font3", "font4", "font5", "font6", "font7",
    "font8", "font9", "FirstPersonComic"]
assert len(executable["style_targets"]) == 15
assert executable["style_targets"][0] == "0x000f0300"
assert executable["style_targets"][8] == "0x000f0ac1"
assert len(executable["ranges"]) == 19
assert report["main_menu_renderer"]["main_row_observed_styles"] == [0, 8]
assert len(report["portme"]) == 3
assert all(value.startswith("// PORTME(") for value in report["portme"])

resources = report["resources"]
assert len(resources) == 10
assert sum(row["glyph_count"] for row in resources) == 943
expected_dimensions = {
    "font1": (256, 128), "font2": (256, 256), "font3": (256, 128),
    "font4": (128, 128), "font5": (256, 128), "font6": (256, 128),
    "font7": (256, 256), "font8": (256, 256), "font9": (128, 128),
    "FirstPersonComic": (256, 256),
}
for slot, row in enumerate(resources):
    assert row["slot"] == slot
    assert (row["width"], row["height"]) == expected_dimensions[row["name"]]
    assert row["maximum_quad_uv_error_pixels"] == 0.0
    assert row["palette_tail_bytes_retained"] == 960
    assert row["used_palette_indices"][0] == 0
    assert row["used_palette_indices"][-1] == 15
    assert set(row["used_palette_indices"]) <= set(range(16))
    assert len([candidate for candidate in row["dimension_candidates"]
                if candidate["maximum_quad_uv_error_pixels"] == 0.0]) == 1

with fonts_path.open(encoding="utf-8", newline="") as stream:
    font_rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(font_rows) == 10
font7 = font_rows[6]
assert font7["name"] == "font7" and font7["slot"] == "6"
assert font7["decoded_sha256"] == (
    "17ee70f82c080f6d392b2063a226edc513e2399c3b535a6d6e80d317bcaa313b")
assert (font7["width"], font7["height"]) == ("256", "256")
assert font7["glyph_count"] == "94"

with glyphs_path.open(encoding="utf-8", newline="") as stream:
    glyph_rows = list(csv.DictReader(stream, dialect="excel-tab"))
assert len(glyph_rows) == 943
capital_a = [row for row in glyph_rows
             if row["font"] == "font7" and row["codepoint"] == "0x0041"]
assert len(capital_a) == 1
capital_a = capital_a[0]
assert capital_a["advance"] == "23"
assert [capital_a[key] for key in ("atlas_x0", "atlas_y0", "atlas_x1", "atlas_y1")] == ["43", "20", "65", "38"]
assert [capital_a[key] for key in ("x0", "y0", "x1", "y1", "x2", "y2", "x3", "y3")] == ["0", "6", "22", "6", "0", "24", "22", "24"]

def parse_png(path):
    raw = path.read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    offset = 8
    ihdr = None
    compressed = bytearray()
    while offset < len(raw):
        size, = struct.unpack_from(">I", raw, offset)
        kind = raw[offset + 4:offset + 8]
        payload = raw[offset + 8:offset + 8 + size]
        crc, = struct.unpack_from(">I", raw, offset + 8 + size)
        assert zlib.crc32(kind + payload) & 0xffffffff == crc
        if kind == b"IHDR": ihdr = payload
        if kind == b"IDAT": compressed.extend(payload)
        offset += 12 + size
    assert ihdr is not None
    width, height, depth, color, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", ihdr)
    assert (depth, color, compression, filtering, interlace) == (8, 6, 0, 0, 0)
    scanlines = zlib.decompress(compressed)
    assert len(scanlines) == height * (1 + width * 4)
    assert all(scanlines[row * (1 + width * 4)] == 0 for row in range(height))
    pixels = b"".join(scanlines[row * (1 + width * 4) + 1:
                                 (row + 1) * (1 + width * 4)]
                      for row in range(height))
    assert set(pixels[0::4]) == {255} and set(pixels[1::4]) == {255}
    assert set(pixels[2::4]) == {255}
    alpha = set(pixels[3::4])
    assert min(alpha) == 0 and max(alpha) == 255
    assert alpha <= set(range(0, 256, 17))
    return width, height, sorted(value // 17 for value in alpha)

for row in resources:
    png = assets / (row["name"] + ".png")
    tail = assets / (row["name"] + ".palette_tail.bin")
    width, height, indices = parse_png(png)
    assert (width, height) == (row["width"], row["height"])
    assert indices == row["used_palette_indices"]
    assert len(tail.read_bytes()) == 960
    assert hashlib.sha256(png.read_bytes()).hexdigest() == row["png_sha256"]
    assert hashlib.sha256(tail.read_bytes()).hexdigest() == row["palette_tail_sha256"]

for source in report["source_pins"].values():
    source_path = Path(source["path"])
    assert source_path.stat().st_size == source["size"]
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source["sha256"]

trace = trace_path.read_text(encoding="utf-8")
pseudo = pseudo_path.read_text(encoding="utf-8")
for phrase in (
    "0x000EF57A MOV EDX,0x544e4f46",
    "0x0014FE7B MOV ECX,0x6",
    "0x0014FF38 CALL 0x000f1d50",
    "0x000F0B80 CALL 0x00047420",
    "0x000F0C29 CALL 0x00047420",
    "0x000464BD CALL 0x0002d2a0",
    "0x00049397 MOV EAX,dword ptr [ECX + 0x10]",
    "0x000493F3 MOV EAX,dword ptr [ESI + 0xc]",
):
    assert phrase in trace
assert "/* 0x000493E0:FUN_000493e0 */" in pseudo

doc = doc_path.read_text(encoding="utf-8")
for phrase in ("`font7`", "943", "field-local", "zero observed pixel error",
               "What worked", "What failed", "What is still blocking",
               "not original-title boot"):
    assert phrase in doc
PY

mode=normal
if [[ "${NFL_MAIN_MENU_FONT_GHIDRA:-0}" == 1 ]]; then
  mkdir -p "$temporary/ghidra"
  env \
    HOME="$root/tools/ghidra-home" \
    XDG_CONFIG_HOME="$root/tools/ghidra-home/.config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      "$root/ghidra_projects" nfl2k5 \
      -process default.xbe -readOnly -noanalysis \
      -scriptPath "$root/tools/ghidra_scripts" \
      -postScript NflMainMenuFontTrace.java "$temporary/ghidra"
  cmp "$temporary/ghidra/nfl_main_menu_font_trace.txt" "$trace"
  cmp "$temporary/ghidra/nfl_main_menu_font_pseudo_c.c" "$pseudo"
  mode=full
fi

echo "NFL_MAIN_MENU_FONT_VALIDATION_PASS mode=$mode fonts=10 glyphs=943 main_menu_slot=6 main_menu_font=font7 pngs=10"
