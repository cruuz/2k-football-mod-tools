#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

test ! -e assets/mod/common/ui/nfl2k5_font7.png
test ! -e assets/mod/common/ui/nfl2k5_font7.metrics.tsv
test -f assets/mod/common/ui/nfl2k5_font7_override.schema.txt

TEMPORARY="$temporary" python3 - <<'PY'
import csv
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


report_path = Path("reports/assets/nfl_main_menu_font.json")
glyph_path = Path("reports/assets/nfl_main_menu_font_glyphs.tsv")
atlas_path = Path("assets/intermediate/nfl2k5/fonts/font7.png")
metrics_path = Path("assets/intermediate/nfl2k5/fonts/font7.metrics.tsv")
report = json.loads(report_path.read_text())
font7 = next(row for row in report["resources"] if row["name"] == "font7")
assert font7["slot"] == 6
assert font7["width"] == 256 and font7["height"] == 256
assert font7["glyph_count"] == 94
assert font7["line_advance"] == 25 and font7["space_advance"] == 9
assert font7["png_path"] == str(atlas_path)
assert digest(atlas_path) == font7["png_sha256"] == (
    "627ad377e33d56d0da9d0dd3bd9b29fea534e89e21fb33a491ef1d73b9ab35fa"
)

with glyph_path.open(newline="") as stream:
    rows = [row for row in csv.DictReader(stream, delimiter="\t")
            if row["slot"] == "6" and row["font"] == "font7"]
assert len(rows) == 94
lines = [
    "# schema=vc_bitmap_font_metrics_v1",
    "# representation=recovered_host_representation",
    "# source=reports/assets/nfl_main_menu_font_glyphs.tsv slot=6 font=font7",
    "# boundary=host-renderable metrics derived from title data; not original LAYT coordinates or boot execution",
    "atlas_width=256",
    "atlas_height=256",
    "line_advance=25",
    "space_advance=9",
    "codepoint\tadvance\tleft\ttop\tright\tbottom\tatlas_left\tatlas_top\tatlas_right\tatlas_bottom",
]
for row in rows:
    assert row["x0"] == row["x2"] and row["x1"] == row["x3"]
    assert row["y0"] == row["y1"] and row["y2"] == row["y3"]
    lines.append("\t".join([
        row["codepoint"], row["advance"], row["x0"], row["y0"],
        row["x1"], row["y2"], row["atlas_x0"], row["atlas_y0"],
        row["atlas_x1"], row["atlas_y1"],
    ]))
rebuilt = ("\n".join(lines) + "\n").encode()
assert metrics_path.read_bytes() == rebuilt
assert digest(metrics_path) == (
    "849c7d6706029c3a90d108ab961defe35eb98c74ba6d7584efe429f20aa32374"
)
Path(os.environ["TEMPORARY"], "rebuilt.metrics.tsv").write_bytes(rebuilt)

schema = Path(
    "assets/mod/common/ui/nfl2k5_font7_override.schema.txt"
).read_text()
assert "intentionally does not contain extracted retail font pixels" in schema
assert "recovered host-representation seam" in schema
assert "LAYT coordinates" in schema
PY

cmp assets/intermediate/nfl2k5/fonts/font7.metrics.tsv \
  "$temporary/rebuilt.metrics.tsv"

strict=(
  -std=c11 -Wall -Wextra -Wpedantic -Wconversion -Wshadow -Werror
  -Iinclude
)
for compiler in gcc clang-18; do
  "$compiler" "${strict[@]}" \
    tests/nfl_bitmap_font_test.c \
    src/assets/bitmap_font_metrics.c -lm \
    -o "$temporary/nfl_bitmap_font_${compiler//[^a-zA-Z0-9]/_}"
  "$temporary/nfl_bitmap_font_${compiler//[^a-zA-Z0-9]/_}" \
    assets/intermediate/nfl2k5/fonts/font7.metrics.tsv \
    | tee "$temporary/${compiler}.log"
  grep -q "NFL_BITMAP_FONT_NATIVE_PASS" "$temporary/${compiler}.log"
done

gcc "${strict[@]}" -O1 -g -fsanitize=address,undefined \
  -fno-omit-frame-pointer \
  tests/nfl_bitmap_font_test.c src/assets/bitmap_font_metrics.c -lm \
  -o "$temporary/nfl_bitmap_font_sanitize"
ASAN_OPTIONS=detect_leaks=1 \
  "$temporary/nfl_bitmap_font_sanitize" \
    assets/intermediate/nfl2k5/fonts/font7.metrics.tsv \
    > "$temporary/sanitize.log"
grep -q "NFL_BITMAP_FONT_NATIVE_PASS" "$temporary/sanitize.log"

PYTHONPYCACHEPREFIX="$temporary/pycache" python3 -m py_compile \
  tests/nfl_bitmap_font_screenshot_test.py

mapfile -t native_sources < <(find src -type f -name '*.c' -print | sort)
read -r -a native_cflags <<< "$(pkg-config --cflags sdl2 glew openal libpng assimp)"
read -r -a native_libs <<< "$(pkg-config --libs sdl2 glew openal libpng assimp)"
for compiler in gcc clang-18; do
  "$compiler" "${strict[@]}" -D_POSIX_C_SOURCE=200809L \
    -DVC_PORT_VERSION='"font7-native-test"' \
    -DVC_INSTALL_ASSET_RELATIVE='"../share/vc-font-test"' \
    "${native_cflags[@]}" "${native_sources[@]}" \
    "${native_libs[@]}" -lm \
    -o "$temporary/vc_football_port_${compiler//[^a-zA-Z0-9]/_}"
  "$temporary/vc_football_port_${compiler//[^a-zA-Z0-9]/_}" --help \
    > "$temporary/help-${compiler}.log"
  grep -q -- "--nfl-font-atlas PNG" "$temporary/help-${compiler}.log"
done

if "$temporary/vc_football_port_gcc" \
    --nfl-font-atlas /missing/font.png > "$temporary/unpaired.log" 2>&1; then
  echo "unpaired NFL font override unexpectedly succeeded" >&2
  exit 1
fi
grep -q "requires both atlas PNG and metrics TSV" "$temporary/unpaired.log"

gl_runner=()
smoke=no_display
if command -v xvfb-run >/dev/null 2>&1; then
  gl_runner=(xvfb-run -a)
  smoke=xvfb
elif [[ -n "${DISPLAY:-}" ]]; then
  smoke=display
fi
if [[ "$smoke" != no_display ]]; then
  "${gl_runner[@]}" "$temporary/vc_football_port_gcc" \
    --menu nfl2k5 --smoke 3 \
    --screenshot "$temporary/nfl-font7.png" \
    > "$temporary/font7-smoke.log" 2>&1
  grep -q "menu font source: title-derived intermediate" \
    "$temporary/font7-smoke.log"
  grep -q "bitmap font: loaded font7 recovered host representation" \
    "$temporary/font7-smoke.log"
  grep -q "original LAYT coordinates and boot are not claimed" \
    "$temporary/font7-smoke.log"
  grep -q "SMOKE PASS: rendered 3 frames" "$temporary/font7-smoke.log"
  if grep -q "row labels use the 5x7 host fallback" \
      "$temporary/font7-smoke.log"; then
    echo "font7 smoke unexpectedly used the fallback" >&2
    exit 1
  fi

  "${gl_runner[@]}" "$temporary/vc_football_port_gcc" \
    --menu nfl2k5 \
    --nfl-font-atlas "$temporary/missing.png" \
    --nfl-font-metrics "$temporary/missing.metrics.tsv" \
    --smoke 3 --screenshot "$temporary/nfl-fallback.png" \
    > "$temporary/fallback-smoke.log" 2>&1
  grep -q "menu font source: explicit loose override" \
    "$temporary/fallback-smoke.log"
  grep -q "row labels use the 5x7 host fallback" \
    "$temporary/fallback-smoke.log"
  grep -q "SMOKE PASS: rendered 3 frames" "$temporary/fallback-smoke.log"

  python3 tests/nfl_bitmap_font_screenshot_test.py \
    "$temporary/nfl-font7.png" "$temporary/nfl-fallback.png" \
    | tee "$temporary/screenshot.log"
  grep -q "NFL_BITMAP_FONT_SCREENSHOT_PASS" "$temporary/screenshot.log"
fi

echo "NFL_BITMAP_FONT_NATIVE_VALIDATION_PASS glyphs=94 atlas=256x256 line=25 space=9 representation=recovered_host_representation smoke=$smoke"
