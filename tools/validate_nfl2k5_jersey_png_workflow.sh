#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
artifact=/media/noah/Storage/.codex-tmp/nfl2k5-dynamic-jersey-workflow-20260711
source_xiso='ESPN NFL 2K5 (USA).xiso.iso'
output_xiso="$artifact/ESPN-NFL-2K5-Detroit-HOME-noncanonical-jersey.xiso.iso"
manifest="$artifact/workflow_manifest.json"
clean_png="$artifact/noncanonical_user_jersey.png"
previews="$artifact/previews"
temporary=$(mktemp -d /tmp/nfl2k5-jersey-workflow-validate.XXXXXX)
cleanup() {
  rm -f -- "$temporary/o_excl.stdout" "$temporary/o_excl.stderr"
  rmdir -- "$temporary" 2>/dev/null || true
}
trap cleanup EXIT

for required in "$source_xiso" "$output_xiso" "$manifest" "$clean_png"; do
  [[ -f "$required" && ! -L "$required" ]] || {
    echo "missing/non-regular frozen artifact: $required" >&2
    exit 1
  }
done
[[ -d "$previews" && ! -L "$previews" ]] || {
  echo "missing frozen preview directory: $previews" >&2
  exit 1
}

printf '%s  %s\n' \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 \
  "$source_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  c5acc40122480dfc49d653e90a4aebceab982e544ca521c2b40921a4e735e177 \
  "$output_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  1c71e702be3f6f0da609d5f6b42c78a894fd70a4ec3f47e6ae31c932576a5727 \
  "$manifest" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  63b42c14dea5b222e5524531e964baf18cb11edbaf654d87075b11ed19680d50 \
  "$clean_png" | sha256sum -c - >/dev/null

python3 -m py_compile \
  tools/nfl_tset_png_import_dynamic_validate.py \
  tools/nfl_tset_png_import_xiso_generic_patch.py \
  tools/nfl2k5_jersey_png_workflow.py \
  tools/nfl2k5_jersey_png_workflow_verify.py \
  tools/test_nfl_tset_png_import_dynamic_workflow.py
PYTHONPATH=tools python3 tools/test_nfl_tset_png_import_dynamic_workflow.py
PYTHONPATH=tools python3 tools/nfl2k5_jersey_png_workflow_verify.py \
  --source-xiso "$source_xiso" \
  --output-xiso "$output_xiso" \
  --manifest "$manifest" \
  --clean-png "$clean_png" \
  --previews "$previews"

# A rerun must stop before generation because all three final outputs already
# exist; the sentinels must remain byte-identical.
before_output=$(sha256sum "$output_xiso" | awk '{print $1}')
before_manifest=$(sha256sum "$manifest" | awk '{print $1}')
before_clean=$(sha256sum "$clean_png" | awk '{print $1}')
set +e
PYTHONPATH=tools python3 tools/nfl2k5_jersey_png_workflow.py \
  --source-xiso "$source_xiso" \
  --clean-png "$clean_png" \
  --mud-mode darken_60 \
  --output-xiso "$output_xiso" \
  --manifest "$manifest" \
  --preview-dir "$previews" \
  >"$temporary/o_excl.stdout" 2>"$temporary/o_excl.stderr"
status=$?
set -e
[[ $status -ne 0 ]] || {
  echo "O_EXCL workflow rerun unexpectedly succeeded" >&2
  exit 1
}
rg -q 'already exists' "$temporary/o_excl.stderr"
[[ $(sha256sum "$output_xiso" | awk '{print $1}') == "$before_output" ]]
[[ $(sha256sum "$manifest" | awk '{print $1}') == "$before_manifest" ]]
[[ $(sha256sum "$clean_png" | awk '{print $1}') == "$before_clean" ]]

printf '%s  %s\n' \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 \
  "$source_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d \
  'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' | sha256sum -c - >/dev/null

echo "NFL2K5_JERSEY_PNG_WORKFLOW_VALIDATION_PASS output_sha=c5acc40122480dfc49d653e90a4aebceab982e544ca521c2b40921a4e735e177 span_sha=cce20e17246b121a15b3429724c55177835404e930228c694410f4f832d0e621 target=09H0 chunk=1 changed_bytes=70303 runs=3196 files=19 layout=identical source=unchanged xbe=unchanged pack0=unchanged encoded=22381 stored=74688 zero_pad=52307 mips=6 previews=12 forged_rejected=true oversize_refused=true symlink_refused=true path_swap_refused=true o_excl=true strict_mud=true mud_conflict_refused=true temp_owned_cleanup=true runtime_visibility=false xemu_started=false title_executed=false"
