"""Public-truth gate for the bounded NFL 2K5 face-shield editor."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from mod_editor.capabilities.validate_registry import validate_data


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "mod_editor/capabilities/registry.v1.json"


class Nfl2k5FaceShieldRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.capability = next(
            row for row in cls.document["capabilities"]
            if row["id"] == "nfl2k5.players.disc_roster"
        )

    def test_registry_remains_structurally_valid(self) -> None:
        self.assertIs(validate_data(self.document, check_files=True), self.document)

    def test_public_claim_names_exact_safe_boundary(self) -> None:
        searchable = " ".join(
            [self.capability["summary"], self.capability["gui"]["reason"]]
            + self.capability["input_constraints"]
            + [self.capability["selectors"]["notes"]]
        )
        folded = searchable.casefold()
        for required in (
            "+0x20 bits 15..16",
            "0 none, 1 clear, or 2 dark",
            "reserved value 3 is refused",
            "not a home/away tint",
            "loaded roster/franchise save may override",
        ):
            self.assertIn(required, folded)
        self.assertEqual(
            self.capability["backend"]["module"],
            "tools/nfl_player_roster_general_workflow.py",
        )
        self.assertIn(
            "tests/test_nfl_player_roster_general_workflow.py",
            self.capability["evidence"],
        )


if __name__ == "__main__":
    unittest.main()
