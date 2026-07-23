#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT

before_nfl_xbe="$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/default.xbe' | cut -d' ' -f1)"
before_nfl_index="$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' | cut -d' ' -f1)"
before_nfl_xiso="$(sha256sum 'ESPN NFL 2K5 (USA).xiso.iso' | cut -d' ' -f1)"
before_apf_xex="$(sha256sum 'extracted/All-Pro Football 2K8 (USA)/default.xex' | cut -d' ' -f1)"
before_apf_index="$(sha256sum 'extracted/All-Pro Football 2K8 (USA)/0A' | cut -d' ' -f1)"

python3 -m py_compile \
  tools/scorebug_presentation_audit.py \
  tools/nfl_scorebug_fixture.py \
  tools/nfl_scorebug_png_import.py \
  tools/nfl_scorebug_png_import_verify.py \
  tools/nfl_scorebug_xiso_workflow.py \
  tools/nfl_scorebug_xiso_verify.py

clang++-18 -std=c++20 -O2 \
  tools/xex_extract_pe.cpp \
  -Itools/vendor/XenonRecomp/XenonUtils \
  -Itools/vendor/XenonRecomp/thirdparty/TinySHA1 \
  -Itools/vendor/XenonRecomp/thirdparty/tiny-AES-c \
  tools/vendor/XenonRecomp/build/XenonUtils/libXenonUtils.a \
  -o "$temporary/xex_extract_pe"

"$temporary/xex_extract_pe" \
  'extracted/All-Pro Football 2K8 (USA)/default.xex' \
  "$temporary/apf2k8_default.pe"

python3 tools/scorebug_presentation_audit.py \
  --apf-pe "$temporary/apf2k8_default.pe" \
  --json-out "$temporary/audit.json" \
  --tsv-out "$temporary/resources.tsv"
cmp reports/assets/scorebug_presentation_audit.json "$temporary/audit.json"
cmp reports/assets/scorebug_presentation_resources.tsv "$temporary/resources.tsv"

python3 tools/nfl_scorebug_fixture.py --output-dir "$temporary/fixtures"
for name in \
    manifest.json \
    score_buga_diagnostic.png \
    shield_espn_diagnostic.png \
    digital_font_diagnostic.png; do
  cmp "reports/assets/nfl2k5_scorebug_fixtures/$name" "$temporary/fixtures/$name"
done

for target in score_buga shield_espn digital_font; do
  python3 tools/nfl_scorebug_png_import.py \
    --target "$target" \
    --png "$temporary/fixtures/${target}_diagnostic.png" \
    --output-dir "$temporary/import-$target"
  python3 tools/nfl_scorebug_png_import_verify.py \
    --target "$target" \
    --png "$temporary/fixtures/${target}_diagnostic.png" \
    --output-dir "$temporary/import-$target"
done

ln -s "$temporary/fixtures/score_buga_diagnostic.png" "$temporary/symlink.png"
if python3 tools/nfl_scorebug_png_import.py \
    --target score_buga --png "$temporary/symlink.png" \
    --output-dir "$temporary/reject-symlink" >/dev/null 2>&1; then
  echo "scorebug importer accepted a symlink PNG" >&2
  exit 1
fi

cp reports/assets/scorebug_presentation_audit.json "$temporary/forged-audit.json"
printf '\n' >> "$temporary/forged-audit.json"
if python3 tools/nfl_scorebug_png_import.py \
    --audit "$temporary/forged-audit.json" --target score_buga \
    --png "$temporary/fixtures/score_buga_diagnostic.png" \
    --output-dir "$temporary/reject-forged" >/dev/null 2>&1; then
  echo "scorebug importer accepted a forged audit" >&2
  exit 1
fi

PYTHONPATH=tools python3 - "$temporary/wrong-size.png" "$temporary/noise.png" <<'PY'
from pathlib import Path
import random
import sys
from nfl_txtr import encode_rgba_png

wrong = bytes((1, 2, 3, 255)) * (63 * 64)
Path(sys.argv[1]).write_bytes(encode_rgba_png(63, 64, wrong))
rng = random.Random(0x2C5)
noise = bytes(rng.randrange(256) for _ in range(64 * 64 * 4))
Path(sys.argv[2]).write_bytes(encode_rgba_png(64, 64, noise))
PY

if python3 tools/nfl_scorebug_png_import.py \
    --target score_buga --png "$temporary/wrong-size.png" \
    --output-dir "$temporary/reject-size" >/dev/null 2>&1; then
  echo "scorebug importer accepted a wrong-size PNG" >&2
  exit 1
fi

if python3 tools/nfl_scorebug_png_import.py \
    --target score_buga --png "$temporary/noise.png" \
    --output-dir "$temporary/reject-noise" >/dev/null 2>&1; then
  echo "scorebug importer unexpectedly fit deterministic high-entropy noise" >&2
  exit 1
fi

if python3 tools/nfl_scorebug_png_import.py \
    --target score_buga \
    --png "$temporary/fixtures/score_buga_diagnostic.png" \
    --output-dir "$temporary/import-score_buga" >/dev/null 2>&1; then
  echo "scorebug importer overwrote an existing output directory" >&2
  exit 1
fi

if python3 tools/nfl_scorebug_xiso_workflow.py \
    --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
    --output-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
    --manifest "$temporary/alias.json" --preview "$temporary/alias.png" \
    --target score_buga \
    --png "$temporary/fixtures/score_buga_diagnostic.png" >/dev/null 2>&1; then
  echo "scorebug XISO workflow accepted source overwrite" >&2
  exit 1
fi

python3 tools/nfl_scorebug_xiso_verify.py \
  --source-xiso 'ESPN NFL 2K5 (USA).xiso.iso' \
  --output-xiso \
    build/nfl2k5-scorebug-workflow-20260712/ESPN-NFL-2K5-scorebug-magenta.xiso.iso \
  --manifest build/nfl2k5-scorebug-workflow-20260712/workflow.json \
  --preview build/nfl2k5-scorebug-workflow-20260712/preview.png \
  --target score_buga \
  --png reports/assets/nfl2k5_scorebug_fixtures/score_buga_diagnostic.png

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

audit_path = Path("reports/assets/scorebug_presentation_audit.json")
audit = json.loads(audit_path.read_text())
assert hashlib.sha256(audit_path.read_bytes()).hexdigest() == \
    "57bcbb1c0ff8e6c2376565365aba523e4c2fe8cdb66d3a7058daa84993c2ccd1"
assert audit["schema"] == "vc_scorebug_presentation_audit/v1"
assert len(audit["nfl2k5"]["compiled_owner"]["bindings"]) == 11
textures = [row["texture"] for row in audit["nfl2k5"]["compiled_owner"]["bindings"]]
assert textures.count("score_buga") == 9
assert textures.count("shield_espn") == 2
targets = {row["name"]: row for row in audit["nfl2k5"]["texture_targets"]}
assert set(targets) == {"score_buga", "shield_espn", "digital_font"}
assert targets["score_buga"]["xiso_absolute_span_offset"] == 1741540432
assert targets["score_buga"]["safe_write_class"] == \
    "fixed_span_png_writeback_ready"
assert targets["digital_font"]["safe_write_class"].endswith("global_side_effects")
apf = audit["apf2k8"]
assert len(apf["field_scorebug_package"]["resources"]) == 7
assert all(row["safe_write_class"] == "gltf_extract_only_no_scne_serializer"
           for row in apf["field_scorebug_package"]["resources"])
assert apf["digital_font"]["metadata"]["format_name"] == "DXT5A"
# This label is part of the frozen v1 authority used by retained NFL builds.
# The current capability boundary is composed from the later pinned round-trip
# receipt below; rewriting v1 would invalidate those historical build inputs.
assert apf["digital_font"]["safe_write_class"] == \
    "metadata_only_dxt5a_codec_and_import_missing"
assert apf["season_gamecast_scorebug"]["use_class"] == \
    "season_gamecast_menu_not_field_scorebug"
assert apf["replay_halftime_presentation"]["sfx_overlay"]["audo_count"] == 17
assert audit["scope"]["runtime_capture_performed"] is False

font_roundtrip_path = Path(
    "reports/assets/apf_digital_font_patch_roundtrip.json")
font_roundtrip = json.loads(font_roundtrip_path.read_text())
assert hashlib.sha256(font_roundtrip_path.read_bytes()).hexdigest() == \
    "c1ccb433832fe4c3465c2f9632e3a31887133cc5f8cf811cdff71ec9b36cd06e"
assert font_roundtrip["schema"] == "apf_digital_font_patch_roundtrip/v1"
font_conclusion = font_roundtrip["conclusion"]
assert font_conclusion["copy_only_global_digital_font_cli_exposed"] is True
assert font_conclusion["dxt5a_encode_decode_proved"] is True
assert font_conclusion["xenos_tile_endian_roundtrip_proved"] is True
assert font_conclusion["full_shared_vram_h7a_rebuild_proved"] is True
assert font_conclusion["all_750_unrelated_inner_parts_preserved"] is True
assert font_conclusion["xenia_runtime_visibility_proved"] is False

workflow = json.loads(Path(
    "build/nfl2k5-scorebug-workflow-20260712/workflow.json").read_text())
assert workflow["schema"] == "nfl2k5_scorebug_xiso_workflow/v1"
assert workflow["output"]["xiso_sha256"] == \
    "852901f79ae3368b1e0663106dffdfd5c3576c1ebd6579022c58277ed2a60a83"
assert workflow["patch"]["actual_changed_byte_count"] == 2169
assert workflow["patch"]["all_other_xiso_bytes_identical"] is True
assert workflow["claims"]["runtime_visibility_proved"] is False

doc = Path("docs/research/scorebug_presentation_modding.md").read_text()
for heading in ("## Worked", "## Failed or unproved", "## Blocking"):
    assert heading in doc
for phrase in ("not nine separate image files", "2,169", "dxt5a",
               "gamecast is not the field scorebug",
               "separate isolated xemu 0.8.135 runs visibly prove",
               "does not prove the shared atlas is unused"):
    assert phrase in " ".join(doc.lower().split())
assert "PORTME(NFL SCNE 346:78)" in doc
assert "PORTME(APF SCNE 1310:106/131/156/235/250/262/360)" in doc
assert "PORTME(APF TXTR 1310:246)" not in doc
PY

after_nfl_xbe="$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/default.xbe' | cut -d' ' -f1)"
after_nfl_index="$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' | cut -d' ' -f1)"
after_nfl_xiso="$(sha256sum 'ESPN NFL 2K5 (USA).xiso.iso' | cut -d' ' -f1)"
after_apf_xex="$(sha256sum 'extracted/All-Pro Football 2K8 (USA)/default.xex' | cut -d' ' -f1)"
after_apf_index="$(sha256sum 'extracted/All-Pro Football 2K8 (USA)/0A' | cut -d' ' -f1)"

test "$before_nfl_xbe" = "$after_nfl_xbe"
test "$before_nfl_index" = "$after_nfl_index"
test "$before_nfl_xiso" = "$after_nfl_xiso"
test "$before_apf_xex" = "$after_apf_xex"
test "$before_apf_index" = "$after_apf_index"

echo "SCOREBUG_PRESENTATION_PIPELINE_VALIDATION_PASS nfl_bindings=11 nfl_png_targets=3 nfl_xiso_changed=2169 apf_field_scenes=7 apf_audo=17 forged_refused=true symlink_refused=true high_entropy_refused=true audit_runtime=false score_buga_runtime=proved shield_runtime=proved digital_font_route=not_visible originals_unchanged=yes"
