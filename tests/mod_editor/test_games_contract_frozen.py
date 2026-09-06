"""The frozen contract files match their pins, and the pins match their changelog entry.

If this fails after you edited something under ``mod_editor/games/`` or a
contract test: you moved the contract.  Put it back, or follow the procedure in
``docs/product/GAME_MODULE_CONTRACT.md`` -- bump ``CONTRACT_VERSION``, add a
``(unreleased)`` changelog entry, ``python -m mod_editor.games pins --write``,
run the conformance suite, commit that alone.  Loosening this file is itself a
pinned edit.  Pins are loud, not preventive; the procedure is what makes a move
deliberate.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.games import contract, pins  # noqa: E402

EXPLANATION = (
    "\n\nA frozen contract file or its pins moved. Either revert the edit, or follow the "
    "version procedure (bump CONTRACT_VERSION, add a '(unreleased)' CONTRACT_CHANGELOG.md "
    "entry, run 'python -m mod_editor.games pins --write', run the conformance suite, and "
    "commit that alone). See docs/product/GAME_MODULE_CONTRACT.md."
)


def _scratch_copy() -> Path:
    root = Path(tempfile.mkdtemp(prefix="contract-pins-"))
    for relative in pins.FROZEN_FILES + (
        "mod_editor/games/" + pins.PINS_NAME,
        "mod_editor/games/" + pins.CHANGELOG_NAME,
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return root


class FrozenContractTests(unittest.TestCase):
    def test_frozen_files_match_their_pins(self) -> None:
        problems = pins.check()
        self.assertEqual(problems, [], "\n".join(problems) + EXPLANATION)

    def test_the_frozen_set_is_the_contract_and_its_tests(self) -> None:
        names = set(pins.FROZEN_FILES)
        for required in (
            "mod_editor/games/contract.py", "mod_editor/games/__init__.py",
            "mod_editor/games/registry_merge.py", "mod_editor/games/conformance.py",
            "mod_editor/games/chooser.py", "mod_editor/games/chooser_qt.py",
            "mod_editor/games/pins.py", "tests/mod_editor/test_games_contract.py",
            "tests/mod_editor/test_games_contract_frozen.py",
            "tests/mod_editor/test_games_conformance.py", "tests/mod_editor/test_games_chooser.py",
        ):
            self.assertIn(required, names)
        recorded = pins.read()
        self.assertIsNotNone(recorded)
        self.assertEqual(set(recorded["files"]), names)
        self.assertEqual(recorded["contract_version"], contract.CONTRACT_VERSION)

    def test_the_changelog_names_the_current_version_first_with_its_digest(self) -> None:
        entries = pins.changelog_entries()
        self.assertTrue(entries, "CONTRACT_CHANGELOG.md has no entries")
        self.assertEqual(entries[0].version, contract.CONTRACT_VERSION)
        self.assertEqual(entries[0].pins_digest, pins.digest(pins.read()))


class PinsProcedureTests(unittest.TestCase):
    """The detector catches an edit; the writer refuses without a version bump."""

    def setUp(self) -> None:
        self.root = _scratch_copy()
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_an_edit_to_a_frozen_file_is_reported_by_name(self) -> None:
        self.assertEqual(pins.check(self.root), [])
        target = self.root / "mod_editor/games/contract.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# moved\n", encoding="utf-8", newline="\n")
        problems = pins.check(self.root)
        self.assertTrue(any("mod_editor/games/contract.py changed" in item for item in problems), problems)
        self.assertIn(pins.PROCEDURE, problems)

    def test_rewriting_pins_without_a_new_entry_is_caught(self) -> None:
        target = self.root / "mod_editor/games/chooser.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# moved\n", encoding="utf-8", newline="\n")
        document = pins.compute(self.root)
        pins.pins_path(self.root).write_bytes(pins.canonical_bytes(document))  # bypassing the tool
        problems = pins.check(self.root)
        self.assertTrue(any("moved without a new entry" in item for item in problems), problems)

    def test_write_refuses_a_released_version_and_accepts_a_bumped_one(self) -> None:
        changelog = pins.changelog_path(self.root)
        text = changelog.read_text(encoding="utf-8")
        released = text.replace(f"## {contract.CONTRACT_VERSION} (unreleased)", f"## {contract.CONTRACT_VERSION}")
        changelog.write_text(released, encoding="utf-8", newline="\n")
        target = self.root / "mod_editor/games/registry_merge.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# moved\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(contract.ContractError, "released; its pins are fixed"):
            pins.write(self.root)
        major, minor = (int(part) for part in contract.CONTRACT_VERSION.split("."))
        bumped = f"{major}.{minor + 1}"
        with self.assertRaisesRegex(contract.ContractError, "has no '## "):
            pins.write(self.root, bumped)
        changelog.write_text(
            released.replace("## " + contract.CONTRACT_VERSION, f"## {bumped} (unreleased)\n\nAdded a field.\n\n## {contract.CONTRACT_VERSION}", 1),
            encoding="utf-8", newline="\n",
        )
        pins.write(self.root, bumped)
        self.assertEqual(pins.check(self.root, bumped), [])
        self.assertEqual(pins.read(self.root)["contract_version"], bumped)
        self.assertEqual(pins.changelog_entries(self.root)[0].pins_digest, pins.digest(pins.read(self.root)))
        with self.assertRaisesRegex(contract.ContractError, "never goes backwards"):
            pins.write(self.root, contract.CONTRACT_VERSION)

    def test_release_drops_the_marker_and_freezes(self) -> None:
        pins.write(self.root, release=True)
        self.assertFalse(pins.changelog_entries(self.root)[0].unreleased)
        self.assertEqual(pins.check(self.root), [])
        with self.assertRaisesRegex(contract.ContractError, "already released"):
            pins.write(self.root, release=True)
        with self.assertRaisesRegex(contract.ContractError, "released; its pins are fixed"):
            pins.write(self.root)


if __name__ == "__main__":
    unittest.main()
