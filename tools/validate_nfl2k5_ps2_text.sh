#!/usr/bin/env bash
# Deterministic validator for bounded PS2 on-disc text editing.
#
# Runs the three tools' self-tests and the full conformance suite, which
# between them prove, with no game data at all:
#
#   * a synthetic UTF-16LE STRG bank parses and rebuilds byte-identically, and
#     a terminator-only allocation is reported read-only;
#   * the writer refuses an over-length replacement, an empty one, a dropped or
#     added inline token, a read-only allocation, an unknown bank or index, two
#     edits on one allocation, a stale expected digest, an LZ-compressed bank
#     and an edit that would change nothing -- and leaves no destination file
#     behind when it does;
#   * a same-length edit and a shorter, zero-filled edit both write into a
#     synthetic ISO9660 volume and verify;
#   * the verifier FAILS on a byte changed elsewhere in the replaced pack, on a
#     byte changed elsewhere in the image, on a same-length overwrite of a
#     string the recipe never named, on a moved pointer, on a resized image and
#     on a patch report that disagrees with the bytes;
#   * the verifier imports neither the patcher, nor the catalog, nor the ISO
#     writer's reader.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"

python3 -m py_compile \
  tools/nfl2k5_ps2_text_target_catalog.py \
  tools/nfl2k5_ps2_text_patch.py \
  tools/nfl2k5_ps2_text_verify.py

python3 tools/nfl2k5_ps2_text_target_catalog.py --selftest
python3 tools/nfl2k5_ps2_text_patch.py --selftest
python3 tools/nfl2k5_ps2_text_verify.py --selftest

python3 -m unittest -v tests.mod_editor.test_nfl2k5_ps2_text

echo "NFL2K5_PS2_TEXT_VALIDATION_PASS"
