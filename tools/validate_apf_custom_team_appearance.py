#!/usr/bin/env python3
"""Retail-free release gate for the custom-team appearance contract."""

from __future__ import annotations

from pathlib import Path
import sys

# The installed Windows runtime uses an embeddable CPython ``._pth`` file,
# which does not automatically add this script's directory to ``sys.path``.
# Restore it before importing sibling tools so direct subprocess launches work
# the same way as a normal Python installation.
_here = str(Path(__file__).resolve().parent)
if _here not in sys.path:
    sys.path.insert(0, _here)

import apf_custom_team_appearance_patch as writer


def main() -> int:
    bank = writer.AppearanceBank(
        tuple(0xFF000000 + index for index in range(10)),
        bytes.fromhex("0703020009000000"),
        bytes.fromhex("5000000302010000"),
    )
    source = writer.CustomTeamAppearance(32, bank, bank)
    preset = writer.eagles_2017_preset(source)
    assert writer.USER_SLOTS == tuple(range(32, 40))
    assert preset.home.palette[8] == 0xFF004C54
    assert preset.home.helmet_selector == bytes.fromhex("0708020009000000")
    assert preset.home.logo_selector == bytes.fromhex("1E00010009000000")
    assert writer.decode_replacement_payload(
        writer.encode_replacement_payload(preset)
    ) == preset
    for unsafe in (31, 40, True):
        try:
            writer.asset_id(unsafe)
        except writer.CustomTeamAppearanceError:
            pass
        else:
            raise AssertionError(f"unsafe custom-team slot accepted: {unsafe!r}")
    print("custom-team appearance contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
