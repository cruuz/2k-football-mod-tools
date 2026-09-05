#!/usr/bin/env bash
# Deterministic validator for the PS2 executable-patch lane (interface only).
#
# Runs the lane's self-test: the host's patch catalogue is read, every
# translation is refused with the reason (nothing is mapped to MIPS yet), a
# hand-authored recipe against a synthetic ELF inside a synthetic ISO is
# planned, emitted as a pnach and independently verified, and a pnach whose
# value was changed fails verification. No game data is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/games/nfl2k5_ps2/code_patches.py mod_editor/games/_formats/ps2_elf/__init__.py
python3 -c 'from mod_editor.games.nfl2k5_ps2 import code_patches; raise SystemExit(code_patches.selftest())'

echo "NFL2K5_PS2_CODE_PATCHES_VALIDATION_PASS"
