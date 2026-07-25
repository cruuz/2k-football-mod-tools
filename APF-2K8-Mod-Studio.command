#!/bin/bash
# APF 2K8 Mod Studio - macOS launcher (double-clickable from Finder).
#
# Mirrors tools/launch_apf2k8_mod_studio.sh: it resolves the application root
# from this script's own real path, checks that Python 3, PyQt5, and Pillow are
# importable, shows a friendly terminal error if not, and otherwise starts
# `python3 -m mod_editor.apf_studio`.  BSD readlink has no `-f`, so the real
# path is resolved with a portable symlink-follow loop instead.
set -u

studio_name="APF 2K8 Mod Studio"

pause_and_exit() {
    printf '\n%s\n' "Press Return to close this window."
    read -r _ || true
    exit "$1"
}

fail() {
    printf '%s could not start.\n\n%s\n' "$studio_name" "$1" >&2
    pause_and_exit 1
}

# Resolve this script's real directory, following symlinks, so the application
# root is correct no matter where Finder launched it from.
source_path=${BASH_SOURCE[0]}
while [ -h "$source_path" ]; do
    link_dir=$(cd -P -- "$(dirname -- "$source_path")" >/dev/null 2>&1 && pwd)
    source_path=$(readlink -- "$source_path")
    case $source_path in
        /*) ;;
        *) source_path="$link_dir/$source_path" ;;
    esac
done
app_root=$(cd -P -- "$(dirname -- "$source_path")" >/dev/null 2>&1 && pwd)

if [ -z "$app_root" ] || ! cd -- "$app_root"; then
    fail "The application folder could not be opened. Keep this launcher inside the extracted APF 2K8 Mod Studio folder."
fi

# Prefer python3; accept a python that is actually Python 3.
python_bin=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[0] == 3 else 1)' >/dev/null 2>&1; then
        python_bin=$candidate
        break
    fi
done

if [ -z "$python_bin" ]; then
    fail "Python 3 is not installed. Install Python 3 from https://www.python.org/downloads/ then run: pip3 install PyQt5 Pillow"
fi

export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export PYTHONPATH="$app_root"

if ! "$python_bin" -c 'from PyQt5 import QtWidgets; import PIL; import mod_editor.apf_studio.gui' >/dev/null 2>&1; then
    fail "A required component (PyQt5 or Pillow) is missing. Install both with: pip3 install PyQt5 Pillow"
fi

exec "$python_bin" -m mod_editor.apf_studio "$@"
