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
    printf '%s\n' \
        'APF 2K8 Mod Studio cannot be installed because Python 3 is missing.' \
        'On Linux Mint/Ubuntu: sudo apt install python3 python3-pyqt5 python3-pil' >&2
    exit 1
fi
if [[ ! -f "$installer" || -L "$installer" ]]; then
    printf 'APF 2K8 Mod Studio installer component is missing: %s\n' "$installer" >&2
    exit 1
fi

# Importing the installer loads the packaged compatibility module before the
# release audit runs.  Keep that bootstrap read-only so it cannot create a
# __pycache__ entry that the fail-closed audit would correctly reject.
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$installer" install --source-root "$release_root" "$@"
