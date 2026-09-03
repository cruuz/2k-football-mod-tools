#!/usr/bin/env bash
# Set xemu's display aspect for the flatpak install: `xemu_aspect.sh 16x9` or `xemu_aspect.sh native`.
# xemu rewrites xemu.toml on exit, so this refuses to run while xemu is up.
set -euo pipefail
want="${1:-}"
case "$want" in
  16x9|native|4x3|auto) ;;
  *) echo "usage: $0 16x9|native|4x3|auto" >&2; exit 2 ;;
esac
toml="$HOME/.var/app/app.xemu.xemu/data/xemu/xemu/xemu.toml"
if pgrep -x xemu >/dev/null 2>&1 || pgrep -f "^/app/bin/xemu" >/dev/null 2>&1; then
  echo "xemu is running; close it first (it rewrites $toml on exit)" >&2; exit 1
fi
cur=$(grep -E "^aspect_ratio" "$toml" | head -1 | sed -E "s/.*= *'([^']*)'.*/\1/")
if [[ "$cur" == "$want" ]]; then echo "aspect_ratio already '$want'"; exit 0; fi
sed -i -E "s/^aspect_ratio = '[^']*'/aspect_ratio = '$want'/" "$toml"
echo "aspect_ratio: '$cur' -> '$(grep -E "^aspect_ratio" "$toml" | sed -E "s/.*= *'([^']*)'.*/\1/")'"
