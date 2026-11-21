#!/bin/bash
# Run from the archive root by the Finder entries and the Linux APF private setup.
set -u
case "$1" in
    2k5) name="2K5 Mod Studio"; module=mod_editor; launcher=tools/launch_2k5_mod_studio.sh ;;
    apf) name="APF 2K8 Mod Studio"; module=mod_editor.apf_studio; launcher=tools/launch_apf2k8_mod_studio.sh ;;
    *) exit 2 ;;
esac
platform=$2
shift 2
root=$(pwd -P)
fail() {
    printf '%s could not start.\n%s\n' "$name" "$1" >&2
    if [[ -t 0 && $pause == yes ]]; then read -r -p 'Press Return to close this window.' _; fi
    exit 1
}
pause=no
[[ $# -gt 0 ]] || pause=yes
[[ -f $launcher && -f packaging/requirements-studio.txt && -f packaging/posix_studio_setup.py ]] ||
    fail 'Extract the entire Studio archive, then open the .command file inside it.'
unset PYTHONHOME
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$root"

python=${MOD_STUDIO_PYTHON:-}
if [[ -z $python && -f .studio-python ]]; then
    IFS= read -r python < .studio-python || true
    if [[ -n $python && $python != /* ]]; then python="$root/$python"; fi
fi
if [[ -n $python ]]; then
    chosen=$(command -v "$python") || fail "The selected Python could not be found at $python. Restore it or set MOD_STUDIO_PYTHON to its executable."
    [[ -x $chosen ]] || fail "The selected Python cannot run: $chosen"
    python=$chosen
else
    for candidate in "$root/.venv/bin/python3" "$root/venv/bin/python3" "$root/runtime/bin/python3"; do
        if [[ -x $candidate ]]; then python=$candidate; break; fi
    done
fi
supported() {
    "$1" -I -c 'import sys; sys.exit(sys.version_info[:2] not in ((3, 11), (3, 12), (3, 13)))' >/dev/null 2>&1
}
if [[ -z $python ]]; then
    # Finder's PATH can omit both the python.org framework and Homebrew.
    candidates=(python3 python3.13 python3.12 python3.11)
    if [[ $platform == macos ]]; then
        for version in 3.13 3.12 3.11; do
            candidates+=("/Library/Frameworks/Python.framework/Versions/$version/bin/python3")
            for prefix in /opt/homebrew /usr/local; do
                candidates+=("$prefix/bin/python$version" "$prefix/opt/python@$version/bin/python$version")
            done
        done
    fi
    for candidate in "${candidates[@]}"; do
        chosen=$(command -v "$candidate") || continue
        # Apple's command-line tools stub asks to install developer tools when invoked on a clean Mac.
        if [[ $chosen == /usr/bin/python3 && $OSTYPE == darwin* ]] && ! xcode-select -p >/dev/null 2>&1; then continue; fi
        if supported "$chosen"; then python=$chosen; break; fi
    done
fi
if [[ $platform == macos ]]; then
    install_python='Install Python 3.11, 3.12 or 3.13 from https://www.python.org/downloads/macos/ and open this launcher again.'
else
    install_python='Install Python 3.11, 3.12 or 3.13 with its venv module, or select it with MOD_STUDIO_PYTHON, then rerun ./APF-2K8-Mod-Studio.sh --setup.'
fi
[[ -n $python ]] || fail "$install_python"
imports='from PyQt5 import QtWidgets; import PIL; import numpy; import capstone; import unicorn'
setup_only=no
[[ ${1:-} != --setup ]] || setup_only=yes
if [[ $setup_only == yes ]] || ! "$python" -I -c "$imports" >/dev/null 2>&1; then
    supported "$python" || fail "$install_python"
    "$python" -I -B "$root/packaging/posix_studio_setup.py" "$root" "$imports" ||
        fail 'Private setup did not finish. Review the message above and reopen this launcher to retry.'
    python="$root/.venv/bin/python3"
fi
if [[ $setup_only == yes ]]; then printf '%s\n' "Setup finished. Open $name with this launcher."; exit 0; fi
export MOD_STUDIO_PYTHON="$python"
if [[ $# -eq 0 || ${1:-} == --update-check ]]; then
    exec /bin/bash "$root/$launcher" "$@"
fi
# Explicit CLI actions use normal stdout and the module's own parser. Its no-argument default opens the GUI.
exec "$python" -m "$module" "$@"
