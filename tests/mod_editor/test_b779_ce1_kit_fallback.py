"""b779-ce1: Anniversary moment kits must not stop a build because the user's own artwork made a donor kit unusable
(Coach Edwards' project: "composed kit allocation 10752/2867776 exceeds the largest existing kit" and "clean and mud must
share their indices", both hours into a build). Synthetic packages only: a 'kit package' is 53 ten-byte chunk spans
(kind, video bytes, system bytes, flag), parsed by a stand-in for nfl_txtr.parse_chunks."""
import struct
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl_txtr  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from mod_editor.core import nfl2k5_moment_kits as mk  # noqa: E402

SPAN = 10
VIDEO, SYSTEM = 100, 7


def span(video=VIDEO, system=SYSTEM, flag=0, kind=b"T"):
    return kind + struct.pack("<II", video, system) + bytes([flag])


def package(first=b"U", **chunks):
    """A 53-chunk package: chunk 0 is Unif; ``chunks`` maps 'c<index>' to a span."""
    out = []
    for index in range(53):
        out.append(chunks.get(f"c{index}", span(kind=first if index == 0 else b"T")))
    return b"".join(out)


def parse(raw):
    rows = []
    for index in range(len(raw) // SPAN):
        at = index * SPAN
        kind = {b"U": "Unif", b"T": "TSET"}[raw[at:at + 1]]
        video, system = struct.unpack_from("<II", raw, at + 1)
        rows.append(types.SimpleNamespace(index=index, kind=kind, offset=at, end_offset=at + SPAN,
                                          video_bytes=video, system_bytes=system))
    return rows


def unshared(span_bytes, kind):
    if span_bytes[9]:
        raise ValueError("2026 kit fixes: clean and mud must share their indices")
    return None, None, None


def swap_colours(span_bytes, row):
    if span_bytes[9]:
        raise ValueError("2026 kit fixes: clean and mud must share their indices")
    return span_bytes[:9] + b"\x09"


class Harness(unittest.TestCase):
    def setUp(self):
        limits = 53 * VIDEO
        patches = [mock.patch.object(nfl_txtr, "parse_chunks", parse),
                   mock.patch.object(mk, "MAX_VIDEO_BYTES", limits),
                   mock.patch.object(mk, "MAX_SYSTEM_BYTES", 53 * SYSTEM),
                   mock.patch.object(fixes, "native_textures", unshared),
                   mock.patch.object(mk, "palette_map", swap_colours)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.retail = {"18A0": package(), "18A8": package()}
        self.side = {"base": "18A8", "chunks": {"4": "18A0", "13-14": "18A0"}}

    def donors(self, **override):
        out = dict(self.retail)
        out.update(override)
        return out


class Allocation(Harness):
    def test_an_unmodified_donor_composes_without_a_note(self):
        report = []
        out = mk.compose_side(self.side, self.donors(), self.retail, report, "K1 A")
        self.assertEqual(len(out), 53 * SPAN)
        self.assertEqual(report, [])

    def test_a_grown_donor_chunk_stops_the_build_as_before_without_retail(self):
        grown = package(c4=span(video=VIDEO + 1))
        with self.assertRaisesRegex(ValueError, "exceeds the largest existing kit"):
            mk.compose_side(self.side, self.donors(**{"18A0": grown}))

    def test_a_grown_donor_chunk_takes_the_retail_chunk_and_is_named(self):
        grown = package(c4=span(video=VIDEO + 500), c13=span(flag=5))
        report = []
        out = mk.compose_side(self.side, self.donors(**{"18A0": grown}), self.retail, report, "K1 NYG A")
        got = parse(out)
        self.assertEqual(got[4].video_bytes, VIDEO)                 # the retail sock chunk
        self.assertEqual(out[13 * SPAN:14 * SPAN], span(flag=5))     # the user's other chunk is kept
        self.assertEqual(len(report), 1)
        self.assertEqual(report[0]["chunks"], [4])
        self.assertEqual(report[0]["side"], "K1 NYG A")
        self.assertEqual(report[0]["from_kits"], ["18A0"])

    def test_the_donor_itself_is_never_changed(self):
        grown = package(c4=span(video=VIDEO + 500))
        packages = self.donors(**{"18A0": grown})
        mk.compose_side(self.side, packages, self.retail, [], "K1 A")
        self.assertEqual(packages["18A0"], grown)

    def test_compose_sums_to_the_kit_limit_not_chunk_by_chunk(self):
        # two chunks each fit alone but the kit as a whole is over: both grown chunks are swapped
        grown = package(c4=span(video=VIDEO + 30), c13=span(video=VIDEO + 30))
        mk_limit = 53 * VIDEO + 59
        with mock.patch.object(mk, "MAX_VIDEO_BYTES", mk_limit):
            with self.assertRaises(ValueError):
                mk.compose_side(self.side, self.donors(**{"18A0": grown}))
            report = []
            mk.compose_side(self.side, self.donors(**{"18A0": grown}), self.retail, report, "K1 A")
        self.assertEqual(report[0]["chunks"], [4, 13])


class CleanAndMud(Harness):
    def setUp(self):
        super().setUp()
        self.side = {"base": "18A8", "chunks": {"4": "18A0"}, "art": [
            {"chunk": 4, "kind": "palette_map", "texture_kind": "tset", "map": []}]}

    def test_a_chunk_whose_clean_and_mud_no_longer_share_indices_takes_the_retail_chunk(self):
        own_sock = package(c4=span(flag=1))
        with self.assertRaisesRegex(ValueError, "clean and mud"):
            mk.compose_side(self.side, self.donors(**{"18A0": own_sock}))
        report = []
        out = mk.compose_side(self.side, self.donors(**{"18A0": own_sock}), self.retail, report, "K1 A")
        self.assertEqual(out[4 * SPAN + 9:5 * SPAN], b"\x09")        # recoloured from the retail chunk
        self.assertEqual(report[0]["chunks"], [4])
        self.assertIn("clean and mud", report[0]["reason"])

    def test_a_retail_chunk_that_still_cannot_compose_leaves_the_error(self):
        broken = package(c4=span(flag=1))
        retail = dict(self.retail, **{"18A0": broken})
        with self.assertRaisesRegex(ValueError, "clean and mud"):
            mk.compose_side(self.side, self.donors(**{"18A0": broken}), retail, [], "K1 A")


class WholeKit(Harness):
    def doc(self):
        kit = lambda i, base: {"id": i, "team": "NYG", "code": "18", "style": 9 if i == "K1" else 10,
                               "sides": {"H": {"base": base}, "A": {"base": base}}}
        return {"kits": [kit("K1", "18A8"), kit("K2", "18A0")],
                "selections": [{"row": 1, "side": "away", "kit": "K1", "style": 9, "before": 0, "file": "x"},
                               {"row": 2, "side": "away", "kit": "K2", "style": 10, "before": 0, "file": "x"},
                               {"row": 3, "side": "home", "reuse": "18A0", "style": 0, "before": 1, "file": "x"}]}

    def test_a_kit_that_cannot_compose_even_with_retail_chunks_is_left_out_by_name(self):
        packages = self.donors(**{"18A8": package(c0=span(kind=b"T"))})        # chunk 0 is not Unif: not a kit package
        skipped = {}
        out = mk.compose(self.doc(), packages, self.retail, [], skipped)
        self.assertEqual(sorted(skipped), ["K1"])
        self.assertIn("not a kit package", skipped["K1"])
        self.assertEqual(sorted(out), ["18a10.iff", "18h10.iff"])

    def test_without_the_skipped_dict_the_refusal_still_propagates(self):
        packages = self.donors(**{"18A8": package(c0=span(kind=b"T"))})
        with self.assertRaisesRegex(ValueError, "not a kit package"):
            mk.compose(self.doc(), packages)

    def test_a_left_out_kit_takes_its_selections_with_it_and_nothing_else(self):
        doc = self.doc()
        live = mk.without_kits(doc, {"K1": "why"})
        self.assertEqual([k["id"] for k in live["kits"]], ["K2"])
        self.assertEqual([s["row"] for s in live["selections"]], [2, 3])
        self.assertIs(mk.without_kits(doc, {}), doc)
        self.assertEqual(len(doc["kits"]), 2)                       # the shipped document is untouched

    def test_user_notes_name_every_swap_and_every_left_out_kit(self):
        receipt = dict(substitutions=[dict(side="K1 NYG A", reason="Anniversary moment kits: composed kit allocation "
                                           "10752/2867776 exceeds the largest existing kit",
                                           chunks=[4, 8], from_kits=["18A0"])],
                       skipped_kits={"K7": "Anniversary moment kits: not a kit package"})
        notes = mk.user_notes(receipt)
        self.assertEqual(len(notes), 2)
        self.assertIn("K1 NYG A", notes[0])
        self.assertIn("18A0", notes[0])
        self.assertIn("socks and shoes", notes[0])
        self.assertIn("chunks 4, 8", notes[0])
        self.assertIn("kit K7 was left out", notes[1])
        self.assertTrue(notes[0].startswith("Anniversary moment kits: "))
        self.assertTrue(mk.user_notes(receipt, "Classic teams' kits")[1].startswith("Classic teams' kits: "))
        self.assertNotIn("—", "".join(notes))                  # no em dashes in user-facing text


class Policy(Harness):
    """Which stage may leave a kit out, and that the build says so."""

    def inputs(self, **extra):
        broken = self.donors(**{"18A8": package(c0=span(kind=b"T"))})
        retail = mk.RetailPackages("unused")
        retail.update(self.retail)
        return dict(packages=broken, retail=retail, **extra)

    def doc(self):
        return {"kits": [{"id": "K1", "team": "NYG", "code": "18", "style": 9,
                          "sides": {"H": {"base": "18A8"}, "A": {"base": "18A8"}}}], "selections": []}

    def test_the_classic_teams_kit_is_never_left_out(self):
        inputs = self.inputs(allow_skip=False)
        with self.assertRaisesRegex(ValueError, "not a kit package"):
            mk.expected(self.doc(), dict(inputs, main=b"", files={}, situ=b"", members={}))

    def test_the_build_names_the_swaps_of_both_stages(self):
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertIn('for note in kits_receipt.get("user_notes", ()):', text)
        self.assertIn('for note in (classic_receipt.get("authored_kits") or {}).get("user_notes", ()):', text)
        classic = (ROOT / "mod_editor/core/nfl2k5_classic_teams.py").read_text(encoding="utf-8")
        self.assertEqual(classic.count("allow_skip=False"), 3)


class Pinned(unittest.TestCase):
    def test_shipped_donors_keep_the_strict_compose(self):
        with mock.patch.object(mk, "pins", return_value={"donors": {"18A0": mk.sha(b"x")}}):
            self.assertTrue(mk._donors_pinned({"18A0": b"x"}))
            self.assertFalse(mk._donors_pinned({"18A0": b"y"}))
            self.assertFalse(mk._donors_pinned({"18A0": b"x", "07A0": b"x"}))
            self.assertFalse(mk._donors_pinned({}))
        with mock.patch.object(mk, "pins", side_effect=ValueError("moment kit data changed after the pins")):
            self.assertFalse(mk._donors_pinned({"18A0": b"x"}))


class ClassicHelperPage(unittest.TestCase):
    """Coach Edwards' next refusal after the kits: "the classic helper page is not executable". The classic teams' helpers
    are x86 bytes in the read-only run, which was executable only when some other owner already made it so."""

    def test_the_read_only_run_is_executable_when_the_classic_teams_are_requested(self):
        from mod_editor.core import nfl2k5_classic_teams as classic
        from mod_editor.core import nfl2k5_xbe_space as space
        plain = [("nfl2k5_test_owner", "read_only", 16, 16)]
        self.assertEqual(space._scale_regions(plain)[5]["flags"], 0x32)
        self.assertEqual(space._scale_regions(plain + list(classic.REQUESTS))[5]["flags"], 0x36)

    def test_a_run_that_was_already_executable_keeps_its_flags(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        directory_code = [r for r in space.DIRECTORY_CODE_REQUESTS][:1]
        self.assertEqual(space._scale_regions(directory_code)[5]["flags"], 0x36)
        self.assertEqual(space.EXECUTABLE_READ_ONLY_OWNERS, ("nfl2k5_classic_teams",))


class MomentCoachIdentity(unittest.TestCase):
    """The end-of-build refusal after the classic teams: "coach catalog does not match this physical moment" for a project
    that ticks the 25 more moments without Named previews (six retail moments keep their retail titles)."""

    RETAIL = Path(__import__("os").environ.get("NFL2K5_RETAIL_XISO",
                                                "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))

    def situ(self, named):
        if not self.RETAIL.is_file():
            self.skipTest("the retail disc is not available")
        from mod_editor.core import nfl2k5_espn25_more_moments as more
        from mod_editor.core import nfl2k5_historic_styles as hs
        from mod_editor.core import nfl2k5_music_archive as archive
        with archive.Disc(self.RETAIL, descriptors=()) as disc:
            target = hs.Target(disc)
            collection, main = target.get(identity=hs.SITU_OUTER_ID), target.get(identity=hs.ROSTER_OUTER_ID)
        return more.compile_situ(collection, more.Data.load(), main, named=named)

    def test_the_catalog_matches_the_moments_with_and_without_named_previews(self):
        from mod_editor.core import nfl2k5_moment_coaches as coaches
        for named in (False, True):
            rebuilt = coaches.situation(self.situ(named), stats={})
            self.assertEqual(rebuilt[:4], b"SITU")

    def test_a_different_moment_is_still_refused(self):
        from mod_editor.core import nfl2k5_moment_coaches as coaches
        from mod_editor.core import nfl2k5_espn25_scenarios as sc
        raw = bytearray(self.situ(False))
        at = 32 + sc.RECORDS + 12 * sc.STRIDE
        # the row's date pointer now reads its title text: not this moment
        title = struct.unpack_from("<i", raw, at)[0]
        struct.pack_into("<i", raw, at + 12, title - 12)
        with self.assertRaisesRegex(ValueError, "does not match this physical moment"):
            coaches.situation(bytes(raw), stats={})


class Installed(Harness):
    """A disc where one kit was left out earlier reads as installed, not foreign."""

    def test_an_absent_kit_that_cannot_compose_is_read_as_left_out(self):
        from mod_editor.core import nfl2k5_historic_styles as hs
        doc = WholeKit.doc(self)
        for kit in doc["kits"]:
            kit["cards"] = {}
        broken = self.donors(**{"18A8": package(c0=span(kind=b"T"))})
        situ = b"situ"
        inputs = dict(packages=broken, retail=mk.RetailPackages("unused"), situ=situ, members={}, skipped={},
                      new_present={"18h9.iff": False, "18a9.iff": False, "18h10.iff": True, "18a10.iff": True})
        inputs["retail"].update(self.retail)
        fields = {(1, "away"): (0, 0), (2, "away"): (10, 0), (3, "home"): (1, 0)}
        with mock.patch.object(mk, "_situ_fields", return_value=fields), \
                mock.patch.object(mk, "card_sources", return_value={}):
            live = mk._installed_document(doc, inputs)
        self.assertEqual([k["id"] for k in live["kits"]], ["K2"])
        self.assertEqual(sorted(inputs["skipped"]), ["K1"])

    def test_an_absent_kit_that_could_compose_is_a_partial_install(self):
        doc = WholeKit.doc(self)
        inputs = dict(packages=self.donors(), retail=mk.RetailPackages("unused"), situ=b"s", members={}, skipped={},
                      new_present={"18h9.iff": False, "18a9.iff": False, "18h10.iff": True, "18a10.iff": True})
        inputs["retail"].update(self.retail)
        fields = {(1, "away"): (0, 0), (2, "away"): (10, 0), (3, "home"): (1, 0)}
        with mock.patch.object(mk, "_situ_fields", return_value=fields), \
                mock.patch.object(mk, "card_sources", return_value={}):
            live = mk._installed_document(doc, inputs)
        self.assertIs(live, doc)


if __name__ == "__main__":
    unittest.main()
