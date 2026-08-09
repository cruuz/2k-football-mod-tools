#!/usr/bin/bash
set -euo pipefail

script_path=${BASH_SOURCE[0]}
case "$script_path" in
  */*) script_dir=${script_path%/*} ;;
  *) script_dir=. ;;
esac
root="$(CDPATH= builtin cd -- "$script_dir/.." && builtin pwd -P)"
builtin cd -- "$root"

rg_path=
for candidate in /usr/bin/rg /bin/rg; do
  if [[ -f $candidate && -x $candidate ]]; then
    rg_path=$candidate
    break
  fi
done
if [[ -z $rg_path ]]; then
  rg_path=$(type -P -- rg || true)
fi
if [[ -z $rg_path ]]; then
  echo "required command not found: rg" >&2
  exit 1
fi
case "$rg_path" in
  /*) ;;
  *)
    rg_name=${rg_path##*/}
    case "$rg_path" in
      */*) rg_dir=${rg_path%/*} ;;
      *) rg_dir=. ;;
    esac
    rg_dir=$(CDPATH= builtin cd -- "$rg_dir" && builtin pwd -P)
    rg_path=$rg_dir/$rg_name
    ;;
esac
rg_dir=${rg_path%/*}

exec /usr/bin/env -i \
  GIT_CONFIG_GLOBAL=/dev/null \
  GIT_CONFIG_NOSYSTEM=1 \
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
