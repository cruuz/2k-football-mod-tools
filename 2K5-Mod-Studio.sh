#!/usr/bin/env bash
# 2K5 Mod Studio - Linux / SteamOS / Steam Deck launcher.
#
#   ./2K5-Mod-Studio.sh            start the Studio
#   ./2K5-Mod-Studio.sh --setup    first run: create .venv and install the Studio packages
#
# The Linux archive carries the application but no Python runtime. --setup builds
# a private runtime inside this folder (.venv), which needs no root access and no
# change to the system partition, so it also works on a Steam Deck in Desktop Mode.
# Every other argument is passed to tools/launch_2k5_mod_studio.sh, which picks the
# .venv (or MOD_STUDIO_PYTHON), checks the packages and shows a dialog if anything
# is missing.
set -u

script_path=${BASH_SOURCE[0]}
if command -v readlink >/dev/null 2>&1; then
    resolved_script=$(readlink -f -- "$script_path" 2>/dev/null || true)
    if [[ -n "$resolved_script" ]]; then
        script_path=$resolved_script
    fi
fi
release_root=$(CDPATH= cd -- "$(dirname -- "$script_path")" && pwd -P)
launcher="$release_root/tools/launch_2k5_mod_studio.sh"
requirements="$release_root/packaging/requirements-studio.txt"

if [[ "${1:-}" == "--setup" ]]; then
    if [[ ! -f "$requirements" ]]; then
        printf '%s\n' "Setup cannot continue: $requirements is missing. Extract the whole archive and run this script from inside the extracted folder." >&2
        exit 1
    fi
    if ! command -v python3 >/dev/null 2>&1; then
        printf '%s\n' \
            "Python 3 is not installed, so 2K5 Mod Studio cannot be set up." \
            "Linux Mint / Ubuntu / Debian: sudo apt install python3 python3-venv python3-pip" >&2
        exit 1
    fi
    if ! python3 -c 'import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 12) else 1)' >/dev/null 2>&1; then
        printf '%s\n' \
            "Note: the Studio packages are pinned for Python 3.11 or 3.12 and this is $(python3 -V 2>&1)." \
            "If the install below fails, install Python 3.11 or 3.12 and run: MOD_STUDIO_PYTHON=/path/to/python3 ./2K5-Mod-Studio.sh --setup" >&2
    fi
    base_python=${MOD_STUDIO_PYTHON:-python3}
    venv_dir="$release_root/.venv"
    if [[ ! -x "$venv_dir/bin/python3" ]]; then
        printf '%s\n' "Creating a private Python runtime in $venv_dir ..."
        if ! "$base_python" -m venv "$venv_dir"; then
            rm -rf -- "$venv_dir"
            printf '%s\n' \
                "Could not create the runtime. On Linux Mint / Ubuntu / Debian install the venv module first:" \
                "    sudo apt install python3-venv" \
                "On SteamOS or Steam Deck, open Desktop Mode, then Konsole, and check that 'python3 -m venv --help' works." >&2
            exit 1
        fi
    fi
    printf '%s\n' "Installing the Studio packages (about 110 MB to download, 400 MB on disk, needs internet) ..."
    if ! "$venv_dir/bin/python3" -m pip install -r "$requirements"; then
        printf '%s\n' \
            "The package install failed. Check the internet connection and the messages above, then run" \
            "    ./2K5-Mod-Studio.sh --setup" \
            "again. It is safe to repeat." >&2
        exit 1
    fi
    if ! "$venv_dir/bin/python3" -c 'from PyQt5 import QtWidgets; import PIL, numpy, capstone, unicorn' >/dev/null 2>&1; then
        printf '%s\n' "The packages installed but one of them does not load. Run the setup again; if it repeats, share the messages above on the Discord." >&2
        exit 1
    fi
    printf '%s\n' "Setup finished. Start 2K5 Mod Studio with:  ./2K5-Mod-Studio.sh"
    exit 0
fi

if [[ ! -f "$launcher" || -L "$launcher" ]]; then
    printf '2K5 Mod Studio launcher is missing: %s\n' "$launcher" >&2
    printf '%s\n' "Extract the whole archive again and run this script from inside the extracted folder." >&2
    exit 1
fi

if [[ ! -x "$release_root/.venv/bin/python3" && ! -f "$release_root/.studio-python" && -z "${MOD_STUDIO_PYTHON:-}" ]]; then
    # No private runtime yet. The launcher falls back to the system python3, which is
    # fine when the packages are already installed there; when they are not, it shows
    # a dialog. Tell a terminal user the one command that fixes it.
    if ! python3 -c 'from PyQt5 import QtWidgets; import PIL, numpy, capstone, unicorn' >/dev/null 2>&1; then
        printf '%s\n' "First run on this computer? Run  ./2K5-Mod-Studio.sh --setup  once to install the Studio packages." >&2
    fi
fi

# A zip extractor can drop the executable bit; running it through bash works either way.
if [[ -x "$launcher" ]]; then
    exec "$launcher" "$@"
fi
exec bash "$launcher" "$@"
