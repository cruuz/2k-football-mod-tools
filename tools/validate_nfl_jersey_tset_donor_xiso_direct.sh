#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
source_xiso="$root/ESPN NFL 2K5 (USA).xiso.iso"
artifact_dir=/media/noah/Storage/.codex-tmp/nfl2k5-lions-jersey-falcons-donor-20260710
output_xiso="$artifact_dir/ESPN-NFL-2K5-Lions-home-Falcons-away-jersey-TSET-donor.xiso.iso"
manifest="$artifact_dir/manifest.json"
canonical="$root/reports/assets/nfl2k5_jersey_tset_donor_xiso_direct.json"
evidence="$root/reports/assets/nfl2k5_jersey_tset_donor_evidence.json"
samples="$root/reports/assets/nfl2k5_jersey_tset_donor_samples"
index="$root/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0"
inventory="$root/reports/assets/nfl2k5_resource_chunks_v2.json"
vendor="$root/tools/vendor/extract-xiso"
extract_xiso="$vendor/build/extract-xiso"
expected_commit=b72e5b60d598ec6df80534cda19cdcd4361aa18c
expected_extract_sha=96e6286d371e47e24474a3b7c89ef5c204ddca9c93c95d5ebcb7bcf1d6eb530f
fresh=$(mktemp -d /tmp/nfl-jersey-tset-donor-validate.XXXXXX)
trap 'rm -rf -- "$fresh"' EXIT

[[ -f "$source_xiso" && -f "$output_xiso" ]] || {
  echo "missing retail or donor XISO" >&2
  exit 1
}
[[ -f "$manifest" && -f "$canonical" && -f "$evidence" ]] || {
  echo "missing writer manifest or canonical report/evidence" >&2
  exit 1
}
[[ -x "$extract_xiso" ]] || { echo "missing pinned extract-xiso build" >&2; exit 1; }

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
  73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9 \
  "$root/extracted/ESPN NFL 2K5 (USA)/default.xbe" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  34e5665bc53c393ef978b505e0f1d28d457915ba193f96c3a6113ff4b08b8b3d \
  "$index" | sha256sum -c - >/dev/null

python3 -m py_compile \
  "$root/tools/nfl_jersey_tset_donor_evidence.py" \
  "$root/tools/nfl_jersey_tset_donor_xiso_direct_patch.py" \
  "$root/tools/nfl_jersey_tset_donor_xiso_direct_verify.py" \
  "$root/tools/test_nfl_jersey_tset_donor_xiso_direct_patch.py"

PYTHONPATH="$root/tools" python3 \
  "$root/tools/test_nfl_jersey_tset_donor_xiso_direct_patch.py"

PYTHONPATH="$root/tools" python3 \
  "$root/tools/nfl_jersey_tset_donor_evidence.py" \
  --index 'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0' \
  --inventory reports/assets/nfl2k5_resource_chunks_v2.json \
  --png-dir "$fresh/png" \
  --output "$fresh/evidence.json" >/dev/null
cmp "$fresh/evidence.json" "$evidence"
for name in \
  donor_01A0_jersey00.png \
  donor_01A0_jersey00_mud.png \
  target_09H0_jersey00.png \
  target_09H0_jersey00_mud.png
do
  cmp "$fresh/png/$name" "$samples/$name"
done

printf '%s  %s\n' \
  c9cd83c68553be88c82401be0bb8d78ef417c33ad75837ff7c870b50caa8b5bb \
  "$samples/donor_01A0_jersey00.png" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  c5d3eac336e5f4f23cc924927cd0e6175958a20e56b5b041e213b505bb33088c \
  "$samples/donor_01A0_jersey00_mud.png" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  be7312d3eeef47f74a525bd5a430244aeebbf9f4a4d7031323dd42766253e76d \
  "$samples/target_09H0_jersey00.png" | sha256sum -c - >/dev/null
printf '%s  %s\n' \
  b4d657313adbafc2372464fa559a30feb71c1639c60ed3c2b05fbc57f6225667 \
  "$samples/target_09H0_jersey00_mud.png" | sha256sum -c - >/dev/null

PYTHONPATH="$root/tools" python3 \
  "$root/tools/nfl_jersey_tset_donor_xiso_direct_verify.py" \
  --source "$source_xiso" \
  --output "$output_xiso" \
  --manifest "$manifest" \
  --canonical-report "$canonical" \
  --extract-xiso "$extract_xiso"

echo "NFL_JERSEY_TSET_DONOR_XISO_DIRECT_VALIDATION_PASS output_sha=502b41d2d7813549342861c92e17b9ff1bc83a8f0cb5995401e9abaeb2b288f5 target=09H0 donor=01A0 chunk=1 span=74720 changed_bytes=73304 runs=903 textures=2 pngs=4 descriptors=512x256_P8 files=19 layout=identical source=unchanged xbe=unchanged pack0=unchanged o_excl=yes runtime_visibility=false png_importer=false title_executed=false"
