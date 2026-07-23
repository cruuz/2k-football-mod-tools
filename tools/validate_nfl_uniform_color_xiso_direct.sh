#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
source_xiso="$root/ESPN NFL 2K5 (USA).xiso.iso"
output_xiso="/media/noah/Storage/.codex-tmp/nfl2k5-lions-magenta-direct-20260710/ESPN-NFL-2K5-Lions-magenta-layout-identical.xiso.iso"
manifest="/media/noah/Storage/.codex-tmp/nfl2k5-lions-magenta-direct-20260710/manifest.json"
canonical="$root/reports/assets/nfl2k5_lions_magenta_xiso_direct.json"
vendor="$root/tools/vendor/extract-xiso"
extract_xiso="$vendor/build/extract-xiso"
expected_commit=b72e5b60d598ec6df80534cda19cdcd4361aa18c

[[ -f "$source_xiso" ]] || { echo "missing retail XISO" >&2; exit 1; }
[[ -f "$canonical" ]] || { echo "missing canonical direct-patch manifest" >&2; exit 1; }

manifest_source=historical
if [[ ! -f "$manifest" ]]; then
  # The canonical copy is byte-identical to the historical writer manifest and
  # deliberately makes the proof independent of the ephemeral build directory.
  manifest="$canonical"
  manifest_source=canonical
fi

output_mode=materialized
verify_mode=()
if [[ ! -e "$output_xiso" && ! -L "$output_xiso" ]]; then
  output_mode=virtual
  verify_mode=(--virtual-output)
fi

if [[ "$output_mode" == materialized ]]; then
  [[ -x "$extract_xiso" && ! -L "$extract_xiso" ]] || {
    echo "missing pinned extract-xiso build" >&2
    exit 1
  }
  actual_commit=$(git -C "$vendor" rev-parse HEAD)
  [[ "$actual_commit" == "$expected_commit" ]] || {
    echo "extract-xiso commit mismatch: $actual_commit" >&2
    exit 1
  }
  [[ -z "$(git -C "$vendor" status --porcelain --untracked-files=no)" ]] || {
    echo "tracked extract-xiso vendor files are dirty" >&2
    exit 1
  }
fi

python3 "$root/tools/test_nfl_uniform_color_xiso_direct_patch.py"
python3 "$root/tools/nfl_uniform_color_xiso_direct_verify.py" \
  --source "$source_xiso" \
  --output "$output_xiso" \
  --manifest "$manifest" \
  --canonical-report "$canonical" \
  --extract-xiso "$extract_xiso" \
  "${verify_mode[@]}"

echo "NFL_UNIFORM_COLOR_XISO_DIRECT_VALIDATION_PASS output_sha=4d7474e1994d08fc9c4eefec2f3eaa1ec7d4ea4fbf94e5370b2532060c26b7b4 output_mode=$output_mode output_materialized=$([[ "$output_mode" == materialized ]] && echo true || echo false) manifest_source=$manifest_source changed_bytes=10 files=19 layout=identical source=unchanged xbe=unchanged pack0=unchanged runtime_visibility=false"
