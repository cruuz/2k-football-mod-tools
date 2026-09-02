"""The camera surface, and the two boundaries it must never overstate.

Camera was the one investigation that started from nothing: before this work the
repo had not located a single camera byte. What it found is a complete, exact
map of the settings menu on both products -- and a writer that does not exist on
either. Both halves have to survive, so these tests pin the map *and* the
refusals.

The specific error this file guards against is an off-by-table read. In both
games the camera preset names live in a run of adjacent enum label tables, each
ending in a ``Custom`` entry, and the table immediately after the camera one is
the replay-camera enum. Reading past the bound yields plausible, tempting names
-- ``Broadcast``, ``TV Broadcast``, ``In Stands`` -- that are not gameplay camera
presets at all.
"""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from mod_editor.core.camera_inspection import (
    CAMERA_REPORT_SCHEMA,
    CAMERA_SNAPSHOT_SCHEMA,
    DEFAULT_CAMERA_REPORT,
    DEFAULT_CAMERA_SNAPSHOT,
    build_snapshot,
    inspect_camera_options,
)
from mod_editor.core.errors import ValidationError


ROOT = Path(__file__).resolve().parents[2]

#: Names that belong to the *replay* camera enum, which sits directly after the
#: gameplay camera enum in both binaries. None of these may ever be published as
#: a gameplay camera preset.
REPLAY_ENUM_NAMES = {
    "1st Person", "TV Broadcast", "In Stands", "On Field", "Realistic",
    "Quick", "Default",
}


def _available() -> bool:
    return DEFAULT_CAMERA_REPORT.is_file()


@unittest.skipUnless(_available(), "camera options report is not present")
class CameraInspectionTests(unittest.TestCase):
    def test_both_games_expose_their_exact_named_settings(self) -> None:
        nfl = inspect_camera_options("nfl2k5")
        apf = inspect_camera_options("apf2k8")
        self.assertEqual(nfl["setting_count"], 7)
        self.assertEqual(apf["setting_count"], 9)
        names = [row["name"] for row in nfl["settings"]]
        self.assertEqual(names[:4], [
            "Camera", "QB Pivot Mode", "Runner Pivot Mode", "Pass Play Zoom Out"
        ])
        self.assertIn("Camera Distance", names)
        self.assertIn("Camera Angle", names)
        self.assertIn("Camera Height", names)
        # APF ships a fourth axis 2K5 does not have, and separate Home/Away
        # toggles. Collapsing the two products into one table would lose both.
        apf_names = [row["name"] for row in apf["settings"]]
        self.assertIn("Camera Pitch", apf_names)
        self.assertNotIn("Camera Pitch", names)
        self.assertIn("QB Pivot Mode (Home)", apf_names)

    def test_height_is_not_a_normalised_slider(self) -> None:
        """Distance is a multiplier and Height is world units; only Angle is 0..1.

        A panel that draws all three as one kind of bar is wrong, so the
        distinction is published rather than left to be inferred.
        """

        for game, low, high in (("nfl2k5", 50.0, 300.0), ("apf2k8", 50.0, 500.0)):
            with self.subTest(game=game):
                rows = {row["name"]: row for row in inspect_camera_options(game)["settings"]}
                height = rows["Camera Height"]
                self.assertEqual((height["stock_minimum"], height["stock_maximum"]), (low, high))
                self.assertFalse(height["normalised_0_to_1"])
                self.assertTrue(rows["Camera Angle"]["normalised_0_to_1"])

    def test_every_bound_was_decoded_not_left_unknown(self) -> None:
        for game in ("nfl2k5", "apf2k8"):
            for row in inspect_camera_options(game)["settings"]:
                with self.subTest(game=game, setting=row["name"]):
                    self.assertIsNotNone(row["stored_type"])
                    self.assertIsNotNone(row["stock_minimum"])
                    self.assertIsNotNone(row["stock_maximum"])

    def test_no_replay_camera_name_is_published_as_a_preset(self) -> None:
        for game in ("nfl2k5", "apf2k8"):
            names = {p["name"] for p in inspect_camera_options(game)["presets"]}
            with self.subTest(game=game):
                self.assertFalse(names & REPLAY_ENUM_NAMES,
                                 f"{game} published a replay-enum name as a camera preset")

    def test_2k5_has_six_presets_and_none_are_hidden(self) -> None:
        nfl = inspect_camera_options("nfl2k5")
        self.assertEqual(nfl["preset_count"], 6)
        self.assertEqual([p["name"] for p in nfl["presets"]],
                         ["Standard", "Far", "Side", "Iso", "Blimp", "Custom"])
        # The menu's MAX callback returns 5, so all six are reachable. An
        # earlier reading of this table claimed two hidden presets; it had
        # walked into the next enum.
        self.assertEqual(nfl["presets_present_but_not_selectable"], [])

    def test_apf_blimp_is_authored_but_not_selectable(self) -> None:
        apf = inspect_camera_options("apf2k8")
        self.assertEqual(apf["menu_reachable_preset_count"], 5)
        self.assertEqual(apf["presets_present_but_not_selectable"], ["Blimp"])
        blimp = next(p for p in apf["presets"] if p["name"] == "Blimp")
        self.assertTrue(blimp["fully_authored"])
        # A camera 3,750 units up, which is what its own name says. That
        # agreement between name and geometry is the cross-check the 2K5
        # adjacency never had.
        self.assertGreater(blimp["eye"][1], 3000.0)

    def test_no_writer_is_offered_on_either_product(self) -> None:
        for game in ("nfl2k5", "apf2k8"):
            value = inspect_camera_options(game)
            with self.subTest(game=game):
                self.assertFalse(value["writer_available"])
                self.assertTrue(value["read_only"])
                self.assertTrue(value["why_read_only"])
                self.assertFalse(value["runtime_behaviour_proved"])

    def test_the_archive_only_refusal_is_explicit(self) -> None:
        """The mod people keep trying to build, refuted rather than unproved."""

        for game in ("nfl2k5", "apf2k8"):
            value = inspect_camera_options(game)
            with self.subTest(game=game):
                self.assertFalse(value["archive_only_mod_possible"])
                self.assertIn("no asset-side representation", value["archive_only_mod_note"])

    def test_no_raw_address_reaches_the_public_projection(self) -> None:
        import re
        for game in ("nfl2k5", "apf2k8"):
            text = json.dumps(inspect_camera_options(game))
            with self.subTest(game=game):
                self.assertIsNone(re.search(r"0x[0-9A-Fa-f]{6,}", text))
                self.assertNotIn("virtual_address", text)
                self.assertNotIn("callbacks", text)

    def test_an_unknown_game_is_refused(self) -> None:
        for bad in ("", "madden", "nfl2k5 ; rm", "offset:123"):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                inspect_camera_options(bad)

    def test_a_wrong_schema_report_is_refused(self) -> None:
        """A report that is present but wrong must never be read.

        A *missing* report is a different case and is not an error: a packaged
        build has no reports/ tree at all and falls back to the shipped
        snapshot. That path is covered in ShippedSnapshotTests.
        """

        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            wrong = Path(temporary) / "wrong.json"
            wrong.write_text(json.dumps({"schema": "something/else"}))
            with self.assertRaises(ValidationError):
                inspect_camera_options("nfl2k5", wrong)
            empty = Path(temporary) / "empty.json"
            empty.write_text("[]")
            with self.assertRaises(ValidationError):
                inspect_camera_options("nfl2k5", empty)


@unittest.skipUnless(_available(), "camera options report is not present")
class CameraReportTests(unittest.TestCase):
    def test_the_report_records_its_own_scope_honestly(self) -> None:
        value = json.loads(DEFAULT_CAMERA_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(value["schema"], CAMERA_REPORT_SCHEMA)
        scope = value["scope"]
        self.assertTrue(scope["read_only"])
        self.assertFalse(scope["originals_modified"])
        self.assertFalse(scope["emulator_or_game_launched"])
        self.assertFalse(scope["runtime_behaviour_claimed"])
        self.assertFalse(scope["asset_side_camera_representation_found"])

    def test_the_preset_bound_carries_its_evidence(self) -> None:
        value = json.loads(DEFAULT_CAMERA_REPORT.read_text(encoding="utf-8"))
        for game in ("nfl2k5", "apf2k8"):
            with self.subTest(game=game):
                self.assertTrue(value[game]["preset_count_evidence"])


class ShippedSnapshotTests(unittest.TestCase):
    """The packaged build has no ``reports/`` tree at all.

    The release gate refuses any ``reports/`` path, so a shipped Mod Studio
    carries the sanitized projection under ``mod_editor/data/`` instead. If that
    snapshot goes stale the inspector silently ships yesterday's answer, so it is
    required to equal a fresh projection.
    """

    def test_the_shipped_snapshot_exists_and_declares_its_schema(self) -> None:
        self.assertTrue(DEFAULT_CAMERA_SNAPSHOT.is_file())
        value = json.loads(DEFAULT_CAMERA_SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(value["schema"], CAMERA_SNAPSHOT_SCHEMA)
        for game in ("nfl2k5", "apf2k8"):
            self.assertIn(game, value)

    @unittest.skipUnless(_available(), "camera options report is not present")
    def test_the_shipped_snapshot_matches_a_fresh_projection(self) -> None:
        on_disk = json.loads(DEFAULT_CAMERA_SNAPSHOT.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, build_snapshot())

    def test_the_snapshot_is_used_when_the_private_report_is_absent(self) -> None:
        """This is the path a packaged build actually takes."""

        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            absent = Path(temporary) / "no-report.json"
            value = inspect_camera_options("apf2k8", absent, DEFAULT_CAMERA_SNAPSHOT)
            self.assertEqual(value["presets_present_but_not_selectable"], ["Blimp"])
            self.assertFalse(value["writer_available"])

    def test_missing_both_sources_is_refused_rather_than_empty(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            absent = Path(temporary) / "no-report.json"
            no_snapshot = Path(temporary) / "no-snapshot.json"
            with self.assertRaises(ValidationError):
                inspect_camera_options("nfl2k5", absent, no_snapshot)


if __name__ == "__main__":
    unittest.main()
