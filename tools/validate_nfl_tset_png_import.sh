#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
input=reports/assets/nfl2k5_lions_diagnostic_codex_mod.png
span=reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.tset.bin
manifest=reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.json
previews=reports/assets/nfl2k5_lions_09H0_diagnostic_png_import_previews
fresh=$(mktemp -d /tmp/nfl-tset-png-import-validate.XXXXXX)
trap 'rm -rf -- "$fresh"' EXIT
fresh_input="$fresh/nfl2k5_lions_diagnostic_codex_mod.png"
fresh_span="$fresh/nfl2k5_lions_09H0_diagnostic_png_import.tset.bin"
fresh_manifest="$fresh/nfl2k5_lions_09H0_diagnostic_png_import.json"
fresh_previews="$fresh/nfl2k5_lions_09H0_diagnostic_png_import_previews"

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
  tools/nfl_tset_diagnostic_png.py \
  tools/nfl_tset_png_import.py \
  tools/nfl_tset_png_import_verify.py \
  tools/test_nfl_tset_png_import.py

PYTHONPATH=tools python3 tools/test_nfl_tset_png_import.py

PYTHONPATH=tools python3 tools/nfl_tset_diagnostic_png.py \
  --output "$fresh_input"
cmp "$fresh_input" "$input"

PYTHONPATH=tools python3 tools/nfl_tset_png_import.py \
  --index "$index" \
  --inventory reports/assets/nfl2k5_resource_chunks_v2.json \
  --clean-png "$fresh_input" \
  --mud-mode darken_60 \
  --output-span "$fresh_span" \
  --manifest "$fresh_manifest" \
  --preview-dir "$fresh_previews"

cmp "$fresh_span" "$span"
cmp "$fresh_manifest" "$manifest"
[[ $(find "$fresh_previews" -maxdepth 1 -type f | wc -l) -eq 12 ]]
for canonical in "$previews"/*.png
do
  name=$(basename "$canonical")
  cmp "$fresh_previews/$name" "$canonical"
done

printf '%s  %s\n' \
  6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8 \
  "$input" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8 \
  "$span" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  3500f6e6a3fddc4680a43214dd8f283bb8d1a13b355dcb2e8bbb349417613d80 \
  "$manifest" | sha256sum -c - >/dev/null

PYTHONPATH=tools python3 tools/nfl_tset_png_import_verify.py \
  --index "$index" \
  --input-png "$fresh_input" \
  --span "$fresh_span" \
  --manifest "$fresh_manifest" \
  --preview-dir "$fresh_previews"

# O_EXCL rerun must fail before doing work and must leave every artifact exact.
before_span=$(sha256sum "$fresh_span" | awk '{print $1}')
before_manifest=$(sha256sum "$fresh_manifest" | awk '{print $1}')
set +e
PYTHONPATH=tools python3 tools/nfl_tset_png_import.py \
  --index "$index" \
  --inventory reports/assets/nfl2k5_resource_chunks_v2.json \
  --clean-png "$fresh_input" \
  --mud-mode darken_60 \
  --output-span "$fresh_span" \
  --manifest "$fresh_manifest" \
  --preview-dir "$fresh_previews" >"$fresh/o_excl.stdout" 2>"$fresh/o_excl.stderr"
status=$?
set -e
[[ $status -ne 0 ]] || { echo "O_EXCL rerun unexpectedly succeeded" >&2; exit 1; }
rg -q 'already exists' "$fresh/o_excl.stderr"
[[ $(sha256sum "$fresh_span" | awk '{print $1}') == "$before_span" ]]
[[ $(sha256sum "$fresh_manifest" | awk '{print $1}') == "$before_manifest" ]]

if find "$fresh" -type f \( -iname '*.iso' -o -iname '*.xiso' \) | grep -q .
then
  echo "PNG importer validator unexpectedly created a disc image" >&2
  exit 1
fi

printf '%s  %s\n' \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 \
  'ESPN NFL 2K5 (USA).xiso.iso' | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' | sha256sum -c - >/dev/null

echo "NFL_TSET_PNG_IMPORT_VALIDATION_PASS input_sha=6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8 span_sha=76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8 target=09H0 chunk=1 rgba=512x256 colors=32 quantization_error=0 mips=6 index_bytes=174720 palettes=2 shared_indices=true mud=darken_60 decoded=177024 encoded=22285 stored=74688 zero_pad=52403 previews=12 descriptors=preserved deterministic=true bounded=true o_excl=yes originals_unchanged=true xiso_created=false title_executed=false runtime_visibility=false"
