#!/usr/bin/env bash
set -u

script_path=${BASH_SOURCE[0]}
if command -v readlink >/dev/null 2>&1; then
    resolved_script=$(readlink -f -- "$script_path" 2>/dev/null || true)
    if [[ -n "$resolved_script" ]]; then
        script_path=$resolved_script
    fi
fi
release_root=$(CDPATH= cd -- "$(dirname -- "$script_path")" && pwd -P)
launcher="$release_root/tools/launch_apf2k8_mod_studio.sh"

if [[ ! -x "$launcher" || -L "$launcher" ]]; then
    printf 'APF 2K8 Mod Studio launcher is missing or not executable: %s\n' "$launcher" >&2
    exit 1
fi

exec "$launcher" "$@"
