#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

source_xiso='ESPN NFL 2K5 (USA).xiso.iso'
compatibility=reports/assets/nfl2k5_sleeve_tset_compatibility.json
compatibility_tsv=reports/assets/nfl2k5_sleeve_tset_compatibility.tsv
artifact=/media/noah/Storage/.codex-tmp/nfl2k5-sleeve-workflow-20260711
output_xiso="$artifact/ESPN-NFL-2K5-06H2-custom-sleeve.xiso.iso"
manifest="$artifact/workflow.json"
clean_png="$artifact/noncanonical_user_sleeve.png"
previews="$artifact/previews"
temporary=$(mktemp -d /tmp/nfl-sleeve-compatibility-validate.XXXXXX)
cleanup() {
  rm -f -- "$temporary/fresh.json" "$temporary/fresh.tsv" \
    "$temporary/o_excl.stdout" "$temporary/o_excl.stderr"
  rmdir -- "$temporary" 2>/dev/null || true
}
trap cleanup EXIT

for required in "$source_xiso" "$compatibility" "$compatibility_tsv" \
                "$output_xiso" "$manifest" "$clean_png"; do
  [[ -f "$required" && ! -L "$required" ]] || {
    echo "missing/non-regular sleeve artifact: $required" >&2
    exit 1
  }
done
[[ -d "$previews" && ! -L "$previews" ]] || {
  echo "missing sleeve preview directory: $previews" >&2
  exit 1
}

printf '%s  %s\n' \
  72a25d908135322a6c15c1f19f2f575224ab224c8b8c4c6969f5b4ba2359ae2b \
  "$compatibility" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  df1a26c99d8dcad097bc5ea6a35933ee8d616984f03e5fc9fa497af45faaa924 \
  "$compatibility_tsv" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  d38ff03c1995ef497cec483f370deca102fb04076570463f099c52c7d8a14c4b \
  "$clean_png" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  32cca13bce556268ebca4f7abbcf4b1e9759dbbaa520d2aef36e060c44f2065c \
  "$manifest" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  a955674cecdfea0b70c50141c21ef941b71d565d7889bc192c68fdbb967be14d \
  "$output_xiso" | sha256sum -c - >/dev/null

python3 -m py_compile \
  tools/nfl_sleeve_tset_compatibility.py \
  tools/nfl_sleeve_tset_targets.py \
  tools/nfl_sleeve_tset_png_import.py \
  tools/nfl_sleeve_tset_dynamic_validate.py \
  tools/nfl_sleeve_tset_xiso_patch.py \
  tools/nfl2k5_uniform_sleeve_png_workflow.py \
  tools/nfl2k5_uniform_sleeve_png_workflow_verify.py \
  tools/test_nfl_sleeve_tset_compatibility.py

PYTHONPATH=tools python3 tools/nfl_sleeve_tset_compatibility.py \
  --index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --inventory reports/assets/nfl2k5_resource_chunks_v2.json \
  --uniform-inventory reports/assets/nfl2k5_uniform_inventory.json \
  --source-xiso "$source_xiso" \
  --output-json "$temporary/fresh.json" \
  --output-tsv "$temporary/fresh.tsv"
cmp -- "$temporary/fresh.json" "$compatibility"
cmp -- "$temporary/fresh.tsv" "$compatibility_tsv"

PYTHONPATH=tools python3 tools/test_nfl_sleeve_tset_compatibility.py

PYTHONPATH=tools python3 tools/nfl2k5_uniform_sleeve_png_workflow_verify.py \
  --source-xiso "$source_xiso" \
  --output-xiso "$output_xiso" \
  --manifest "$manifest" \
  --target-code 06 --target-side H --target-variant 2 \
  --clean-png "$clean_png" \
  --previews "$previews"

# Existing final outputs must stop a second workflow before generation.
before_output=$(sha256sum "$output_xiso" | awk '{print $1}')
before_manifest=$(sha256sum "$manifest" | awk '{print $1}')
set +e
PYTHONPATH=tools python3 tools/nfl2k5_uniform_sleeve_png_workflow.py \
  --source-xiso "$source_xiso" \
  --target-code 06 --target-side H --target-variant 2 \
  --clean-png "$clean_png" --mud-mode darken_60 \
  --output-xiso "$output_xiso" \
  --manifest "$manifest" \
  --preview-dir "$previews" \
  >"$temporary/o_excl.stdout" 2>"$temporary/o_excl.stderr"
status=$?
set -e
[[ $status -ne 0 ]] || {
  echo "sleeve O_EXCL workflow rerun unexpectedly succeeded" >&2
  exit 1
}
rg -q 'already exists' "$temporary/o_excl.stderr"
[[ $(sha256sum "$output_xiso" | awk '{print $1}') == "$before_output" ]]
[[ $(sha256sum "$manifest" | awk '{print $1}') == "$before_manifest" ]]

printf '%s  %s\n' \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 \
  "$source_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d \
  'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' | sha256sum -c - >/dev/null

echo "NFL_SLEEVE_TSET_COMPATIBILITY_VALIDATION_PASS packages=634 pairs=317 home=317 away=317 layouts=1 allocations=275 compatible=634 incompatible=0 packs=9,A,B,C offsets=466 stored_classes=193 stored=5648..20496 target=06H2 output_sha=a955674cecdfea0b70c50141c21ef941b71d565d7889bc192c68fdbb967be14d span_sha=70b5abb8a8d6ea309ae86546c7d3b12ecdc0fff8a70df98645b429581130f981 changed_bytes=5229 runs=233 encoded=1837/5648 zero_pad=3811 mips=5 previews=10 fixture_all_634=true source=unchanged xbe=unchanged pack0=unchanged overflow_fitted=true forged_rejected=true symlink_refused=true o_excl=true v3_loader_alias_guard=true runtime_visibility=false xemu_started=false title_executed=false"
