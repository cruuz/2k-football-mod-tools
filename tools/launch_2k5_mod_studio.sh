#!/usr/bin/env bash
set -u

studio_name="2K5 Mod Studio"

show_studio_error() {
    local message=$1
    if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v zenity >/dev/null 2>&1; then
        zenity --error --title="$studio_name" --width=520 --text="$message"
    elif [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v kdialog >/dev/null 2>&1; then
        kdialog --title "$studio_name" --error "$message"
    else
        printf '%s: %s\n' "$studio_name" "$message" >&2
    fi
}


launcher_path=${BASH_SOURCE[0]}
if command -v readlink >/dev/null 2>&1; then
    resolved_launcher=$(readlink -f -- "$launcher_path" 2>/dev/null || true)
    if [[ -n "$resolved_launcher" ]]; then
        launcher_path=$resolved_launcher
    fi
fi
launcher_dir=$(CDPATH= cd -- "$(dirname -- "$launcher_path")" && pwd -P)
portable_root=$(dirname -- "$launcher_dir")

# An in-app update records the interpreter that already runs this install.
# A local runtime travels with the app, so SteamOS needs no system changes.
studio_python=${MOD_STUDIO_PYTHON:-}
if [[ -z "$studio_python" && -f "$portable_root/.studio-python" ]]; then
    IFS= read -r studio_python < "$portable_root/.studio-python" || true
    if [[ -n "$studio_python" && "$studio_python" != /* ]]; then
        studio_python="$portable_root/$studio_python"
    fi
fi
if [[ -z "$studio_python" ]]; then
    for candidate in "$portable_root/.venv/bin/python3" "$portable_root/venv/bin/python3" "$portable_root/runtime/bin/python3"; do
        if [[ -x "$candidate" ]]; then
            studio_python=$candidate
            break
        fi
    done
fi
if [[ -z "$studio_python" ]]; then
    studio_python=$(command -v python3 || true)
fi
if [[ -z "$studio_python" || ! -x "$studio_python" ]]; then
    show_studio_error "The Python runtime for this copy is missing. Restore the previous application folder or select your installed Python with MOD_STUDIO_PYTHON, then reopen the studio."
    exit 1
fi


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
export PYTHONPATH="$portable_root"

# Headless launch check: imports the app and its GUI, prints the version, exits.
if [[ "${1:-}" == "--update-check" ]]; then
    exec "$studio_python" -B -s -c 'import mod_editor; import mod_editor.__main__; import mod_editor.gui.studio_qt; print(mod_editor.__version__)'
fi

if ! "$studio_python" -c 'from PyQt5 import QtWidgets; import PIL; import mod_editor' >"$studio_log" 2>&1; then
    show_studio_error "A required application component is missing. Restore the Python runtime and its PyQt5 and Pillow packages, then reopen 2K5 Mod Studio.\n\nDetails were saved to: $studio_log"
    exit 1
fi

if "$studio_python" -m mod_editor --studio "$@" >"$studio_log" 2>&1; then
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
