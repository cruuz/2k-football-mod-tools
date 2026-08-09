#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
source_xiso='ESPN NFL 2K5 (USA).xiso.iso'
artifact_dir=/media/noah/Storage/.codex-tmp/nfl2k5-lions-png-import-xiso-20260711
output_xiso="$artifact_dir/ESPN-NFL-2K5-Lions-CODEX-MOD-jersey-layout-identical.xiso.iso"
writer_manifest="$artifact_dir/writer_manifest.json"
canonical=reports/assets/nfl2k5_lions_09H0_diagnostic_png_import_xiso_direct.json
replacement=reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.tset.bin
import_manifest=reports/assets/nfl2k5_lions_09H0_diagnostic_png_import.json
input_png=reports/assets/nfl2k5_lions_diagnostic_codex_mod.png
previews=reports/assets/nfl2k5_lions_09H0_diagnostic_png_import_previews
index='extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'
vendor=tools/vendor/extract-xiso
extract_xiso="$vendor/build/extract-xiso"
expected_commit=b72e5b60d598ec6df80534cda19cdcd4361aa18c
expected_extract_sha=222e7763df8f16d9b252c625fac5ef551cd25cdf031a785b3ec73c6e53c5d7f2
fresh=$(mktemp -d /tmp/nfl-png-import-xiso-validate.XXXXXX)
trap 'rm -rf -- "$fresh"' EXIT

for required in "$source_xiso" "$output_xiso" "$writer_manifest" "$canonical" \
                "$replacement" "$import_manifest" "$input_png"
do
  [[ -f "$required" ]] || { echo "missing required file: $required" >&2; exit 1; }
done
[[ -d "$previews" ]] || { echo "missing canonical previews" >&2; exit 1; }
[[ -x "$extract_xiso" ]] || { echo "missing pinned extract-xiso" >&2; exit 1; }

actual_commit=$(git -C "$vendor" rev-parse HEAD)
[[ "$actual_commit" == "$expected_commit" ]] || {
  echo "extract-xiso commit mismatch: $actual_commit" >&2
  exit 1
}
[[ -z "$(git -C "$vendor" status --porcelain --untracked-files=no)" ]] || {
  echo "tracked extract-xiso vendor files are dirty" >&2
  exit 1
}
actual_extract_sha=$(sha256sum "$extract_xiso" | awk '{print $1}')
[[ "$actual_extract_sha" == "$expected_extract_sha" ]] || {
  echo "extract-xiso binary hash mismatch: $actual_extract_sha" >&2
  exit 1
}

printf '%s  %s\n' \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 \
  "$source_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  b9f47fcec3e284a12ea30f390035dd29f97fa62507330ba3ff30391cf4e10ae6 \
  "$output_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d \
  "$index" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8 \
  "$replacement" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  3500f6e6a3fddc4680a43214dd8f283bb8d1a13b355dcb2e8bbb349417613d80 \
  "$import_manifest" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  c4ddd7d3bd206d29d5a743dc78ea2ca69352807fcd643eacd3dcf4307e7b0f41 \
  "$canonical" | sha256sum -c - >/dev/null

python3 -m py_compile \
  tools/nfl_tset_png_import_xiso_direct_patch.py \
  tools/nfl_tset_png_import_xiso_direct_verify.py \
  tools/test_nfl_tset_png_import_xiso_direct_patch.py
PYTHONPATH=tools python3 tools/test_nfl_tset_png_import_xiso_direct_patch.py

PYTHONPATH=tools python3 tools/nfl_tset_png_import_xiso_direct_verify.py \
  --source "$source_xiso" \
  --output "$output_xiso" \
  --writer-manifest "$writer_manifest" \
  --canonical-report "$canonical" \
  --replacement-span "$replacement" \
  --import-manifest "$import_manifest" \
  --input-png "$input_png" \
  --previews "$previews" \
  --index "$index" \
  --extract-xiso "$extract_xiso"

# A second writer invocation must fail at O_EXCL without changing the artifact.
before_output=$(sha256sum "$output_xiso" | awk '{print $1}')
before_manifest=$(sha256sum "$writer_manifest" | awk '{print $1}')
set +e
PYTHONPATH=tools python3 tools/nfl_tset_png_import_xiso_direct_patch.py \
  --source-xiso "$source_xiso" \
  --replacement-span "$replacement" \
  --import-manifest "$import_manifest" \
  --output-xiso "$output_xiso" \
  --writer-manifest "$writer_manifest" >"$fresh/o_excl.stdout" \
  2>"$fresh/o_excl.stderr"
status=$?
set -e
[[ $status -ne 0 ]] || { echo "O_EXCL writer rerun unexpectedly succeeded" >&2; exit 1; }
rg -q 'already exists' "$fresh/o_excl.stderr"
[[ $(sha256sum "$output_xiso" | awk '{print $1}') == "$before_output" ]]
[[ $(sha256sum "$writer_manifest" | awk '{print $1}') == "$before_manifest" ]]

printf '%s  %s\n' \
  7b4b493b9492ecfb353ae97c7243210c8dd4fe1601eb34549eea67ad6ee68bc9 \
  "$source_xiso" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 \
  'extracted/ESPN NFL 2K5 (USA)/default.xbe' | sha256sum -c - >/dev/null

echo "NFL_TSET_PNG_IMPORT_XISO_DIRECT_VALIDATION_PASS output_sha=b9f47fcec3e284a12ea30f390035dd29f97fa62507330ba3ff30391cf4e10ae6 span_sha=76630c16fe8e1b60fabbdd2ec6c8c100ae8020061c27765678ef81ea885d8ae8 target=09H0 chunk=1 changed_bytes=70333 runs=3265 files=19 root_sector=33 layout=identical source=unchanged xbe=unchanged pack0=unchanged decoded=177024 encoded=22285 stored=74688 zero_pad=52403 colors=32 mips=6 previews=12 o_excl=yes runtime_visibility=false xemu_started=false title_executed=false"
