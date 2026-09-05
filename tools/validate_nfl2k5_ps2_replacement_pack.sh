#!/usr/bin/env bash
# Deterministic validator for the PS2 replacement-pack export.
#
# Runs the pack verifier's self-test, which builds a synthetic pack, its
# mapping manifest and its project from scratch and proves: a correct pack
# verifies; the audit tool independently reports xbox_mapping_ready on the
# same folder; and a single changed output byte, an extra file, a receipt
# entry naming an unedited target, a filename the manifest does not map, a
# missing file, a forged provenance block, a stray directory and an
# uncanonical filename are each rejected. It also proves that a run without
# the project is downgraded rather than passed, because the check that no
# exported file names an unedited target cannot run without it. No game data
# is required.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile mod_editor/core/ps2_export_service.py \
    tools/nfl2k5_ps2_replacement_pack_verify.py \
    tools/nfl2k5_ps2_replacement_pack_audit.py
python3 tools/nfl2k5_ps2_replacement_pack_verify.py --selftest

echo "NFL2K5_PS2_REPLACEMENT_PACK_VALIDATION_PASS"
