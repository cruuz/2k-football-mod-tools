"""The capability counts scattered across the repository are one fact, checked.

Fifteen places state how many rows the capability registry has, how many are
covered, how many distinct validators they name, or how many belong to one
game. All four are pure functions of ``mod_editor/capabilities/registry.v1.json``.
``tools/registry_add_rows.py`` moves them all when it adds a row; nothing
checked them, and they had drifted: a row classified ``unknown`` that
nevertheless names a validator is *covered* by the rule
``validate_all_mod_editor_capabilities.build_validation_plan`` asserts, and
*deferred* by the rule ``registry_add_rows.counts`` used, so
``EXPECTED_COVERED_CAPABILITIES`` sat a row short and the pin meant to refuse
drift was the drift.

The rule is: **a row is covered when it names a validator.** These tests keep
every site, and both tools, on that one rule.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import check_registry_counts as counts  # noqa: E402
import registry_add_rows  # noqa: E402
import validate_all_mod_editor_capabilities as validate_all  # noqa: E402

REGISTRY = json.loads((ROOT / "mod_editor/capabilities/registry.v1.json")
                      .read_text(encoding="utf-8"))


class Derivation(unittest.TestCase):
    def test_a_row_is_covered_when_it_names_a_validator(self) -> None:
        derived = counts.derive(REGISTRY)
        rows = REGISTRY["capabilities"]
        self.assertEqual(derived["capabilities"], len(rows))
        self.assertEqual(derived["covered"],
                         sum(1 for row in rows if row["validation_command"]))
        self.assertEqual(derived["deferred"],
                         sum(1 for row in rows if row["validation_command"] is None))
        self.assertEqual(derived["covered"] + derived["deferred"], derived["capabilities"])

    def test_a_row_with_no_validator_must_say_why(self) -> None:
        """The classification is what makes a missing validator allowed."""

        for row in REGISTRY["capabilities"]:
            if row["validation_command"] is None:
                with self.subTest(row=row["id"]):
                    self.assertIn(row["classification"], counts.MAY_LACK_A_VALIDATOR)

    def test_a_misfiled_row_is_refused_by_name(self) -> None:
        broken = json.loads(json.dumps(REGISTRY))
        victim = next(row for row in broken["capabilities"]
                      if row["classification"] == "offline-writer-proved")
        victim["validation_command"] = None
        with self.assertRaises(ValueError) as caught:
            counts.derive(broken)
        self.assertIn(victim["id"], str(caught.exception))


class BothToolsAgree(unittest.TestCase):
    def test_the_pin_mover_counts_the_way_the_pin_checker_asserts(self) -> None:
        total, covered, validators, game = registry_add_rows.counts(REGISTRY["capabilities"])
        derived = counts.derive(REGISTRY)
        self.assertEqual(total, derived["capabilities"])
        self.assertEqual(covered, derived["covered"])
        self.assertEqual(validators, derived["unique_validators"])
        self.assertEqual(game, derived["nfl2k5_xbox_capabilities"])

    def test_validate_all_expects_what_the_registry_implies(self) -> None:
        derived = counts.derive(REGISTRY)
        self.assertEqual(validate_all.EXPECTED_CAPABILITIES, derived["capabilities"])
        self.assertEqual(validate_all.EXPECTED_COVERED_CAPABILITIES, derived["covered"])
        self.assertEqual(validate_all.EXPECTED_DEFERRED_CAPABILITIES, derived["deferred"])
        self.assertEqual(validate_all.EXPECTED_UNIQUE_VALIDATORS, derived["unique_validators"])
        self.assertEqual(validate_all.EXPECTED_DEFERRED_IDS, counts.deferred_ids(REGISTRY))


class EverySite(unittest.TestCase):
    def test_every_count_in_the_repository_agrees_with_the_registry(self) -> None:
        self.assertEqual(counts.main(["--quiet"]), 0,
                         "run tools/check_registry_counts.py to see which site drifted")

    def test_the_checker_covers_the_sites_the_pin_mover_edits(self) -> None:
        """A site the mover writes and the checker ignores is a site that can rot."""

        checked = {relative for relative, _what, _pattern
                   in counts.sites(counts.derive(REGISTRY), counts.deferred_ids(REGISTRY))}
        for constant in ("RUNTIME_GATE", "APF_RUNTIME_GATE", "INSTALLER_TEST",
                         "PACKAGING_TEST", "VALIDATE_ALL", "APF_README", "APF_STATUS",
                         "GETTING_STARTED", "STATUS"):
            with self.subTest(site=constant):
                self.assertIn(getattr(registry_add_rows, constant), checked)


if __name__ == "__main__":
    unittest.main(verbosity=2)
