#!/usr/bin/bash
set -euo pipefail

script_path=${BASH_SOURCE[0]}
case "$script_path" in
  */*) script_dir=${script_path%/*} ;;
  *) script_dir=. ;;
esac
root="$(CDPATH= builtin cd -- "$script_dir/.." && builtin pwd -P)"
builtin cd -- "$root"

rg_dir=/home/noah/.nvm/versions/node/v22.22.0/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/codex-path

exec /usr/bin/env -i \
  GIT_CONFIG_GLOBAL=/dev/null \
  GIT_CONFIG_NOSYSTEM=1 \
  HOME=/home/noah \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  PATH="/usr/bin:/bin:$rg_dir" \
  PYTHONDONTWRITEBYTECODE=1 \
  PYTHONHASHSEED=0 \
  PYTHONNOUSERSITE=1 \
  PYTHONUTF8=1 \
  TMPDIR=/tmp \
  TZ=UTC \
  /usr/bin/python3 -I -B tools/validate_all_mod_editor_capabilities.py "$@"
