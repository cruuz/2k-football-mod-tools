#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
canonical_span=reports/assets/nfl2k5_lions_09H0_tset1_identity_zero_pad.bin
canonical_report=reports/assets/nfl2k5_vc_lz_fixed_span_rebuild.json
fresh=$(mktemp -d /tmp/nfl-vc-lz-compressor-validate.XXXXXX)
trap 'rm -rf -- "$fresh"' EXIT
fresh_span="$fresh/nfl2k5_lions_09H0_tset1_identity_zero_pad.bin"
fresh_report="$fresh/report.json"

printf '%s  %s\n' \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 \
  'ESPN NFL 2K5 (USA).xiso.iso' | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d \
  "$index" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b \
  'extracted/ESPN NFL 2K5 (USA)/vc_53450030/A' | sha256sum -c - >/dev/null

python3 -m py_compile \
  tools/nfl_txtr.py \
  tools/test_nfl_vc_lz_compress.py \
  tools/nfl_tset_fixed_span_rebuild.py \
  tools/nfl_tset_fixed_span_verify.py

PYTHONPATH=tools python3 tools/test_nfl_vc_lz_compress.py

PYTHONPATH=tools python3 tools/nfl_tset_fixed_span_rebuild.py \
  --index "$index" \
  --inventory reports/assets/nfl2k5_resource_chunks_v2.json \
  --output-span "$fresh_span" \
  --output-report "$fresh_report"

cmp "$fresh_span" "$canonical_span"
cmp "$fresh_report" "$canonical_report"
printf '%s  %s\n' \
  a802389334ad0e895557a9047f24381eb0f3ed9eefc77a7572a87ac64f56c9a9 \
  "$canonical_span" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  a70fe44b9bc02c998c0b8d71ca25144b066ebcab7223a964d00e8bdff3b3aa2d \
  "$canonical_report" | sha256sum -c - >/dev/null

PYTHONPATH=tools python3 tools/nfl_tset_fixed_span_verify.py \
  --index "$index" \
  --rebuilt-span "$fresh_span" \
  --report "$fresh_report"

python3 - <<'PY'
import json
from pathlib import Path

report = json.loads(
    Path("reports/assets/nfl2k5_vc_lz_fixed_span_rebuild.json").read_text()
)
assert report["schema"] == "nfl2k5_tset_fixed_span_rebuild/v1"
assert report["compression"]["encoded_bytes"] == 74674
assert report["compression"]["verified_roundtrip"] is True
assert report["identity_rebuild"]["compressed_stream_matches_template"] is True
assert report["identity_rebuild"]["zero_padding_bytes"] == 14
assert report["one_byte_palette_probe"]["recompressed_bytes"] == 74675
assert report["one_byte_palette_probe"]["zero_padding_bytes"] == 13
assert report["one_byte_palette_probe"]["fits_original_stored_body"] is True
assert report["claims"]["general_png_importer"] is False
assert report["claims"]["xiso_created"] is False
assert report["claims"]["title_executed"] is False
PY

echo "NFL_VC_LZ_COMPRESSOR_VALIDATION_PASS retail_exact_streams=8 retail_decoded_bytes=743040 synthetic=5 target=09H0 chunk=1 decoded=177024 encoded=74674 stored=74688 zero_pad=14 exact_stream=true identity_span_sha=a802389334ad0e895557a9047f24381eb0f3ed9eefc77a7572a87ac64f56c9a9 palette_probe=74675/74688 deterministic=true bounded=true independent_decode=true originals_unchanged=true png_importer=false xiso_created=false title_executed=false"
