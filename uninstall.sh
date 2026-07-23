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
installer="$release_root/packaging/apf2k8_mod_studio_installer.py"

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'APF 2K8 Mod Studio cannot be uninstalled because Python 3 is missing.' >&2
    exit 1
fi
if [[ ! -f "$installer" || -L "$installer" ]]; then
    printf 'APF 2K8 Mod Studio uninstaller component is missing: %s\n' "$installer" >&2
    exit 1
fi

exec python3 "$installer" uninstall "$@"
