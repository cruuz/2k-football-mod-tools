#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"

source_xiso='ESPN NFL 2K5 (USA).xiso.iso'
compatibility=reports/assets/nfl2k5_pants_tset_compatibility.json
compatibility_tsv=reports/assets/nfl2k5_pants_tset_compatibility.tsv
fixture=reports/assets/nfl2k5_lions_diagnostic_codex_mod.png
artifact=build/nfl2k5-pants-workflow-20260711
output_xiso="$artifact/ESPN-NFL-2K5-84H0-custom-pants.xiso.iso"
manifest="$artifact/workflow.json"
previews="$artifact/previews"
temporary=$(mktemp -d "$root/build/nfl-pants-compatibility-validate.XXXXXX")
cleanup() {
  rm -f -- "$temporary/fresh.json" "$temporary/fresh.tsv" "$temporary/o_excl.stdout" "$temporary/o_excl.stderr"
  rmdir -- "$temporary" 2>/dev/null || true
}
trap cleanup EXIT

for required in "$source_xiso" "$compatibility" "$compatibility_tsv" "$fixture" "$output_xiso" "$manifest"; do
  [[ -f "$required" && ! -L "$required" ]] || {
    echo "missing/non-regular pants artifact: $required" >&2
    exit 1
  }
done
[[ -d "$previews" && ! -L "$previews" ]] || {
  echo "missing pants preview directory: $previews" >&2
  exit 1
}

printf '%s  %s\n' 423f082f09f3678185663cac1a4dd74fb2094d992e82c92180e7319e486b5d53 "$compatibility" | sha256sum -c - >/dev/null
printf '%s  %s\n' 9d439360f4d1051ddfd13bce994eb0dd7ec9613fdf20026ff73522205e5fdeb7 "$compatibility_tsv" | sha256sum -c - >/dev/null
printf '%s  %s\n' 6ae65b7c4f982fbadb6da20444b21d7a2bb3c13f28a84b22c612967dc8a8f3c8 "$fixture" | sha256sum -c - >/dev/null
printf '%s  %s\n' 49474ae4548f9cb7115d780f6478e9e441d415a0821f6b171a49057b2ae30549 "$manifest" | sha256sum -c - >/dev/null
printf '%s  %s\n' 1c1995cf11e6eece0a2eead7455666e549d740c4a79f13b3ebf2df87dca3c37f "$output_xiso" | sha256sum -c - >/dev/null

python3 -m py_compile tools/nfl_pants_tset_compatibility.py tools/nfl_pants_tset_targets.py tools/nfl_pants_tset_png_import.py tools/nfl_pants_tset_dynamic_validate.py tools/nfl_pants_tset_xiso_patch.py tools/nfl2k5_uniform_pants_png_workflow.py tools/nfl2k5_uniform_pants_png_workflow_verify.py tools/test_nfl_pants_tset_compatibility.py

PYTHONPATH=tools python3 tools/nfl_pants_tset_compatibility.py --index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' --inventory reports/assets/nfl2k5_resource_chunks_v2.json --uniform-inventory reports/assets/nfl2k5_uniform_inventory.json --source-xiso "$source_xiso" --output-json "$temporary/fresh.json" --output-tsv "$temporary/fresh.tsv"
cmp -- "$temporary/fresh.json" "$compatibility"
cmp -- "$temporary/fresh.tsv" "$compatibility_tsv"

PYTHONPATH=tools python3 tools/test_nfl_pants_tset_compatibility.py

PYTHONPATH=tools python3 tools/nfl2k5_uniform_pants_png_workflow_verify.py --source-xiso "$source_xiso" --output-xiso "$output_xiso" --manifest "$manifest" --target-code 84 --target-side H --target-variant 0 --clean-png "$fixture" --previews "$previews"

# Existing final outputs must stop a second workflow before generation.
before_output=$(stat -c '%d:%i:%s:%Y:%Z' "$output_xiso")
before_manifest=$(sha256sum "$manifest" | awk '{print $1}')
set +e
PYTHONPATH=tools python3 tools/nfl2k5_uniform_pants_png_workflow.py --source-xiso "$source_xiso" --target-code 84 --target-side H --target-variant 0 --clean-png "$fixture" --mud-mode darken_60 --output-xiso "$output_xiso" --manifest "$manifest" --preview-dir "$previews" >"$temporary/o_excl.stdout" 2>"$temporary/o_excl.stderr"
status=$?
set -e
[[ $status -ne 0 ]] || {
  echo "pants O_EXCL workflow rerun unexpectedly succeeded" >&2
  exit 1
}
rg -q 'already exists' "$temporary/o_excl.stderr"
[[ $(stat -c '%d:%i:%s:%Y:%Z' "$output_xiso") == "$before_output" ]]
[[ $(sha256sum "$manifest" | awk '{print $1}') == "$before_manifest" ]]

printf '%s  %s\n' 7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 "$source_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' 73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 'extracted/ESPN NFL 2K5 (USA)/default.xbe' | sha256sum -c - >/dev/null
printf '%s  %s\n' 34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' | sha256sum -c - >/dev/null

echo "NFL_PANTS_TSET_COMPATIBILITY_VALIDATION_PASS packages=634 pairs=317 home=317 away=317 layouts=1 allocations=324 compatible=634 incompatible=0 packs=9,A,B,C offsets=341 stored_classes=298 stored=61328..118880 target=84H0 output_sha=1c1995cf11e6eece0a2eead7455666e549d740c4a79f13b3ebf2df87dca3c37f span_sha=989c22072f3b920edfd40bee5fe00bce16ad8db2a3ba54c9865657adf22c4260 changed_bytes=58509 runs=2355 encoded=22284/61328 zero_pad=39044 template_exact_scratch=23 rebuilt_exact_scratch=39033 rebuilt_scratch=39056 mips=6 previews=12 fixture_all_634=true source=unchanged xbe=unchanged pack0=unchanged overflow_refused=true forged_rejected=true symlink_refused=true o_excl=true v3_loader_alias_guard=true runtime_visibility=false xemu_started=false title_executed=false"
