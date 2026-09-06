"""PCSX2 replacement identities on MVP Baseball 2005: derived, confirmed, and the 0x0E verdict.

Every test here builds the bytes it looks at.  The one thing it reads from the
repository is the *measured document* itself -- counts and filenames, no pixel --
and what it asserts about it is internal consistency: that the schema is the
one the lane loads, that the counts agree with the tables they count, and that
every confirmed filename is one PCSX2 could have written.

The pairing itself is proved by the tool's own ``--selftest``, which builds a
synthetic bank, writes the PNGs PCSX2 would have dumped for it, and pairs the
two; that is exercised here so a broken pairing fails this suite rather than
waiting for the next disc run.
"""

from __future__ import annotations

import json
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
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from mod_editor.games._formats import ea_shps, pcsx2_texture_name  # noqa: E402
from mod_editor.games.contract import Target  # noqa: E402
from mod_editor.games.mvp05_ps2 import art_lane, containers  # noqa: E402

import mvp05_ps2_texture_identities as identities  # noqa: E402


def _target(raw: dict) -> Target:
    return Target(key=raw.get("key", "A.BIG:0:0"), label="t", detail="d", budget="b",
                  searchable="s", raw=raw, fields=())


class DerivedAndConfirmed(unittest.TestCase):
    """What ``replacement_identity`` answers, and why it answers that."""

    def test_a_confirmed_name_wins_over_a_derived_one(self) -> None:
        lane = art_lane.MENU_LANE
        target = _target({"derived_names": {"modern": ["d0.png"], "classic": ["d0.png", "d1.png"]},
                          "confirmed_names": {"modern": ["c0.png"], "classic": ["c0.png", "c1.png"]},
                          "frames": ["20260905142559"]})
        self.assertEqual(lane.replacement_identity(target), "c0.png")
        buckets = lane.replacement_identities(target)
        self.assertEqual(sorted(buckets), ["confirmed:classic", "confirmed:modern",
                                           "derived:classic", "derived:modern"])
        note = lane.identity_note(target)
        self.assertIn("Confirmed by a PCSX2 dump", note)
        self.assertIn("1 frame(s)", note)
        self.assertIn("different name", note)

    def test_a_confirmed_name_with_nothing_derived_says_the_dump_is_all_there_is(self) -> None:
        lane = art_lane.MENU_LANE
        target = _target({"confirmed_names": {"modern": ["c0.png"]},
                          "derived_note": ("no name is derived: this image's palette has 2 entries "
                                           "and PCSX2 hashes a 256-entry CLUT for an 8-bit texture")})
        note = lane.identity_note(target)
        self.assertIn("the dump is the only thing that names it", note)
        self.assertIn("256-entry CLUT", note)
        self.assertEqual(lane.replacement_identity(target), "c0.png")

    def test_a_confirmed_name_the_deriver_agrees_with_says_so(self) -> None:
        lane = art_lane.MENU_LANE
        target = _target({"derived_names": {"modern": ["same.png"]},
                          "confirmed_names": {"modern": ["same.png"]}})
        self.assertIn("produces that same name", lane.identity_note(target))

    def test_without_a_dump_the_derived_name_is_offered_and_labelled(self) -> None:
        lane = art_lane.MENU_LANE
        target = _target({"derived_names": {"modern": ["d0.png"]}})
        self.assertEqual(lane.replacement_identity(target), "d0.png")
        note = lane.identity_note(target)
        self.assertIn("Derived from this texture's own bytes", note)
        self.assertIn("is not confirmed", note)
        self.assertEqual(sorted(lane.replacement_identities(target)), ["derived:modern"])

    def test_an_image_with_no_name_at_all_says_which_and_why(self) -> None:
        lane = art_lane.MENU_LANE
        target = _target({"derived_note": "no name is derived: this image's palette has 17 entries"})
        self.assertIsNone(lane.replacement_identity(target))
        self.assertIn("17 entries", lane.identity_note(target))
        self.assertIn("is not confirmed", lane.identity_note(target))

    def test_the_loader_refuses_a_document_that_is_not_the_lane_s(self) -> None:
        work = Path(tempfile.mkdtemp(prefix="mvp05-identity-"))
        self.addCleanup(shutil.rmtree, work, True)
        missing = work / "absent.json"
        self.assertEqual(art_lane.load_identities(missing), {})
        wrong = work / "wrong.json"
        wrong.write_text(json.dumps({"schema": "someone-elses/v1",
                                     "identities": {"A.BIG:0:0": {"names": {"modern": ["x.png"]}}}}),
                         encoding="utf-8")
        self.assertEqual(art_lane.load_identities(wrong), {})
        right = work / "right.json"
        right.write_text(json.dumps({
            "schema": art_lane.IDENTITY_SCHEMA,
            "identities": {"A.BIG:0:0": {"names": {"modern": ["x.png"]}, "frames": ["f"]},
                           "A.BIG:0:1": {"names": {}}}}), encoding="utf-8")
        self.assertEqual(art_lane.load_identities(right), {"A.BIG:0:0": {"modern": ["x.png"]}})

    def test_a_name_does_not_land_on_a_different_image_at_the_same_key(self) -> None:
        """A key is a position, and the synthetic disc reuses the real archive names.

        The table records what each confirmed image *is* -- its size and its
        pixel code -- and the walker attaches a name only where those agree, so
        a synthetic FEONLY.BIG cannot inherit the retail one's identities.
        """

        work = Path(tempfile.mkdtemp(prefix="mvp05-identity-shape-"))
        self.addCleanup(shutil.rmtree, work, True)
        lane = art_lane.MENU_LANE
        source = lane.synthetic_source(work)
        truth = lane.build_catalogue(source)
        wrong = work / "wrong-shape.json"
        wrong.write_text(json.dumps({
            "schema": art_lane.IDENTITY_SCHEMA,
            "identities": {target.key: {"names": {"modern": ["planted.png"]},
                                        "frames": [], "width": 4095, "height": 4095,
                                        "code": "0x02"}
                           for target in truth.targets}}), encoding="utf-8")
        art_lane._IDENTITY_CACHE.clear()
        planted = lane.walker.walk(source, None, with_identities=False,
                                   identities=art_lane._identity_table(wrong))
        self.assertEqual(planted["totals"]["confirmed"], 0)
        right = work / "right-shape.json"
        right.write_text(json.dumps({
            "schema": art_lane.IDENTITY_SCHEMA,
            "identities": {target.key: {"names": {"modern": ["planted.png"]},
                                        "frames": [], "width": target.raw["width"],
                                        "height": target.raw["height"],
                                        "code": target.raw["code"]}
                           for target in truth.targets}}), encoding="utf-8")
        art_lane._IDENTITY_CACHE.clear()
        landed = lane.walker.walk(source, None, with_identities=False,
                                  identities=art_lane._identity_table(right))
        self.assertEqual(landed["totals"]["confirmed"], len(truth.targets))
        art_lane._IDENTITY_CACHE.clear()


class BothGsModesAreNamed(unittest.TestCase):
    """An 8-bit image is offered under PSMT8 *and* PSMT8H, because the dump shows both."""

    def test_the_lane_derives_a_name_for_each_mode(self) -> None:
        tag, body = containers.synthetic_indexed_image(64, 32, seed=2, tag="both")
        bank = ea_shps.parse(containers.synthetic_bank([(tag, body)]), "synthetic.ssh")
        names, note = art_lane._identities(bank, bank.image(0))
        self.assertEqual(note, "")
        modes = {pcsx2_texture_name.parse_name(name).psm
                 for values in names.values() for name in values}
        self.assertEqual(modes, {pcsx2_texture_name.PSMT8, pcsx2_texture_name.PSMT8H})
        # The two modes hash different streams, so they are different names for
        # one texture -- not the same name twice.
        by_mode = {}
        for name in names["modern"]:
            parsed = pcsx2_texture_name.parse_name(name)
            by_mode.setdefault(parsed.psm, set()).add(parsed.tex0)
        self.assertEqual(len(by_mode[pcsx2_texture_name.PSMT8]
                             & by_mode[pcsx2_texture_name.PSMT8H]), 0)


class TheToolProvesItself(unittest.TestCase):
    def test_selftest(self) -> None:
        self.assertEqual(identities.selftest(), 0)

    def test_the_dump_scanner_refuses_a_directory_that_is_not_one(self) -> None:
        with self.assertRaises(identities.IdentityError):
            identities.scan_dump(Path(__file__))


class TheMeasuredDocuments(unittest.TestCase):
    """The shipped tables have to agree with themselves."""

    def setUp(self) -> None:
        self.folder = ROOT / art_lane.IDENTITY_DOCUMENT.parent
        if not (ROOT / art_lane.IDENTITY_DOCUMENT).exists():
            self.skipTest("no identity table is shipped yet")
        self.document = json.loads((ROOT / art_lane.IDENTITY_DOCUMENT).read_text(encoding="utf-8"))

    def test_the_identity_table_is_consistent_and_grammatical(self) -> None:
        self.assertEqual(self.document["schema"], art_lane.IDENTITY_SCHEMA)
        counts = self.document["counts"]
        self.assertEqual(counts["disc_images_confirmed"], len(self.document["identities"]))
        for key, entry in self.document["identities"].items():
            self.assertEqual(key, f"{entry['archive']}:{entry['entry']}:{entry['image']}")
            self.assertTrue(entry["names"])
            for convention, filenames in entry["names"].items():
                self.assertIn(convention, (pcsx2_texture_name.CONVENTION_MODERN,
                                           pcsx2_texture_name.CONVENTION_CLASSIC))
                for name in filenames:
                    parsed = pcsx2_texture_name.parse_name(name)
                    self.assertEqual((parsed.width, parsed.height),
                                     (entry["width"], entry["height"]))
        # Every archive the coverage table counts confirms no more than it lists.
        for archive, row in self.document["coverage_by_archive"].items():
            self.assertLessEqual(row["confirmed"], row["listed"], archive)
            self.assertLessEqual(row["named"], row["listed"], archive)
        self.assertEqual(sum(row["confirmed"] for row in
                             self.document["coverage_by_archive"].values()),
                         counts["disc_images_confirmed"])

    def test_the_lane_loads_what_the_tool_wrote(self) -> None:
        loaded = art_lane.load_identities()
        self.assertEqual(len(loaded), len(self.document["identities"]))
        key = sorted(loaded)[0]
        self.assertEqual(loaded[key], self.document["identities"][key]["names"])

    def test_the_derivation_census_adds_up(self) -> None:
        path = self.folder / identities.DERIVATION_DOCUMENT
        if not path.exists():
            self.skipTest("no derivation census is shipped yet")
        census = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(census["schema"], identities.DERIVATION_SCHEMA)
        self.assertEqual(census["derived_name_is_the_confirmed_name"]
                         + census["derived_but_a_different_name"]
                         + census["no_name_derived_for_the_disc_image"],
                         census["confirmed_names_checked"])
        totals = {"agree": 0, "disagree": 0, "no name derived": 0}
        for row in census["by_psm"].values():
            for field in totals:
                totals[field] += row[field]
        self.assertEqual(totals["agree"], census["derived_name_is_the_confirmed_name"])
        self.assertEqual(totals["disagree"], census["derived_but_a_different_name"])

    def test_the_block_codec_verdict_names_its_tests(self) -> None:
        path = self.folder / identities.BLOCK_DOCUMENT
        if not path.exists():
            self.skipTest("no block-codec pairing document is shipped yet")
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], identities.BLOCK_SCHEMA)
        self.assertEqual(len(document["tests"]), 4)
        self.assertTrue(document["verdict"])
        # Whatever the verdict, it must follow from the tables in the document.
        verdict, _tests = identities.block_codec_verdict(document)
        self.assertEqual(verdict, document["verdict"])


if __name__ == "__main__":
    unittest.main()
