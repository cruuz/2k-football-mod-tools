"""Carry roster names off a memory card and onto a disc.

Reading a PS2 save has worked for a while, and writing disc text has worked for
a while. Nothing joined them, so somebody with a season of edited names on a
memory card had to retype several hundred of them by hand.

The importer reads the ROST arena and emits a project the unified build already
knows how to apply. Two limits are deliberate and both are tested here, because
each one is a place where being convenient would be worse than being strict:

* **A name too long for its slot is skipped, never truncated.** Every name
  lives in a byte span the disc will not grow. Silently shortening one means
  the modder does not find out until they see it in game; refusing it means
  they choose the shorter spelling themselves.
* **A player the disc does not have is skipped, never invented.** The importer
  refuses to run at all without a resolver from a loaded disc, so it can never
  guess at how the disc numbers its own roster.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

import nfl2k5_save_roster_import as importer  # noqa: E402


def _resolver(known: int = 2):
    def resolve(player: int, field: str) -> str | None:
        if player >= known:
            return None
        return f"nfl2k5.roster.o100.primary_players.{player:04d}.{field}_name"
    return resolve


class ProjectShapeTests(unittest.TestCase):
    def test_names_become_a_project_the_build_accepts(self) -> None:
        rows = [
            {"player": 0, "field": "first", "value": "Alpha",
             "capacity_bytes": 12},
            {"player": 1, "field": "last", "value": "Bravo",
             "capacity_bytes": 12},
        ]
        project, skipped = importer.build_project(rows, _resolver())
        self.assertEqual(project["schema"], importer.PROJECT_SCHEMA)
        self.assertEqual(set(project), {"edits", "purpose", "schema"})
        self.assertEqual(len(project["edits"]), 2)
        self.assertEqual(skipped, [])

    def test_each_edit_matches_the_kind_the_build_validates(self) -> None:
        """Producer and consumer must agree or this is JSON nobody reads."""
        rows = [{"player": 0, "field": "first", "value": "Alpha",
                 "capacity_bytes": 12}]
        project, _skipped = importer.build_project(rows, _resolver())
        edit = project["edits"][0]
        self.assertEqual(set(edit), {"kind", "selector", "text"})
        build = (
            _REPO_ROOT / "tools" / "nfl2k5_visual_mod_project.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'UNIVERSAL_FIXED_TEXT_FIELDS = {"kind", "selector", "text"}', build
        )
        self.assertEqual(edit["kind"], "universal_fixed_text")


class RefusalTests(unittest.TestCase):
    def test_a_name_too_long_for_its_slot_is_skipped_not_truncated(self) -> None:
        rows = [{"player": 0, "field": "first", "value": "Bob",
                 "capacity_bytes": 12},
                {"player": 1, "field": "last",
                 "value": "Vandermeulen-Whitfield", "capacity_bytes": 12}]
        project, skipped = importer.build_project(rows, _resolver())
        self.assertEqual([e["text"] for e in project["edits"]], ["Bob"])
        self.assertEqual(len(skipped), 1)
        self.assertIn("will not fit", skipped[0]["reason"])
        self.assertEqual(skipped[0]["value"], "Vandermeulen-Whitfield")

    def test_capacity_is_measured_in_the_encoding_the_disc_uses(self) -> None:
        """UTF-16LE: a 7-character name is 14 bytes, not 7."""
        rows = [{"player": 0, "field": "first", "value": "Abcdefg",
                 "capacity_bytes": 12},
                {"player": 1, "field": "last", "value": "Ok",
                 "capacity_bytes": 12}]
        _project, skipped = importer.build_project(rows, _resolver())
        self.assertEqual(len(skipped), 1)
        self.assertIn("14 bytes", skipped[0]["reason"])

    def test_a_name_exactly_filling_its_slot_is_kept(self) -> None:
        rows = [{"player": 0, "field": "first", "value": "Abcdef",
                 "capacity_bytes": 12}]
        project, skipped = importer.build_project(rows, _resolver())
        self.assertEqual(skipped, [])
        self.assertEqual(project["edits"][0]["text"], "Abcdef")

    def test_a_player_the_disc_does_not_have_is_skipped(self) -> None:
        rows = [{"player": 0, "field": "first", "value": "Alpha",
                 "capacity_bytes": 12},
                {"player": 9, "field": "first", "value": "Ghost",
                 "capacity_bytes": 12}]
        project, skipped = importer.build_project(rows, _resolver())
        self.assertEqual(len(project["edits"]), 1)
        self.assertIn("no matching player", skipped[0]["reason"])

    def test_blank_names_are_ignored_rather_than_written(self) -> None:
        rows = [{"player": 0, "field": "first", "value": "   ",
                 "capacity_bytes": 12},
                {"player": 1, "field": "last", "value": "Bravo",
                 "capacity_bytes": 12}]
        project, _skipped = importer.build_project(rows, _resolver())
        self.assertEqual(len(project["edits"]), 1)

    def test_it_refuses_to_run_without_a_disc_resolver(self) -> None:
        """It must never guess how the disc numbers its own roster."""
        rows = [{"player": 0, "field": "first", "value": "Alpha",
                 "capacity_bytes": 12}]
        with self.assertRaises(importer.SaveImportError) as caught:
            importer.build_project(rows, None)
        self.assertIn("load the disc first", str(caught.exception))

    def test_a_save_with_nothing_applicable_fails_loudly(self) -> None:
        rows = [{"player": 9, "field": "first", "value": "Ghost",
                 "capacity_bytes": 12}]
        with self.assertRaises(importer.SaveImportError):
            importer.build_project(rows, _resolver())


class SaveReaderTests(unittest.TestCase):
    def test_the_synthetic_save_round_trips_into_names(self) -> None:
        """Uses the PS2 lane's own fixture, so no memory card is needed."""
        import nfl2k5_ps2_save as ps2

        save = ps2._synthetic_save()
        slots = list(ps2.player_name_slots(save))
        rows = [
            {"player": int(s["player"]), "field": str(s["field"]),
             "value": str(s["value"]), "capacity_bytes": int(s["capacity_bytes"])}
            for s in slots if str(s["field"]) in importer.FIELD_NAMES
        ]
        self.assertTrue(rows)
        project, skipped = importer.build_project(rows, _resolver())
        self.assertEqual(skipped, [])
        self.assertEqual(
            {e["text"] for e in project["edits"]}, {"Alpha", "Bravo"}
        )

    def test_a_missing_save_is_refused_with_its_name(self) -> None:
        with self.assertRaises(importer.SaveImportError) as caught:
            importer.read_save_names(Path("/nowhere/BASLUS-20919Missing"))
        self.assertIn("Missing", str(caught.exception))


class ScopeTests(unittest.TestCase):
    def test_only_name_fields_are_claimed(self) -> None:
        """Ratings and numbers are separate proved lanes with their own writers."""
        self.assertEqual(importer.FIELD_NAMES, ("first", "last"))
        source = (
            _REPO_ROOT / "tools" / "nfl2k5_save_roster_import.py"
        ).read_text(encoding="utf-8")
        self.assertIn("Names only", source)


if __name__ == "__main__":
    unittest.main()
