#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

source_xiso='ESPN NFL 2K5 (USA).xiso.iso'
index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
compatibility=reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json
compatibility_tsv=reports/assets/nfl2k5_live_numbers_nameplate_compatibility.tsv
fixtures=reports/assets/nfl2k5_live_numbers_nameplate_fixtures
plan=reports/assets/nfl2k5_live_numbers_nameplate_fixture_plan.json
proof=.codex-tmp/nfl-live-art-xiso-proof
output_xiso="$proof/ESPN-NFL-2K5-Detroit-live-numbers-nameplate-nonretail.xiso.iso"
workflow="$proof/workflow_manifest.json"
previews="$proof/previews"
temporary=$(mktemp -d "$root/.codex-tmp/nfl-live-art-validate.XXXXXX")
cleanup() {
  rm -rf -- "$temporary"
}
trap cleanup EXIT

required_files=(
  "$source_xiso" "$index" "$compatibility" "$compatibility_tsv" "$plan"
  "$fixtures/detroit_away_style0_digit5_32_nonretail.png"
  "$fixtures/detroit_away_style0_digit5_64_nonretail.png"
  "$fixtures/detroit_away_style0_nameplate_nonretail.png"
  "$fixtures/fixture_manifest.json"
  reports/assets/nfl2k5_live_numbers_nameplate_xiso_workflow.json
  reports/assets/nfl2k5_live_numbers_nameplate_xiso_verify.json
  reports/assets/nfl2k5_live_numbers_nameplate_ghidra/nfl_live_numbers_nameplate_trace.txt
  reports/assets/nfl2k5_live_numbers_nameplate_ghidra/nfl_live_numbers_nameplate_pseudo_c.c
  "$output_xiso" "$workflow"
)
for required in "${required_files[@]}"; do
  [[ -f "$required" && ! -L "$required" ]] || {
    echo "missing/non-regular live-art artifact: $required" >&2
    exit 1
  }
done
[[ -d "$previews" && ! -L "$previews" ]] || {
  echo "missing/non-regular live-art preview directory" >&2
  exit 1
}

printf '%s  %s\n' bf2cd1550d5157ad254eb488b4f58cd1f10efda56e98787f8117aec6902bcea2 "$compatibility" | sha256sum -c - >/dev/null
printf '%s  %s\n' 2c5c67eae6cb907f25d85bf96303707175621092311146cee27c00e8a9af6d74 "$compatibility_tsv" | sha256sum -c - >/dev/null
printf '%s  %s\n' 86061df661918711ef59a7d27a65a92b335b568dfd1b023b61cc99cb8aaaff6e "$plan" | sha256sum -c - >/dev/null
printf '%s  %s\n' c6ef65b753d1df2accb49c37eab6a1cb375e48bfe79f11c4b8743bfc73b4279f reports/assets/nfl2k5_live_numbers_nameplate_xiso_workflow.json | sha256sum -c - >/dev/null
printf '%s  %s\n' 8fdef46069bd44bf2e03258564bb8b694fab4a202f7382c39b11f3b7734f2fba reports/assets/nfl2k5_live_numbers_nameplate_xiso_verify.json | sha256sum -c - >/dev/null
printf '%s  %s\n' 905a395131a86d6a8c7ef36fb6b9b463e80b37e0816d88eb17527fb9229cc6a2 "$output_xiso" | sha256sum -c - >/dev/null

python3 -m py_compile \
  tools/nfl_live_numbers_nameplate_compatibility.py \
  tools/nfl_live_numbers_nameplate_targets.py \
  tools/nfl_live_numbers_nameplate_png_import.py \
  tools/nfl_live_numbers_nameplate_fixture.py \
  tools/nfl_live_numbers_nameplate_xiso_workflow.py \
  tools/nfl_live_numbers_nameplate_xiso_verify.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_fixture.py \
    --output-dir "$temporary/fixtures"
for name in \
  detroit_away_style0_digit5_32_nonretail.png \
  detroit_away_style0_digit5_64_nonretail.png \
  detroit_away_style0_nameplate_nonretail.png \
  fixture_manifest.json; do
  cmp -- "$temporary/fixtures/$name" "$fixtures/$name"
done

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_compatibility.py \
    --output "$temporary/compatibility.json" \
    --tsv "$temporary/compatibility.tsv"
cmp -- "$temporary/compatibility.json" "$compatibility"
cmp -- "$temporary/compatibility.tsv" "$compatibility_tsv"

mkdir "$temporary/jersey" "$temporary/nameplate"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_png_import.py \
    --family jersey --asset-code 09 --side A --variant 0 --digit 5 \
    --png "$fixtures/detroit_away_style0_digit5_64_nonretail.png" \
    --output-span "$temporary/jersey/replacement.bin" \
    --output-manifest "$temporary/jersey/import.json" \
    --output-preview "$temporary/jersey/preview.png"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_png_import.py \
    --family nameplate --asset-code 09 --side A --variant 0 \
    --png "$fixtures/detroit_away_style0_nameplate_nonretail.png" \
    --output-span "$temporary/nameplate/replacement.bin" \
    --output-manifest "$temporary/nameplate/import.json" \
    --output-preview "$temporary/nameplate/preview.png"

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_xiso_verify.py \
    --source-xiso "$source_xiso" \
    --output-xiso "$output_xiso" \
    --manifest "$workflow" \
    --preview-dir "$previews" \
    --plan "$plan" \
    --index "$index" \
    --compatibility "$compatibility" \
    --output-report "$temporary/verification.json"
cmp -- "$temporary/verification.json" reports/assets/nfl2k5_live_numbers_nameplate_xiso_verify.json

# A 32x32 helmet fixture must not be accepted by the 64x64 jersey target.
set +e
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_png_import.py \
    --family jersey --asset-code 09 --side A --variant 0 --digit 5 \
    --png "$fixtures/detroit_away_style0_digit5_32_nonretail.png" \
    --output-span "$temporary/wrong-size.bin" \
    --output-manifest "$temporary/wrong-size.json" \
    --output-preview "$temporary/wrong-size.png" \
    >"$temporary/wrong-size.stdout" 2>"$temporary/wrong-size.stderr"
wrong_size_status=$?
set -e
[[ $wrong_size_status -ne 0 ]]
rg -q 'PNG must be exactly 64x64' "$temporary/wrong-size.stderr"
[[ ! -e "$temporary/wrong-size.bin" && ! -e "$temporary/wrong-size.json" && ! -e "$temporary/wrong-size.png" ]]

# Deterministic high-entropy art must not escape the smallest fixed allocation.
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools python3 - "$temporary/overflow.png" <<'PY'
from pathlib import Path
import sys
from nfl_txtr import encode_rgba_png

state = 0x2A5EED01
rgba = bytearray()
for _ in range(32 * 32 * 4):
    state = (1664525 * state + 1013904223) & 0xFFFFFFFF
    rgba.append((state >> 24) & 0xFF)
Path(sys.argv[1]).write_bytes(encode_rgba_png(32, 32, bytes(rgba)))
PY
set +e
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_png_import.py \
    --family helmet --asset-code 00 --side H --variant 0 --digit 1 \
    --png "$temporary/overflow.png" \
    --output-span "$temporary/overflow.bin" \
    --output-manifest "$temporary/overflow.json" \
    --output-preview "$temporary/overflow-preview.png" \
    >"$temporary/overflow.stdout" 2>"$temporary/overflow.stderr"
overflow_status=$?
set -e
[[ $overflow_status -ne 0 ]]
rg -q 'exceeds 384|more than the 384-byte bound' "$temporary/overflow.stderr"
[[ ! -e "$temporary/overflow.bin" && ! -e "$temporary/overflow.json" && ! -e "$temporary/overflow-preview.png" ]]

# Compatibility metadata is hash-pinned; even harmless appended whitespace is refused.
cp "$compatibility" "$temporary/forged.json"
printf ' ' >>"$temporary/forged.json"
set +e
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_png_import.py \
    --compatibility "$temporary/forged.json" \
    --family jersey --asset-code 09 --side A --variant 0 --digit 5 \
    --png "$fixtures/detroit_away_style0_digit5_64_nonretail.png" \
    --output-span "$temporary/forged.bin" \
    --output-manifest "$temporary/forged-manifest.json" \
    --output-preview "$temporary/forged.png" \
    >"$temporary/forged.stdout" 2>"$temporary/forged.stderr"
forged_status=$?
set -e
[[ $forged_status -ne 0 ]]
rg -q 'compatibility report SHA-256 mismatch' "$temporary/forged.stderr"
[[ ! -e "$temporary/forged.bin" && ! -e "$temporary/forged-manifest.json" && ! -e "$temporary/forged.png" ]]

# Existing final outputs stop the workflow before any copied-disc mutation.
before_xiso=$(stat -c '%d:%i:%s:%Y:%Z' "$output_xiso")
before_workflow=$(sha256sum "$workflow" | awk '{print $1}')
set +e
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=tools \
  python3 tools/nfl_live_numbers_nameplate_xiso_workflow.py \
    --source-xiso "$source_xiso" \
    --output-xiso "$output_xiso" \
    --manifest "$workflow" \
    --preview-dir "$previews" \
    --plan "$plan" \
    --index "$index" \
    --compatibility "$compatibility" \
    >"$temporary/o-excl.stdout" 2>"$temporary/o-excl.stderr"
o_excl_status=$?
set -e
[[ $o_excl_status -ne 0 ]]
rg -q 'outputs exist' "$temporary/o-excl.stderr"
[[ $(stat -c '%d:%i:%s:%Y:%Z' "$output_xiso") == "$before_xiso" ]]
[[ $(sha256sum "$workflow" | awk '{print $1}') == "$before_workflow" ]]

if [[ ${NFL_LIVE_ART_FULL_GHIDRA:-0} == 1 ]]; then
  mkdir "$temporary/ghidra"
  env XDG_CONFIG_HOME="$temporary/ghidra-config" \
    JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64 \
    tools/vendor/ghidra_12.1.2_PUBLIC/support/analyzeHeadless \
      ghidra_projects nfl2k5 \
      -process default.xbe -noanalysis -readOnly \
      -scriptPath tools/ghidra_scripts \
      -postScript NflLiveNumbersNameplateTrace.java "$temporary/ghidra"
  cmp -- "$temporary/ghidra/nfl_live_numbers_nameplate_trace.txt" \
    reports/assets/nfl2k5_live_numbers_nameplate_ghidra/nfl_live_numbers_nameplate_trace.txt
  cmp -- "$temporary/ghidra/nfl_live_numbers_nameplate_pseudo_c.c" \
    reports/assets/nfl2k5_live_numbers_nameplate_ghidra/nfl_live_numbers_nameplate_pseudo_c.c
fi

rg -q '19,654' docs/research/nfl_live_numbers_nameplate_pipeline.md README.md docs/phases/phase3.md docs/phases/phase4.md
rg -q 'runtime visibility.*not claimed|visibility of the new fixtures is not claimed' docs/research/nfl_live_numbers_nameplate_pipeline.md README.md

printf '%s  %s\n' 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 "$source_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' 73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 'extracted/ESPN NFL 2K5 (USA)/default.xbe' | sha256sum -c - >/dev/null
printf '%s  %s\n' 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d "$index" | sha256sum -c - >/dev/null

echo "NFL_LIVE_NUMBERS_NAMEPLATE_PIPELINE_VALIDATION_PASS packages=634 pairs=317 home=317 away=317 digits=19020 atlases=634 metrics_objects=634 metric_records=18386 art_resources=19654 layouts=4 compatible=19654 incompatible=0 families=jersey,helmet,arm,nameplate source_xiso=unchanged xbe=unchanged pack0=unchanged proof_edits=4 proof_changed_bytes=12084 output_sha=905a395131a86d6a8c7ef36fb6b9b463e80b37e0816d88eb17527fb9229cc6a2 xdvdfs_identical=true all_mips=true vc_lz_alias_guard=true metrics_writer=false forged_refused=true wrong_size_refused=true overflow_refused=true o_excl=true runtime_visibility=false xemu_started=false title_executed=false"
