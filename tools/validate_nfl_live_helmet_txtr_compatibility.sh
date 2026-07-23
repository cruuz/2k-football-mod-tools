#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TMP="$ROOT/.codex-tmp/nfl-live-helmet-validator-$$"
mkdir -p "$TMP"
cleanup() {
  rm -rf "$TMP"
}
trap cleanup EXIT

export PYTHONPATH="$ROOT/tools${PYTHONPATH:+:$PYTHONPATH}"

python3 tools/nfl_live_helmet_txtr_compatibility.py \
  --output-json "$TMP/compatibility.json" \
  --output-tsv "$TMP/compatibility.tsv"
cmp reports/assets/nfl2k5_live_helmet_txtr_compatibility.json \
  "$TMP/compatibility.json"
cmp reports/assets/nfl2k5_live_helmet_txtr_compatibility.tsv \
  "$TMP/compatibility.tsv"

python3 tools/nfl_live_helmet_txtr_fixture.py \
  --output "$TMP/live_helmet_fixture.png"
cmp assets/fixtures/nfl2k5/live_helmet/live_helmet_fixture.png \
  "$TMP/live_helmet_fixture.png"

for family in helmet00 helmet02; do
  python3 tools/nfl_live_helmet_txtr_png_import.py \
    --target-code 09 --target-side A --target-variant 0 \
    --family "$family" \
    --png assets/fixtures/nfl2k5/live_helmet/live_helmet_fixture.png \
    --output-dir "$TMP/import-$family"
  python3 tools/nfl_live_helmet_txtr_import_verify.py \
    --target-code 09 --target-side A --target-variant 0 \
    --family "$family" \
    --png assets/fixtures/nfl2k5/live_helmet/live_helmet_fixture.png \
    --output-dir "$TMP/import-$family"
done

if python3 tools/nfl_live_helmet_txtr_png_import.py \
    --target-code 99 --target-side A --target-variant 99 \
    --family helmet00 \
    --png assets/fixtures/nfl2k5/live_helmet/live_helmet_fixture.png \
    --output-dir "$TMP/must-not-exist-missing-selector" \
    >"$TMP/missing-selector.stdout" 2>"$TMP/missing-selector.stderr"; then
  echo "missing selector unexpectedly succeeded" >&2
  exit 1
fi
test ! -e "$TMP/must-not-exist-missing-selector"

if python3 tools/nfl_live_helmet_txtr_png_import.py \
    --target-code 09 --target-side A --target-variant 0 \
    --family helmet00 \
    --png "$TMP/import-helmet00/previews/mip1_128x128.png" \
    --output-dir "$TMP/must-not-exist-wrong-size" \
    >"$TMP/wrong-size.stdout" 2>"$TMP/wrong-size.stderr"; then
  echo "wrong-size PNG unexpectedly succeeded" >&2
  exit 1
fi
test ! -e "$TMP/must-not-exist-wrong-size"

PROOF="$ROOT/.codex-tmp/nfl-live-helmet-xiso-proof-20260712"
python3 tools/nfl_live_helmet_txtr_xiso_verify.py \
  --source-xiso "$ROOT/ESPN NFL 2K5 (USA).xiso.iso" \
  --output-xiso "$PROOF/ESPN-NFL-2K5-Detroit-AWAY-live-helmet-both-families-CODEX-MOD.xiso.iso" \
  --manifest "$PROOF/workflow_manifest.json" \
  --preview-dir "$PROOF/previews" \
  --plan assets/fixtures/nfl2k5/live_helmet/detroit_away_both_families_plan.json

test "$(sha256sum 'ESPN NFL 2K5 (USA).xiso.iso' | cut -d' ' -f1)" = \
  "7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9"
test "$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/default.xbe' | cut -d' ' -f1)" = \
  "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
test "$(sha256sum 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' | cut -d' ' -f1)" = \
  "34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d"

echo "NFL_LIVE_HELMET_TXTR_COMPATIBILITY_VALIDATION_PASS resources=1268 layouts=1 allocations=367 fixture=true imports=2 xiso_edits=2 output_sha=682c689de24efdcff6c33deeef665dc81d4aba2186c098779aea737355a5030b originals_unchanged=true runtime_visibility=false xemu_started=false title_executed=false"
