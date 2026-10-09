"""b77 e4: Modern stadium boards no longer fail a whole build for one stadium they cannot use.

Coach Edwards' photo (4 October 2026): after a build that ran for hours, the boards step refused the whole disc with
"the modern stadium boards need retail stadium scenes or the 2026 venue art's (found s13ad.iff foreign, ...)". The early
source check had passed, so something earlier in the same build had changed Kansas City's stadium scenes: Modern
Arrowhead rewrites all nine s13 bundles and the kit did not know it. These tests pin the fix:

* a stadium the kit cannot build on is kept exactly as it is, named, and the others still get their boards;
* Modern Arrowhead's Kansas City is recognised as its owner's work (state "arrowhead"), by bytes and by the build plan;
* every published SOFTDRINK 2K28 pack's stadium scenes are known by hash, so nothing published reads as foreign;
* the words say what happened (no dangling "venue art's").

The data-free tests run anywhere; the byte tests need the hydrated retail archive (``extracted/``) like the rest of
the board kit's tests.
"""
import contextlib
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(Path(__file__).parent)]

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_board_kit as bk  # noqa: E402
from mod_editor.core import nfl2k5_scne_builder as sb  # noqa: E402
from mod_editor.core.build_feedback import completion  # noqa: E402

EXTRACTED = ROOT / "extracted" / "ESPN NFL 2K5 (USA)"
VENUES = bk.pinned_venues()
SHA = re.compile(r"^[0-9a-f]{64}$")
PUBLISHED = tuple(f"SOFTDRINK 2K28 v0.{n}" for n in range(1, 6))


def states(**by_venue):
    """{bundle: state} for every kit bundle; ``sNN="state"`` sets a whole venue, the rest are retail."""
    out = {}
    for venue in VENUES:
        for name in bk.variants(venue):
            out[name] = by_venue.get(venue, "retail")
    return out


class Planner(unittest.TestCase):
    """Which stadiums the kit writes, keeps and leaves alone (no game data)."""

    def check(self, rows, **kwargs):
        with mock.patch.object(bk, "bundle_states", return_value=rows):
            return bk.check_request("source.iso", **kwargs)

    def test_one_foreign_stadium_no_longer_fails_the_build(self):
        # Edwards' disc: Kansas City's nine bundles changed, the other thirteen stadiums retail
        result = self.check(states(s13="foreign"))
        self.assertEqual(result["state"], "partial")
        self.assertEqual([row["venue"] for row in result["skipped"]], ["s13"])
        self.assertIn("Arrowhead Stadium", result["skipped"][0]["stadium"])

    def test_a_stadium_is_kept_or_written_whole_never_by_the_bundle(self):
        rows = states()
        rows["s13dd.iff"] = "foreign"          # one of nine: the whole stadium waits
        plan = bk.plan_venues(rows)
        self.assertEqual(sorted(plan["skip"]), ["s13"])
        self.assertEqual(plan["skip"]["s13"]["bundles"], ["s13dd.iff"])
        self.assertNotIn("s13", plan["write"])
        self.assertEqual(len(plan["write"]), len(VENUES) - 1)

    def test_nothing_usable_still_refuses_and_says_what_to_do(self):
        everything = {name: "foreign" for name in states()}
        with mock.patch.object(bk, "bundle_states", return_value=everything), \
                self.assertRaisesRegex(sb.ScneBuildError,
                                       r"s02ad.iff.*unmodified USA retail image.*turn off Modern stadium boards") as caught:
            bk.check_request("source.iso")
        self.assertNotIn("venue art's", str(caught.exception))
        self.assertNotIn("\n", str(caught.exception).split("unmodified")[0])

    def test_applied_and_retail_stadiums_mix_and_finish_the_job(self):
        plan = bk.plan_venues(states(s02="applied", s04="applied"))
        self.assertEqual(plan["keep"], ["s02", "s04"])
        self.assertEqual(len(plan["write"]), len(VENUES) - 2)
        self.assertEqual(plan["skip"], {})
        self.assertEqual(self.check(states(s02="applied"))["state"], "partial")

    def test_venue_art_repaint_counts_as_retail_and_all_applied_is_applied(self):
        self.assertEqual(self.check(states(**{v: "venues" for v in VENUES})), {"state": "retail"})
        self.assertEqual(self.check(states(**{v: "applied" for v in VENUES})), {"state": "applied"})

    def test_modern_arrowhead_in_this_build_owns_kansas_city_even_while_it_is_retail(self):
        result = self.check(states(), owned={"s13": "Modern Arrowhead"})
        self.assertEqual(result["state"], "partial")
        row = result["skipped"][0]
        self.assertEqual((row["venue"], row["kind"], row["by"]), ("s13", "owned", "Modern Arrowhead"))

    def test_modern_arrowhead_found_in_the_bytes_owns_kansas_city_too(self):
        plan = bk.plan_venues(states(s13="arrowhead"))
        self.assertEqual(plan["skip"]["s13"]["kind"], "owned")
        self.assertEqual(plan["skip"]["s13"]["by"], "Modern Arrowhead")
        self.assertEqual(len(plan["write"]), len(VENUES) - 1)

    def test_an_unknown_state_is_never_written(self):
        rows = states()
        rows["s02dd.iff"] = "something new"
        self.assertEqual(sorted(bk.plan_venues(rows)["skip"]), ["s02"])

    def test_image_report_reads_the_four_states_the_build_page_knows(self):
        def state(rows, **kw):
            with mock.patch.object(bk, "bundle_states", return_value=rows):
                return bk.image_report("source.iso", **kw)["state"]
        self.assertEqual(state(states()), "retail")
        self.assertEqual(state(states(**{v: "applied" for v in VENUES})), "applied")
        self.assertEqual(state(states(s13="foreign")), "partial")            # boards still possible elsewhere
        self.assertEqual(state(states(s02="applied")), "partial")
        # a finished build that skipped Kansas City: everything the kit can do is done
        done = states(**{v: "applied" for v in VENUES})
        done.update({name: "arrowhead" for name in bk.variants("s13")})
        self.assertEqual(state(done), "applied")
        self.assertEqual(state({name: "foreign" for name in states()}), "foreign")
        self.assertEqual(state({}), "retail")

    def test_notes_name_each_skipped_stadium_and_are_silent_when_nothing_was_skipped(self):
        self.assertEqual(bk.skip_notes(bk.plan_venues(states())), [])
        notes = bk.skip_notes(bk.plan_venues(states(s13="arrowhead", s02="foreign")))
        text = "\n".join(notes)
        self.assertIn("12 of 14", text)
        self.assertIn("Arrowhead Stadium", text)
        self.assertIn("Modern Arrowhead", text)
        self.assertIn("M&T Bank Stadium", text)
        self.assertNotIn("venue art's", text)

    def test_a_brief_reading_stops_a_stadium_at_its_first_changed_bundle(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        seen = []

        def state(_archive, name, _receipt=None, _colour=None):
            seen.append(name)
            return "foreign" if name == "s13dr.iff" else "retail"

        opener = mock.MagicMock()
        with mock.patch.object(bk, "bundle_state", side_effect=state), \
                mock.patch.object(bk, "_venues_receipt", return_value=None), \
                mock.patch.object(bk, "_mv", return_value=mock.Mock(_colour_receipt=lambda source: None)), \
                mock.patch.object(ml, "_outer_image", return_value=opener):
            full = bk.bundle_states("source.iso")
            full_calls = len(seen)
            del seen[:]
            brief = bk.bundle_states("source.iso", brief=True)
        self.assertEqual(full_calls, len(VENUES) * 9)
        self.assertEqual(len(full), len(VENUES) * 9)
        self.assertEqual(len(seen), len(VENUES) * 9 - 7)                 # Kansas City stopped after dd and dr
        self.assertEqual([n for n in brief if n.startswith("s13")], ["s13dd.iff", "s13dr.iff"])
        self.assertEqual(bk.plan_venues(brief)["skip"]["s13"]["bundles"], ["s13dr.iff"])

    def test_an_image_that_already_carries_every_board_is_reported_not_crashed_on(self):
        """The old branch did dict(state="already_applied", **verify(...)): verify has a state too, so it raised
        TypeError after the whole build, for a SOFTDRINK disc or any finished build used as the source."""
        everything = states(**{v: "applied" for v in VENUES})
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(bk, "bundle_states", return_value=everything):
            result = bk.apply_to_image(str(Path(folder) / "output.iso"))
        self.assertEqual(result["state"], "already_applied")
        self.assertEqual(result["venues_kept"], list(VENUES))
        self.assertEqual((result["venues_written"], result["skipped"], result["user_notes"]), ([], [], []))

    def test_no_message_leaves_a_dangling_possessive(self):
        source = (ROOT / "mod_editor" / "core" / "nfl2k5_board_kit.py").read_text(encoding="utf-8")
        self.assertNotIn("2026 venue art's (found", source)
        self.assertNotIn("venue art's", source.split("def _nothing_to_build_on", 1)[1].split("\n\n\n", 1)[0])


class PublishedPacks(unittest.TestCase):
    """The published SOFTDRINK 2K28 packs (v0.1 to v0.5) are known by the hash of each stadium scene."""

    def test_every_pin_row_lists_every_published_pack_with_well_formed_hashes(self):
        for venue in VENUES:
            for row in bk.model_pins(venue)["bundles"]:
                published = row.get("published")
                self.assertTrue(published, row["name"])
                labels = set()
                for digest, names in published.items():
                    self.assertRegex(digest, SHA, row["name"])
                    self.assertNotIn(digest, (row["retail_sha256"], row["model_sha256"]), row["name"])
                    self.assertEqual(names, sorted(names), row["name"])
                    labels.update(names)
                self.assertEqual(labels, set(PUBLISHED), row["name"])

    def test_published_spans_are_recognised_without_parsing_the_scene(self):
        data = b"a published pack's stadium scene"
        pin = {"size": len(data), "offset": 0, "length": len(data), "model_sha256": "model", "retail_sha256": "retail",
               "published": {hashlib.sha256(data).hexdigest(): ["SOFTDRINK 2K28 v0.4"]}}
        archive = mock.Mock()
        archive.read.return_value = data
        with mock.patch.object(bk, "_pin", return_value=pin), \
                mock.patch.object(bk, "_venue_pins", return_value={"s13dd.iff": {}}), \
                mock.patch.object(bk, "_entry", return_value=mock.Mock(size=len(data), virtual_offset=0)), \
                mock.patch.object(bk, "_renovated", side_effect=AssertionError("the scene was parsed")):
            self.assertEqual(bk.bundle_state(archive, "s13dd.iff"), "applied")
            self.assertEqual(bk.published_spans("s13dd.iff"), pin["published"])

    def test_a_scene_that_matches_nothing_is_still_foreign(self):
        data = b"somebody else's stadium scene"
        pin = {"size": len(data), "offset": 0, "length": len(data), "model_sha256": "model", "retail_sha256": "retail",
               "published": {"0" * 64: ["SOFTDRINK 2K28 v0.4"]}}
        archive = mock.Mock()
        archive.read.return_value = data
        with mock.patch.object(bk, "_pin", return_value=pin), \
                mock.patch.object(bk, "_venue_pins", return_value={"s13dd.iff": {}}), \
                mock.patch.object(bk, "_entry", return_value=mock.Mock(size=len(data), virtual_offset=0)), \
                mock.patch.object(bk, "_renovated", return_value=False), \
                mock.patch.object(bk, "_arrowhead_owns", return_value=False):
            self.assertEqual(bk.bundle_state(archive, "s13dd.iff"), "foreign")

    def test_arrowhead_owned_bytes_read_as_arrowhead_not_foreign(self):
        data = b"modern arrowhead's kansas city"
        pin = {"size": len(data), "offset": 0, "length": len(data), "model_sha256": "model", "retail_sha256": "retail"}
        archive = mock.Mock()
        archive.read.return_value = data
        with mock.patch.object(bk, "_pin", return_value=pin), \
                mock.patch.object(bk, "_venue_pins", return_value={"s13dd.iff": {}}), \
                mock.patch.object(bk, "_entry", return_value=mock.Mock(size=len(data), virtual_offset=0)), \
                mock.patch.object(bk, "_renovated", return_value=False), \
                mock.patch.object(bk, "_arrowhead_owns", return_value=True):
            self.assertEqual(bk.bundle_state(archive, "s13dd.iff"), "arrowhead")
        self.assertFalse(bk._arrowhead_owns(archive, "s02dd.iff", None))     # only Kansas City can be Arrowhead's


class Recorder(unittest.TestCase):
    """tools/b77/e4s_record_published.py writes the pins deterministically (the reading is proved by the real packs)."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("e4s_record_published", ROOT / "tools" / "b77" / "e4s_record_published.py")
        cls.tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tool)

    def copy_pins(self, folder):
        import shutil
        for venue in VENUES:
            shutil.copy(bk.PINS_DIR / f"{venue}.json", Path(folder) / f"{venue}.json")

    def test_write_pins_merges_pack_labels_keeps_only_scenes_with_boards_and_is_idempotent(self):
        one, two = "1" * 64, "2" * 64
        labels = {"SOFTDRINK 2K28 v9.1": {"s02dd.iff": (one, True), "s02dr.iff": (two, False)},
                  "SOFTDRINK 2K28 v9.2": {"s02dd.iff": (one, True), "s02ds.iff": (two, True)}}
        sources = {"SOFTDRINK 2K28 v9.1": {"pack": {"kind": "pack", "pack_sha256": "a" * 64}, "disc": {"kind": "disc", "size": 1}},
                   "SOFTDRINK 2K28 v9.2": {"disc": {"kind": "disc", "size": 2}}}
        with tempfile.TemporaryDirectory() as folder:
            self.copy_pins(folder)
            self.tool.write_pins(labels, sources, folder)
            first = {p.name: p.read_bytes() for p in Path(folder).glob("*.json")}
            self.tool.write_pins(labels, sources, folder)
            self.assertEqual({p.name: p.read_bytes() for p in Path(folder).glob("*.json")}, first)
            doc = json.loads(first["s02.json"].decode("utf-8"))
            self.assertEqual(first["s02.json"].decode("utf-8"), json.dumps(doc, indent=2, sort_keys=True) + "\n")
            rows = {r["name"]: r for r in doc["bundles"]}
            self.assertEqual(rows["s02dd.iff"]["published"][one], ["SOFTDRINK 2K28 v9.1", "SOFTDRINK 2K28 v9.2"])
            self.assertEqual(rows["s02ds.iff"]["published"][two], ["SOFTDRINK 2K28 v9.2"])
            self.assertNotIn(two, rows["s02dr.iff"].get("published", {}))      # no boards by structure: never kept
            self.assertEqual(doc["published_from"]["SOFTDRINK 2K28 v9.1"], {"pack_sha256": "a" * 64})
            self.assertEqual(doc["published_from"]["SOFTDRINK 2K28 v9.2"], {"size": 2})
            self.assertNotIn(b"\r", first["s02.json"])

    def test_the_tool_names_every_bundle_the_kit_renovates(self):
        wanted = self.tool.kit_bundles()
        self.assertEqual(len(wanted), len(VENUES) * 9)
        self.assertEqual({name[:3] for name in wanted}, set(VENUES))


class BuildWiring(unittest.TestCase):
    """mod_build hands the kit the build plan and tells the person what the kit left alone."""

    def test_the_early_check_passes_ownership_only_when_modern_arrowhead_is_on(self):
        boards = mock.Mock()
        boards.check_request.return_value = {"state": "retail"}
        with tempfile.TemporaryDirectory() as td, mock.patch.object(mod_build, "_core_module", return_value=boards), \
                mock.patch.object(mod_build.tt, "is_disc_image", return_value=True):
            source = str(Path(td) / "source.iso")
            mod_build.preflight_board_source(mod_build.BuildPlan(source, "out.iso", modern_board_kit=True))
            boards.check_request.assert_called_once_with(Path(source))
            boards.check_request.reset_mock()
            mod_build.preflight_board_source(
                mod_build.BuildPlan(source, "out.iso", modern_board_kit=True, modern_arrowhead=True))
            boards.check_request.assert_called_once_with(Path(source), owned={"s13": "Modern Arrowhead"})

    def test_the_early_check_says_which_stadiums_will_be_left_alone(self):
        boards = mock.Mock()
        boards.check_request.return_value = {"state": "partial", "skipped": [
            {"venue": "s13", "stadium": "Arrowhead Stadium (KC)", "kind": "owned", "by": "Modern Arrowhead"}]}
        said = []
        with mock.patch.object(mod_build, "_core_module", return_value=boards), \
                mock.patch.object(mod_build.tt, "is_disc_image", return_value=True):
            mod_build.preflight_board_source(
                mod_build.BuildPlan("source.iso", "out.iso", modern_board_kit=True, modern_arrowhead=True),
                lambda message, done, total: said.append(message))
        self.assertTrue(any("Arrowhead Stadium (KC)" in line and "left" in line for line in said), said)

    def test_the_finished_disc_message_carries_the_boards_notes_and_only_then(self):
        plain = {"outcome": {"status": "changed", "message": "The copy differs."}, "steps": [{"step": "modern_board_kit"}]}
        self.assertEqual(completion(plain), ("Disc ready", "The copy differs."))
        noted = {"outcome": {"status": "changed", "message": "The copy differs."},
                 "steps": [{"step": "modern_board_kit", "user_notes": ["Modern stadium boards: 13 of 14 stadiums have them.",
                                                                       "Arrowhead Stadium (KC): kept."]}]}
        title, message = completion(noted)
        self.assertEqual(title, "Disc ready")
        self.assertIn("13 of 14", message)
        self.assertIn("Arrowhead Stadium (KC): kept.", message)

    def test_the_board_kit_build_step_receives_the_plan_ownership(self):
        source = (ROOT / "mod_editor" / "core" / "mod_build.py").read_text(encoding="utf-8")
        self.assertIn("board_kit.apply_to_image(target, progress=progress, **_board_kit_options(plan))", source)
        self.assertIn("board_kit.check_request(source, **_board_kit_options(plan))", source)
        self.assertEqual(mod_build._board_kit_options(mod_build.BuildPlan("s", "t")), {})
        self.assertEqual(mod_build._board_kit_options(mod_build.BuildPlan("s", "t", modern_arrowhead=True)),
                         {"owned": {"s13": "Modern Arrowhead"}})


class BuildPageStates(unittest.TestCase):
    """The Build page enables the boards for a partial image and names the stadiums that stay as they are."""

    @classmethod
    def setUpClass(cls):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication
            from mod_editor.gui.build_panel_qt import BuildPanel
        except ImportError as exc:  # pragma: no cover - the Studio's GUI needs PyQt5
            raise unittest.SkipTest(f"needs PyQt5: {exc}")
        cls.app = QApplication.instance() or QApplication([])
        cls.BuildPanel = BuildPanel

    def setUp(self):
        self.panel = self.BuildPanel()

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()

    def show(self, state, skips=()):
        reading = dict(path="source.iso", container="xiso", **{k: "retail" for k in self.panel._boxes()})
        reading["modern_board_kit"] = state
        if skips:
            reading["modern_board_kit_skips"] = list(skips)
        self.panel.apply_state(reading)
        return self.panel.modern_board_kit_check, self.panel._badges["modern_board_kit"].text()

    def test_retail_and_partial_images_can_take_the_boards_and_applied_ones_show_it(self):
        box, _badge = self.show("retail")
        self.assertTrue(box.isEnabled() and not box.isChecked())
        box, badge = self.show("partial", ["Arrowhead Stadium (KC)"])
        self.assertTrue(box.isEnabled() and not box.isChecked())
        self.assertIn("leaves Arrowhead Stadium (KC) as it is", badge)
        box, badge = self.show("applied", ["Arrowhead Stadium (KC)"])
        self.assertTrue(box.isChecked() and not box.isEnabled())
        self.assertIn("Already in this source", badge)
        self.assertIn("Arrowhead Stadium (KC)", badge)

    def test_an_image_no_stadium_of_which_can_take_the_boards_stays_off(self):
        box, badge = self.show("foreign")
        self.assertFalse(box.isEnabled() or box.isChecked())
        self.assertIn("Every stadium scene in this image is modified", badge)
        self.assertIn("unmodified USA retail image", badge)

    def test_many_skipped_stadiums_are_counted_not_listed(self):
        _box, badge = self.show("partial", ["A (X)", "B (Y)", "C (Z)"])
        self.assertIn("leaves 3 stadiums as they are", badge)


class _Entry:
    def __init__(self, pin, offset):
        self.virtual_offset, self.size, self.name_id, self.index = offset, pin["size"], pin["name_id"], pin["outer"]


class _Image:
    """Some of the kit's bundles at the outer indexes the 2026 venue table gives them, as one in-memory archive."""

    def __init__(self, bundles):
        pins = {name: bk._venue_pins(name[:3])[name] for name in bundles}
        self.entries = [None] * (max(p["outer"] for p in pins.values()) + 1)
        self.buffer = bytearray()
        for name, data in bundles.items():
            self.entries[pins[name]["outer"]] = _Entry(pins[name], len(self.buffer))
            self.buffer += data

    def read(self, offset, size):
        return bytes(self.buffer[offset:offset + size])

    def write(self, offset, data):
        self.buffer[offset:offset + len(data)] = data
        return len(data)

    def bundle(self, name):
        e = self.entries[bk._venue_pins(name[:3])[name]["outer"]]
        return self.read(e.virtual_offset, e.size)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@unittest.skipUnless(EXTRACTED.is_dir(), "needs the hydrated retail archive")
class RealBytes(unittest.TestCase):
    """Retail Arrowhead Stadium and Empower Field bundles (dry day), with Modern Arrowhead's real output."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_modern_arrowhead as arrowhead
        cls.retail = {"s08dd.iff": bk.read_retail(EXTRACTED, "s08")["s08dd.iff"],
                      "s13dd.iff": bk.read_retail(EXTRACTED, "s13")["s13dd.iff"]}
        cls.arrowhead, _edits = arrowhead.modern_bundle(cls.retail["s13dd.iff"])
        cls.pin13 = bk._venue_pins("s13")["s13dd.iff"]

    def one_bundle_each(self):
        """Patch the kit down to one dry-day bundle in each of two venues."""
        names = {"s08": ("s08dd.iff",), "s13": ("s13dd.iff",)}
        real = bk._venue_pins
        return (mock.patch.object(bk, "pinned_venues", return_value=("s08", "s13")),
                mock.patch.object(bk, "variants", side_effect=lambda venue: names[venue]),
                mock.patch.object(bk, "_venue_pins",
                                  side_effect=lambda venue: {n: real(venue)[n] for n in names[venue]}))

    def image(self, **overrides):
        return _Image({**self.retail, **overrides})

    def build(self, image, **kwargs):
        from mod_editor.core import nfl2k5_modern_metlife as ml
        with contextlib.ExitStack() as stack:
            for patch in self.one_bundle_each():
                stack.enter_context(patch)
            stack.enter_context(mock.patch.object(ml, "_outer_image", return_value=lambda path, writable=False: image))
            folder = stack.enter_context(tempfile.TemporaryDirectory())
            return bk.apply_to_image(str(Path(folder) / "output.iso"), workers=1, **kwargs)

    def test_modern_arrowhead_bytes_read_as_arrowhead_not_foreign(self):
        from mod_editor.core import nfl2k5_modern_metlife as ml  # noqa: F401
        image = self.image(**{"s13dd.iff": self.arrowhead})
        self.assertEqual(bk.bundle_state(image, "s13dd.iff"), "arrowhead")
        self.assertEqual(bk.bundle_state(self.image(), "s13dd.iff"), "retail")

    def test_the_build_step_leaves_modern_arrowheads_stadium_alone_and_boards_the_rest(self):
        """Edwards' disc: this raised "the modern stadium boards need ... (found s13dd.iff foreign)" after the hours."""
        image = self.image(**{"s13dd.iff": self.arrowhead})
        result = self.build(image)
        self.assertEqual(image.bundle("s13dd.iff"), self.arrowhead)               # byte for byte what Arrowhead wrote
        self.assertNotEqual(image.bundle("s08dd.iff"), self.retail["s08dd.iff"])  # the boards went on
        self.assertEqual(len(image.bundle("s08dd.iff")), len(self.retail["s08dd.iff"]))
        self.assertEqual(result["venues_written"], ["s08"])
        self.assertEqual([row["venue"] for row in result["skipped"]], ["s13"])
        self.assertEqual(result["skipped"][0]["by"], "Modern Arrowhead")
        text = "\n".join(result["user_notes"])
        self.assertIn("1 of 2", text)
        self.assertIn("Arrowhead Stadium", text)

    def test_the_plan_alone_is_enough_to_leave_kansas_city_to_modern_arrowhead(self):
        image = self.image()                                                       # Kansas City still retail
        result = self.build(image, owned={"s13": "Modern Arrowhead"})
        self.assertEqual(image.bundle("s13dd.iff"), self.retail["s13dd.iff"])
        self.assertNotEqual(image.bundle("s08dd.iff"), self.retail["s08dd.iff"])
        self.assertEqual([row["venue"] for row in result["skipped"]], ["s13"])

    def test_a_stadium_somebody_else_changed_is_kept_and_named(self):
        scribbled = bytearray(self.retail["s13dd.iff"])
        pin = bk._pin("s13dd.iff")
        scribbled[pin["offset"] + 64:pin["offset"] + 80] = bytes(16)               # a stranger's edit inside the scene
        image = self.image(**{"s13dd.iff": bytes(scribbled)})
        result = self.build(image)
        self.assertEqual(image.bundle("s13dd.iff"), bytes(scribbled))
        self.assertEqual(result["skipped"][0]["kind"], "foreign")
        self.assertIn("s13dd.iff", "\n".join(result["user_notes"]))

    def test_nothing_the_kit_can_use_refuses_with_words_a_person_can_act_on(self):
        scribbled = {}
        for name in ("s08dd.iff", "s13dd.iff"):
            data = bytearray(self.retail[name])
            data[bk._pin(name)["offset"] + 64:bk._pin(name)["offset"] + 80] = bytes(16)
            scribbled[name] = bytes(data)
        with self.assertRaises(sb.ScneBuildError) as caught:
            self.build(self.image(**scribbled))
        message = str(caught.exception)
        for part in ("s08dd.iff", "unmodified USA retail image", "turn off Modern stadium boards"):
            self.assertIn(part, message)
        self.assertNotIn("venue art's", message)
        self.assertEqual(_Image(scribbled).bundle("s08dd.iff"), scribbled["s08dd.iff"])

    def test_a_clean_build_has_nothing_to_report_and_writes_the_pinned_scenes(self):
        image = self.image()
        result = self.build(image)
        self.assertEqual(sorted(result["venues_written"]), ["s08", "s13"])
        self.assertEqual(result["skipped"], [])
        self.assertEqual(result["user_notes"], [])
        for name in ("s08dd.iff", "s13dd.iff"):        # exactly the bytes the build step wrote before this change
            pin = bk._pin(name)
            span = image.bundle(name)[pin["offset"]:pin["offset"] + pin["length"]]
            self.assertEqual(bk.sha(span), pin["model_sha256"], name)

    def test_building_again_on_a_finished_disc_changes_nothing(self):
        image = self.image()
        self.build(image)
        once = bytes(image.buffer)
        result = self.build(image)
        self.assertEqual(bytes(image.buffer), once)
        self.assertEqual(result["state"], "already_applied")


if __name__ == "__main__":
    unittest.main()
