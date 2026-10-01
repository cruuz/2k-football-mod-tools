#!/usr/bin/env bash
# DESIGN: full production composition proof; never launches xemu.
set -Eeuo pipefail
umask 077
STACK=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
BASE='/home/noah/Desktop/2K5-8 Editors/ultimate/ULTIMATE_BUILD_RECIPE_2026-09-23_final_DRAFT.json'
BUILDER='/home/noah/Desktop/2K5-8 Editors/ultimate/build_ultimate.py'
OUT=/media/noah/Storage/.b76-research/pb/astra-build
mkdir -p "$OUT"
SESSION=$(mktemp -d "$OUT/phase5.XXXXXX")
DISC="$SESSION/final.xiso.iso"
cleanup() {
  local code=$?
  rm -f -- "$DISC"
  printf 'PROVED OFFLINE: build exit %s; disposable disc removed; evidence %s\n' "$code" "$SESSION"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
python3 "$STACK/pb/recipes/compose.py" "$BASE" "$SESSION/recipe.json"
printf '%s\n' "$SESSION" > "$STACK/pb/receipts/phase5/build-location.txt"
sha256sum "$BASE" "$SESSION/recipe.json" > "$SESSION/recipe-hashes.txt"
mkdir "$SESSION/tmp"
nice -n 15 taskset -c 0-23 env ULTIMATE_NO_REEXEC=1 TMPDIR="$SESSION/tmp" \
  python3 "$BUILDER" "$STACK" "$DISC" --recipe "$SESSION/recipe.json" \
  --strict-pending > "$SESSION/build.log" 2>&1
python3 "$STACK/pb/recipes/check_full_build.py" "$SESSION" "$BASE" phase5
