#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
source_xiso='ESPN NFL 2K5 (USA).xiso.iso'
compatibility=reports/assets/nfl2k5_jersey_tset_compatibility.json
compatibility_tsv=reports/assets/nfl2k5_jersey_tset_compatibility.tsv
artifact=/media/noah/Storage/.codex-tmp/nfl2k5-compatible-jersey-27A0-20260711
output_xiso="$artifact/ESPN-NFL-2K5-27A0-custom-jersey.xiso.iso"
manifest="$artifact/workflow_manifest.json"
clean_png=/media/noah/Storage/.codex-tmp/nfl2k5-dynamic-jersey-workflow-20260711/noncanonical_user_jersey.png
previews="$artifact/previews"
temporary=$(mktemp -d /tmp/nfl-jersey-compatibility-validate.XXXXXX)
cleanup() {
  rm -f -- "$temporary/fresh.json" "$temporary/fresh.tsv" \
    "$temporary/o_excl.stdout" "$temporary/o_excl.stderr"
  rmdir -- "$temporary" 2>/dev/null || true
}
trap cleanup EXIT

for required in "$source_xiso" "$compatibility" "$compatibility_tsv" \
                "$output_xiso" "$manifest" "$clean_png"; do
  [[ -f "$required" && ! -L "$required" ]] || {
    echo "missing/non-regular compatibility artifact: $required" >&2
    exit 1
  }
done
[[ -d "$previews" && ! -L "$previews" ]] || {
  echo "missing generalized preview directory: $previews" >&2
  exit 1
}

printf '%s  %s\n' \
  046d03546242c11478d39b48d7f6f80b5f2009c85641b5c81abdaa6f8171cacd \
  "$compatibility" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  5f074fe299a2d23c10cca2b61a2ff9695684eeba0c134b32f9e82863051bbbb0 \
  "$compatibility_tsv" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  63b4fecbf9856d53673ff07fc81d38ad39104d5e440835a1a6bda4b5aaac5670 \
  "$output_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  f303dc5df1524c2c31e6484972dfeb47998bf5e8cce9200e46ec62a647b9fbbe \
  "$manifest" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  63b42c14dea5b222e5524531e964baf18cb11edbaf654d87075b11ed19680d50 \
  "$clean_png" | sha256sum -c - >/dev/null

python3 -m py_compile \
  tools/nfl_jersey_tset_compatibility.py \
  tools/nfl_jersey_tset_targets.py \
  tools/nfl_jersey_tset_png_import.py \
  tools/nfl_jersey_tset_dynamic_validate.py \
  tools/nfl_jersey_tset_xiso_patch.py \
  tools/nfl2k5_uniform_jersey_png_workflow.py \
  tools/nfl2k5_uniform_jersey_png_workflow_verify.py \
  tools/test_nfl_jersey_tset_compatibility.py

PYTHONPATH=tools python3 tools/nfl_jersey_tset_compatibility.py \
  --index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --inventory reports/assets/nfl2k5_resource_chunks_v2.json \
  --uniform-inventory reports/assets/nfl2k5_uniform_inventory.json \
  --source-xiso "$source_xiso" \
  --output-json "$temporary/fresh.json" \
  --output-tsv "$temporary/fresh.tsv"
cmp -- "$temporary/fresh.json" "$compatibility"
cmp -- "$temporary/fresh.tsv" "$compatibility_tsv"

PYTHONPATH=tools python3 tools/test_nfl_jersey_tset_compatibility.py

PYTHONPATH=tools python3 tools/nfl2k5_uniform_jersey_png_workflow_verify.py \
  --source-xiso "$source_xiso" \
  --output-xiso "$output_xiso" \
  --manifest "$manifest" \
  --target-code 27 --target-side A --target-variant 0 \
  --clean-png "$clean_png" \
  --previews "$previews"

# Existing final outputs must stop a second workflow before generation.
before_output=$(sha256sum "$output_xiso" | awk '{print $1}')
before_manifest=$(sha256sum "$manifest" | awk '{print $1}')
set +e
PYTHONPATH=tools python3 tools/nfl2k5_uniform_jersey_png_workflow.py \
  --source-xiso "$source_xiso" \
  --target-code 27 --target-side A --target-variant 0 \
  --clean-png "$clean_png" --mud-mode darken_60 \
  --output-xiso "$output_xiso" \
  --manifest "$manifest" \
  --preview-dir "$previews" \
  >"$temporary/o_excl.stdout" 2>"$temporary/o_excl.stderr"
status=$?
set -e
[[ $status -ne 0 ]] || {
  echo "generalized O_EXCL workflow rerun unexpectedly succeeded" >&2
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

echo "NFL_JERSEY_TSET_COMPATIBILITY_VALIDATION_PASS packages=634 pairs=317 home=317 away=317 layouts=1 allocations=346 compatible=634 incompatible=0 packs=9,A,B,C stored=31872..126704 boundaries=3 selectors=pinned fixtures=00H0,27A0 smallest=30H2 output_target=27A0 output_sha=63b4fecbf9856d53673ff07fc81d38ad39104d5e440835a1a6bda4b5aaac5670 span_sha=30c01b752b581e25367d156752e7808c8bfffffe22d1efaa16297e02beeb1f41 changed_bytes=73127 runs=3473 encoded=22381/77392 zero_pad=55011 mips=6 previews=12 layout=identical source=unchanged xbe=unchanged pack0=unchanged oversize_refused=true forged_rejected=true symlink_refused=true path_swap_refused=true o_excl=true legacy_v2_readonly=true v3_loader_alias_guard=true runtime_visibility=false xemu_started=false title_executed=false"
