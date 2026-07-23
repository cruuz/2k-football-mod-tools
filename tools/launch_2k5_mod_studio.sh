#!/usr/bin/env bash
set -u

studio_name="2K5 Mod Studio"

show_studio_error() {
    local message=$1
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --title="$studio_name" --width=520 --text="$message"
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --title "$studio_name" --error "$message"
    else
        printf '%s: %s\n' "$studio_name" "$message" >&2
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    show_studio_error "Python 3 is not installed. Install Python 3, PyQt5, and Pillow, then reopen 2K5 Mod Studio."
    exit 1
fi

launcher_path=${BASH_SOURCE[0]}
if command -v readlink >/dev/null 2>&1; then
    resolved_launcher=$(readlink -f -- "$launcher_path" 2>/dev/null || true)
    if [[ -n "$resolved_launcher" ]]; then
        launcher_path=$resolved_launcher
    fi
fi
launcher_dir=$(CDPATH= cd -- "$(dirname -- "$launcher_path")" && pwd -P)
portable_root=$(dirname -- "$launcher_dir")

# A portable build keeps this launcher in <app>/tools. An installed Python
# package needs no working-directory adjustment.
if [[ -f "$portable_root/mod_editor/__main__.py" ]]; then
    cd -- "$portable_root" || {
        show_studio_error "The application folder could not be opened. Reinstall 2K5 Mod Studio."
        exit 1
    }
fi

state_base=${XDG_STATE_HOME:-${HOME:-}/.local/state}
if [[ -z "$state_base" ]]; then
    state_base=/tmp
fi
studio_state_dir="$state_base/2k5-mod-studio"
if ! mkdir -p -- "$studio_state_dir" 2>/dev/null; then
    studio_state_dir=/tmp
fi
studio_log="$studio_state_dir/last-launch.log"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1

if ! python3 -c 'from PyQt5 import QtWidgets; import PIL; import mod_editor' >"$studio_log" 2>&1; then
    show_studio_error "A required application component is missing. Install Python 3, PyQt5, and Pillow, then reopen 2K5 Mod Studio.\n\nDetails were saved to: $studio_log"
    exit 1
fi

if python3 -m mod_editor --studio "$@" >"$studio_log" 2>&1; then
    exit 0
else
    studio_status=$?
fi

studio_details=$(tail -n 12 -- "$studio_log" 2>/dev/null || true)
if [[ -z "$studio_details" ]]; then
    studio_details="No diagnostic message was produced."
fi
show_studio_error "2K5 Mod Studio could not start.\n\n$studio_details\n\nFull details: $studio_log"
exit "$studio_status"
