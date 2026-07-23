#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
recipe="$root/reports/asset_samples/apf_roster/uniform_all_families_built_in_capacity.v1.json"

usage() {
  echo "usage: $0 --source-game DIR --output-game NEW_DIR [--preflight-only]" >&2
}

source_game=
output_game=
preflight_only=false
while (($#)); do
  case "$1" in
    --source-game)
      (($# >= 2)) || { usage; exit 2; }
      source_game=$2
      shift 2
      ;;
    --output-game)
      (($# >= 2)) || { usage; exit 2; }
      output_game=$2
      shift 2
      ;;
    --preflight-only)
      preflight_only=true
      shift
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -n "$source_game" && -n "$output_game" ]] || { usage; exit 2; }
[[ -d "$source_game" && ! -L "$source_game" ]] || {
  echo "error: source game must be a real directory" >&2
  exit 1
}
source_game=$(realpath -e -- "$source_game")

required=("0A" "0B" "1A" "1B" "default.xex")
for name in "${required[@]}"; do
  [[ -f "$source_game/$name" && ! -L "$source_game/$name" ]] || {
    echo "error: source game lacks regular $name" >&2
    exit 1
  }
done
[[ -d "$source_game/\$SystemUpdate" && ! -L "$source_game/\$SystemUpdate" ]] || {
  echo 'error: source game lacks real $SystemUpdate directory' >&2
  exit 1
}
update="$source_game/\$SystemUpdate/su20076000_00000000"
[[ -f "$update" && ! -L "$update" ]] || {
  echo 'error: source game lacks regular $SystemUpdate payload' >&2
  exit 1
}

declare -A expected_sha=(
  [0A]=dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e
  [0B]=775bd47bbac3101938eb7f8b83bf1a71925776fb36b6ef4773ba4f8f6368df53
  [1A]=9f48974f4a63d1827a1ca6bbe847aeaa6911cdb884f84f4d3bbd0a9a1eb6eacb
  [1B]=04dd4a16240f94db79671b9f4a46bf60d7b23a2cfc3146e37a686587b6a0c084
  [default.xex]=981a57143b0a665b2220f72366e1368c5374b91c77a22d93945439d51a2cd28f
  [su20076000_00000000]=39a492de1d957e767657dfe7fb5ff3b315a22c10aa8e9d4009c524362d851fc8
)
for name in "${required[@]}"; do
  actual=$(sha256sum -- "$source_game/$name")
  actual=${actual%% *}
  [[ "$actual" == "${expected_sha[$name]}" ]] || {
    echo "error: source $name is not the pinned APF retail file" >&2
    exit 1
  }
done
actual=$(sha256sum -- "$update")
actual=${actual%% *}
[[ "$actual" == "${expected_sha[su20076000_00000000]}" ]] || {
  echo 'error: source $SystemUpdate payload differs' >&2
  exit 1
}

output_parent=$(dirname -- "$output_game")
output_name=$(basename -- "$output_game")
[[ "$output_name" != . && "$output_name" != .. && "$output_name" != */* ]] || {
  echo "error: output game basename is unsafe" >&2
  exit 1
}
[[ -d "$output_parent" && ! -L "$output_parent" ]] || {
  echo "error: output parent must already be a real directory" >&2
  exit 1
}
output_parent=$(realpath -e -- "$output_parent")
output_game="$output_parent/$output_name"
[[ ! -e "$output_game" && ! -L "$output_game" ]] || {
  echo "error: refusing to replace output game directory" >&2
  exit 1
}
case "$output_game/" in
  "$source_game/"*)
    echo "error: output game may not be inside the retail source" >&2
    exit 1
    ;;
esac

if [[ "$preflight_only" == true ]]; then
  echo "APF_UNIFORM_SELECTOR_MOD_PREFLIGHT_PASS source=retail output=new"
  exit 0
fi

stage="$output_parent/.${output_name}.apf-selector-partial.$$"
[[ ! -e "$stage" && ! -L "$stage" ]] || {
  echo "error: staging path already exists" >&2
  exit 1
}
mkdir -- "$stage"
marker="$stage/.owned-by-apf-uniform-selector-builder"
: > "$marker"
cleanup() {
  if [[ -f "$marker" && ! -L "$stage" ]]; then
    rm -rf -- "$stage"
  fi
}
trap cleanup EXIT INT TERM

mkdir -- "$stage/\$SystemUpdate" "$stage/.apf-all-family-selector"
for name in 0B 1A 1B default.xex; do
  cp --reflink=auto --preserve=mode,timestamps -- "$source_game/$name" "$stage/$name"
done
cp --reflink=auto --preserve=mode,timestamps -- "$update" \
  "$stage/\$SystemUpdate/su20076000_00000000"

python3 "$root/tools/apf_uniform_selector_patch.py" \
  --index "$source_game/0A" \
  --recipe "$recipe" \
  --output-volume "$stage/0A" \
  --manifest "$stage/.apf-all-family-selector/manifest.json"

python3 "$root/tools/apf_uniform_selector_verify.py" \
  --source-index "$source_game/0A" \
  --recipe "$recipe" \
  --output-volume "$stage/0A" \
  --manifest "$stage/.apf-all-family-selector/manifest.json" \
  --json "$stage/.apf-all-family-selector/verify.json"

for name in 0B 1A 1B default.xex; do
  actual=$(sha256sum -- "$stage/$name")
  actual=${actual%% *}
  [[ "$actual" == "${expected_sha[$name]}" ]] || {
    echo "error: installed $name changed during the transaction" >&2
    exit 1
  }
done
actual=$(sha256sum -- "$stage/\$SystemUpdate/su20076000_00000000")
actual=${actual%% *}
[[ "$actual" == "${expected_sha[su20076000_00000000]}" ]] || {
  echo 'error: installed $SystemUpdate payload changed during the transaction' >&2
  exit 1
}

mv -- "$stage" "$output_game"
stage=
rm -- "$output_game/.owned-by-apf-uniform-selector-builder"
marker=
trap - EXIT INT TERM

echo "APF_UNIFORM_SELECTOR_MOD_BUILD_PASS output=$output_game output_0A_sha256=d2823acba35284dc35f08d3a9706476d08aba95120ccbbd168b987904f643d5a"
