#!/usr/bin/env bash
set -u

umask 077

studio_name="APF 2K8 Mod Studio"

show_studio_error() {
    local message=$1
    if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]] && command -v zenity >/dev/null 2>&1; then
        zenity --error --title="$studio_name" --width=540 --text="$message"
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


if [[ ! -f "$portable_root/mod_editor/apf_studio/__main__.py" || -L "$portable_root/mod_editor/apf_studio/__main__.py" ]]; then
    show_studio_error "A required application file is missing. Keep the portable folder together, or run install.sh again. Missing: $portable_root/mod_editor/apf_studio/__main__.py"
    exit 1
fi
cd -- "$portable_root" || {
    show_studio_error "The application folder could not be opened: $portable_root"
    exit 1
}

studio_state_base=${XDG_STATE_HOME:-}
if [[ -z "$studio_state_base" ]]; then
    if [[ -n "${HOME:-}" && "$HOME" = /* ]]; then
        studio_state_base="$HOME/.local/state"
    else
        studio_state_base=""
    fi
fi
if [[ -n "$studio_state_base" && "$studio_state_base" != /* ]]; then
    show_studio_error "XDG_STATE_HOME must be an absolute path. Fix that environment setting and reopen the app."
    exit 1
fi
studio_state_dir="$studio_state_base/apf2k8-mod-studio"
if [[ -z "$studio_state_base" || -L "$studio_state_dir" ]] || ! mkdir -p -- "$studio_state_dir" 2>/dev/null; then
    studio_state_dir=$(mktemp -d "/tmp/apf2k8-mod-studio-launch-${UID:-user}.XXXXXX" 2>/dev/null || true)
fi
if [[ -z "$studio_state_dir" || ! -d "$studio_state_dir" || -L "$studio_state_dir" ]]; then
    show_studio_error "A private diagnostic folder could not be created. Check permissions for your user state directory."
    exit 1
fi
studio_log="$studio_state_dir/last-launch.log"
if [[ -L "$studio_log" ]]; then
    studio_log="$studio_state_dir/launch-$$.log"
fi
if ! : >"$studio_log" 2>/dev/null; then
    show_studio_error "The diagnostic log could not be created: $studio_log"
    exit 1
fi
chmod 600 -- "$studio_log" 2>/dev/null || true

export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export PYTHONPATH="$portable_root"
# Keep diagnostics, recent-file metadata, and the replacement-only recovery
# project in the exact same private directory.  This also makes the guarded
# mktemp fallback coherent when HOME/XDG state is unavailable.
export APF2K8_MOD_STUDIO_STATE_DIR="$studio_state_dir"

# Headless launch check: imports the app and its GUI, prints the version, exits.
if [[ "${1:-}" == "--update-check" ]]; then
    exec "$studio_python" -B -s -c 'import mod_editor.apf_studio; import mod_editor.apf_studio.__main__; import mod_editor.apf_studio.gui; print(mod_editor.apf_studio.__version__)'
fi

if ! "$studio_python" -c 'from PyQt5 import QtWidgets' >>"$studio_log" 2>&1; then
    printf -v studio_message '%s\n\nDetails: %s' \
        'PyQt5 is missing from the selected Python runtime. Restore that runtime or install PyQt5 into it.' \
        "$studio_log"
    show_studio_error "$studio_message"
    exit 1
fi
if ! "$studio_python" -c 'import PIL' >>"$studio_log" 2>&1; then
    printf -v studio_message '%s\n\nDetails: %s' \
        'Pillow is missing from the selected Python runtime. Restore that runtime or install Pillow into it.' \
        "$studio_log"
    show_studio_error "$studio_message"
    exit 1
fi
if ! "$studio_python" -c 'import mod_editor.apf_studio.gui' >>"$studio_log" 2>&1; then
    printf -v studio_message '%s\n\nDetails: %s' \
        'An APF 2K8 Mod Studio program file is missing or damaged. Run install.sh again, or re-extract the portable release.' \
        "$studio_log"
    show_studio_error "$studio_message"
    exit 1
fi

if [[ "${1:-}" == "--version" || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    exec "$studio_python" -m mod_editor.apf_studio "$@"
fi

if "$studio_python" -m mod_editor.apf_studio "$@" >>"$studio_log" 2>&1; then
    exit 0
else
    studio_status=$?
fi

studio_details=$(tail -n 12 -- "$studio_log" 2>/dev/null || true)
if [[ -z "$studio_details" ]]; then
    studio_details="No diagnostic message was produced."
fi
printf -v studio_message 'APF 2K8 Mod Studio could not start.\n\n%s\n\nFull details: %s' \
    "$studio_details" "$studio_log"
show_studio_error "$studio_message"
exit "$studio_status"
