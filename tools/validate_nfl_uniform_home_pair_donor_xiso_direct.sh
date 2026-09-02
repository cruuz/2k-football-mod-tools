#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_xiso="$root/ESPN NFL 2K5 (USA).xiso.iso"
artifact_dir="/media/noah/Storage/.codex-tmp/nfl2k5-lions-home-49ers-pair-20260710"
output_xiso="$artifact_dir/ESPN-NFL-2K5-Lions-home-49ers-pair-donor-exact.xiso.iso"
manifest="$artifact_dir/manifest.json"
canonical="$root/reports/assets/nfl2k5_lions_home_49ers_pair_xiso_direct.json"
vendor="$root/tools/vendor/extract-xiso"
extract_xiso="$vendor/build/extract-xiso"
expected_commit=b72e5b60d598ec6df80534cda19cdcd4361aa18c
expected_extract_sha=222e7763df8f16d9b252c625fac5ef551cd25cdf031a785b3ec73c6e53c5d7f2

[[ -f "$source_xiso" ]] || { echo "missing retail XISO" >&2; exit 1; }
[[ -f "$output_xiso" ]] || { echo "missing donor-exact output XISO" >&2; exit 1; }
[[ -f "$manifest" && -f "$canonical" ]] || {
  echo "missing writer manifest or canonical report" >&2
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

python3 -m py_compile \
  "$root/tools/nfl_uniform_home_pair_donor_xiso_direct_patch.py" \
  "$root/tools/nfl_uniform_home_pair_donor_xiso_direct_verify.py" \
  "$root/tools/test_nfl_uniform_home_pair_donor_xiso_direct_patch.py"
python3 "$root/tools/test_nfl_uniform_color_xiso_direct_patch.py"
python3 "$root/tools/test_nfl_uniform_home_pair_donor_xiso_direct_patch.py"
python3 "$root/tools/nfl_uniform_home_pair_donor_xiso_direct_verify.py" \
  --source "$source_xiso" \
  --output "$output_xiso" \
  --manifest "$manifest" \
  --canonical-report "$canonical" \
  --extract-xiso "$extract_xiso"

echo "NFL_UNIFORM_HOME_PAIR_DONOR_XISO_DIRECT_VALIDATION_PASS output_sha=85af4081bd01017960a0b9c27ec2446828305ae3ce32200f1755a9d0f000d3ee target=09H0 donor=25H0 target_body_sha=8d176356012bcb041035fa0b6eb992d67b701e2fab3a7e88d6547e3da195b74a changed_bytes=6 files=19 layout=identical source=unchanged xbe=unchanged pack0=unchanged packB=unchanged o_excl=yes runtime_visibility=false title_executed=false"
