#!/usr/bin/env python3
"""Validate the APF roster identity writer without publishing game bytes."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_roster_identity_patch as writer
from mod_editor.apf_studio import save_roster_players as raw_save


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


def _validate_raw_save_lane() -> tuple[int, str]:
    if (
        len(raw_save.FIELDS) != 149
        or len(raw_save.PLAYER_TEXT_FIELDS_BY_ID) != 15
        or "jersey_number" not in raw_save.FIELDS_BY_ID
        or "position" not in raw_save.FIELDS_BY_ID
        or not callable(raw_save.make_patch)
        or not callable(raw_save.verify_patch)
        or not callable(raw_save.write_new_save)
    ):
        raise writer.RosterIdentityError(
            "Raw Save Players shipped field/write contract changed"
        )
    test_paths = (
        ROOT / "tests/mod_editor/test_apf_save_roster_players.py",
        ROOT / "tests/mod_editor/test_apf_save_roster_players_gui.py",
    )
    if not all(path.is_file() for path in test_paths):
        return 0, "shipped-contract"
    suite = unittest.TestSuite()
    loader = unittest.defaultTestLoader
    for name in (
        "tests.mod_editor.test_apf_save_roster_players",
        "tests.mod_editor.test_apf_save_roster_players_gui",
    ):
        suite.addTests(loader.loadTestsFromName(name))
    count = suite.countTestCases()
    result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise writer.RosterIdentityError(
            "Raw Save Players write/reopen validation failed"
        )
    return count, "full-retail-free-roundtrip"


def main() -> int:
    try:
        writer._self_test()  # type: ignore[attr-defined]
        raw_save_tests, raw_save_mode = _validate_raw_save_lane()
        if not SOURCE.is_file():
            print(
                "APF_ROSTER_IDENTITY_VALIDATION_PASS "
                f"private_source=false self_test=true raw_save_tests={raw_save_tests} "
                f"raw_save_mode={raw_save_mode} "
                "on_disc_numbers=locked raw_save_numbers=editable "
                "retail_bytes=0 offsets=0"
            )
            return 0
        allocations = writer.inventory(SOURCE)
        selected = next(item for item in allocations if item.editable)
        replacement = "X" if selected.text != "X" else "Y"
        result = writer.build_patch(
            SOURCE, {selected.pool_index: replacement}
        )
        manifest_text = json.dumps(result.manifest, sort_keys=True)
        if (
            result.manifest.get("mode") != "patched"
            or len(result.entry_bytes) <= 0
            or replacement in manifest_text
            or "pack_offset" in manifest_text
            or "byte_offset" in manifest_text
            or result.manifest.get("validation", {}).get(
                "fixed_outer_allocation_preserved"
            )
            is not True
        ):
            raise writer.RosterIdentityError(
                "Changed-path validation did not satisfy the retail-free contract"
            )
        print(
            "APF_ROSTER_IDENTITY_VALIDATION_PASS "
            f"private_source=true allocations={len(allocations)} "
            f"editable={sum(item.editable for item in allocations)} "
            f"owners={sum(item.known_owner_count for item in allocations)} "
            f"changed={result.manifest['output']['decoded_changed_byte_count']} "
            f"raw_save_tests={raw_save_tests} raw_save_mode={raw_save_mode} "
            "on_disc_numbers=locked "
            "raw_save_numbers=editable retail_bytes=0 offsets=0"
        )
        return 0
    except (writer.RosterIdentityError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
