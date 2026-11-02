"""b791-h2-kits: Anniversary moment kits never stop a build (Coach Edwards, 11/02).

Shipped RC114 on a clean retail disc with his 10/27 Build options stopped six minutes in: "Anniversary moment kits:
classic default 9 has no year pair in its team file". Kit K1 (Giants 2007-2011 road) has one art step, which paints
white over the two 2026 maker marks on the sleeve; on a sleeve without those marks it changes nothing and the art
compiler refused ("the art changed no texel"). b779-ce1's fallback then left K1 out together with its moment selections
but kept the classic team defaults that opened on K1's style, and the Giants files could not show style 9.

The synthetic tests use 53 ten-byte chunk spans as kit packages and a one-team ROST with the real record offsets; the
disc tests read the retail disc and the b775 fixture disc (a SOFTDRINK disc whose copy is still untouched by this
stage), both read only, and skip when a disc is absent.
"""
import json
import os
from pathlib import Path
import struct
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import nfl_txtr  # noqa: E402
from mod_editor.core import nfl2k5_historic_styles as hs  # noqa: E402
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402
from mod_editor.core import nfl2k5_moment_kits as mk  # noqa: E402
# The kit stage imports these inside its functions and they bind nfl_txtr.parse_chunks when first imported. Import them
# here, before a test patches parse_chunks with a stand-in, or the stand-in stays bound in them for every later test.
from mod_editor.core import nfl2k5_era_kits  # noqa: E402,F401
from mod_editor.core import nfl2k5_classic_kit_art  # noqa: E402,F401
from mod_editor.core import nfl2k5_classic_art  # noqa: E402,F401

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XISO", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
FIXTURE = Path(os.environ.get("B775_EK1_DISC",
                              "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6.1 i4 test (2026-10-17).xiso.iso"))

SPAN = 10
VIDEO, SYSTEM = 100, 7
MARKS = 1                      # a chunk-3 span whose flag byte is 1 carries "the 2026 maker marks"


def span(video=VIDEO, system=SYSTEM, flag=0, kind=b"T"):
    return kind + struct.pack("<II", video, system) + bytes([flag])


def package(first=b"U", **chunks):
    return b"".join(chunks.get(f"c{i}", span(kind=first if i == 0 else b"T")) for i in range(53))


def parse(raw, allow_trailing=False):
    rows = []
    for index in range(len(raw) // SPAN):
        at = index * SPAN
        kind = {b"U": "Unif", b"T": "TSET"}[raw[at:at + 1]]
        video, system = struct.unpack_from("<II", raw, at + 1)
        rows.append(types.SimpleNamespace(index=index, kind=kind, offset=at, end_offset=at + SPAN,
                                          video_bytes=video, system_bytes=system))
    return rows


def fake_compile_texture(chunk_span, row, donors=None, *, fixed=True):
    """The real compiler's contract for K1's step: a sleeve that carries the marks is repainted, one that does not has
    nothing to change and says so with the typed signal."""
    if chunk_span[9] != MARKS:
        raise fixes.NothingToChange("2026 kit fixes: the art changed no texel")
    return chunk_span[:9] + b"\x00", {}


def fake_palette_map(chunk_span, row):
    if chunk_span[9] == 9:
        raise fixes.NothingToChange(mk.FEATURE + ": the palette map changed nothing")
    return chunk_span[:9] + b"\x07"


def k1():
    return {"id": "K1", "team": "NYG", "code": "18", "style": 9, "label": [2007, 2011],
            "sides": {"H": {"base": "18H8"},
                      "A": {"base": "18A8", "chunks": {"3": "18A0", "4": "18A0"},
                            "art": [{"chunk": 3, "kind": "tset", "texture": "sleeve00", "size": [128, 128, 5],
                                     "note": "remove the two 2026 maker marks above the stripes (2007 sleeves carry none)",
                                     "ops": []}]}},
            "cards": {"H": "18H8", "A": "18A8", "logo": "18H8"}, "moments": [[27, "away"], [29, "away"]]}


def k2():
    return {"id": "K2", "team": "DAL", "code": "07", "style": 10, "label": [1977, 1981],
            "sides": {"H": {"base": "07H3"}, "A": {"base": "07A2"}},
            "cards": {"H": "07H3", "A": "07A2", "logo": "07H3"}, "moments": [[6, "home"]]}


GIANTS_2007, GIANTS_2011, COWBOYS_1977 = ("h-18-2007-giants-9.iff", "h-18-2011-giants-9.iff", "h-07-1977-cowboys-3.iff")


def document():
    return {"schema": mk.SCHEMA, "kits": [k1(), k2()],
            "selections": [
                {"row": 27, "side": "away", "file": GIANTS_2007, "before": 8, "style": 9, "kit": "K1"},
                {"row": 29, "side": "away", "file": GIANTS_2011, "before": 8, "style": 9, "kit": "K1"},
                {"row": 6, "side": "home", "file": COWBOYS_1977, "before": 3, "style": 10, "kit": "K2"}],
            "classic_defaults": [
                {"file": GIANTS_2007, "style": 9, "before": 8, "why": "wears style 9 in row(s) 27 away"},
                {"file": GIANTS_2011, "style": 9, "before": 8, "why": "wears style 9 in row(s) 29 away"},
                {"file": COWBOYS_1977, "style": 10, "before": 3, "why": "wears style 10 in row 6 home"}]}


def team_file(code, listed, default):
    """A one-team ROST at the real offsets: ``listed`` {style: (first, last)} year pairs and the default style byte."""
    body = bytearray(0x400)
    table_at, code_at = 0x100, 0x300
    struct.pack_into("<I", body, 0x40 + 0x18, 1)
    struct.pack_into("<i", body, 0x40 + 0x1C, table_at - (0x40 + 0x1C) + 1)
    struct.pack_into("<i", body, table_at + 0x10C, code_at - (table_at + 0x10C) + 1)
    body[code_at:code_at + 4] = code.encode("utf-16le")
    for style, pair in listed.items():
        struct.pack_into("<HH", body, table_at + hs.TABLE + 4 * (style - 1), *pair)
    body[table_at + hs.STYLE] = default
    return bytes(32) + bytes(body)


def pair_of(raw, style):
    return mk._team_file_pairs(raw)[2][style - 1]


def default_of(raw):
    return mk._default_of(raw)


class Synthetic(unittest.TestCase):
    """Donor packages and team files stand in for the real ones; the module's own logic is what runs."""

    def setUp(self):
        for patch in (mock.patch.object(nfl_txtr, "parse_chunks", parse),
                      mock.patch.object(mk, "MAX_VIDEO_BYTES", 53 * VIDEO),
                      mock.patch.object(mk, "MAX_SYSTEM_BYTES", 53 * SYSTEM),
                      mock.patch.object(fixes, "compile_texture", fake_compile_texture),
                      mock.patch.object(mk, "palette_map", fake_palette_map)):
            patch.start()
            self.addCleanup(patch.stop)
        # retail donors: the Giants road sleeve has no maker marks
        self.retail = {s: package() for s in ("18H8", "18A8", "18A0", "07H3", "07A2")}

    def donors(self, marks=False, **override):
        out = dict(self.retail)
        if marks:
            out["18A0"] = package(c3=span(flag=MARKS))
        out.update(override)
        return out

    def retail_stub(self):
        retail = mk.RetailPackages("unused")
        retail.update(self.retail)
        return retail


class NothingToChangeSignal(unittest.TestCase):
    def test_it_is_a_value_error_with_the_message_the_plain_check_always_had(self):
        self.assertTrue(issubclass(fixes.NothingToChange, ValueError))
        exc = fixes.NothingToChange("2026 kit fixes: the art changed no texel")
        self.assertIsInstance(exc, ValueError)
        self.assertEqual(str(exc), "2026 kit fixes: the art changed no texel")

    def test_the_real_compiler_raises_it_on_art_that_changes_no_texel(self):
        # an all-white 8x8 sleeve and a white polygon over it: the shipped K1 step on a sleeve without marks
        import numpy as np
        from nfl_txtr import swizzle_2d
        decoded = bytearray(2 * 1024 + 64 + 64)
        palette = np.zeros((256, 4), np.uint8)
        palette[:, 3] = 255
        palette[0, :3] = (255, 255, 255)
        bgra = np.ascontiguousarray(palette[:, [2, 1, 0, 3]]).tobytes()
        decoded[0:1024] = bgra            # clean palette
        decoded[1024:2048] = bgra         # _mud twin
        decoded[2048:2112] = swizzle_2d(bytes(64), 8, 8, 1)
        chunk = types.SimpleNamespace(system_bytes=0, compressed=True, kind="TSET")
        textures = [dict(name="sleeve00", pixel=2048, palette=0, width=8, height=8, mips=1, format=0x0B),
                    dict(name="sleeve00_mud", pixel=2048, palette=1024, width=8, height=8, mips=1, format=0x0B)]
        row = {"chunk": 3, "kind": "tset", "texture": "sleeve00", "size": [8, 8, 1],
               "ops": [{"op": "poly", "color": "#FFFFFF", "points": [[0, 0], [4, 0], [4, 4], [0, 4]]}]}
        with mock.patch.object(fixes, "native_textures", return_value=(chunk, bytes(decoded), textures)):
            with self.assertRaises(fixes.NothingToChange) as caught:
                fixes.compile_texture(b"span", row)
        self.assertIn("the art changed no texel", str(caught.exception))
        self.assertTrue(str(caught.exception).startswith("2026 kit fixes: "))

    def test_a_palette_map_with_nothing_to_move_raises_it(self):
        import numpy as np
        decoded = bytes(1024)
        chunk = types.SimpleNamespace(video_bytes=0)
        textures = [dict(palette=0)]
        palette = np.zeros((256, 4), np.int64)       # no entry has alpha: nothing for the map to move
        row = {"chunk": 4, "kind": "palette_map", "map": [{"from": "#002E66", "to": "#FB4F14"}]}
        with mock.patch.object(fixes, "native_textures", return_value=(chunk, decoded, textures)), \
                mock.patch.object(fixes, "read_palette", return_value=palette), \
                mock.patch.object(fixes, "write_texture", return_value=decoded):
            with self.assertRaises(fixes.NothingToChange) as caught:
                mk.palette_map(b"span", row)
        self.assertIn("the palette map changed nothing", str(caught.exception))
        self.assertTrue(str(caught.exception).startswith("Anniversary moment kits: "))


class NoOpArtStep(Synthetic):
    """Part 1: an art step with nothing to change on a donor that is not the shipped SOFTDRINK one is named, not fatal."""

    side = k1()["sides"]["A"]

    def test_the_shipped_donors_stay_strict_and_the_refusal_names_the_kit_side_chunk_and_texture(self):
        with self.assertRaises(ValueError) as caught:
            mk.compose_side(self.side, self.donors(), None, None, "K1 (NYG, away)")
        text = str(caught.exception)
        self.assertTrue(text.startswith("Anniversary moment kits: K1 (NYG, away): "), text)
        self.assertIn("chunk 3 (sleeves, sleeve00)", text)
        self.assertIn("the art changed no texel", text)
        self.assertIn("artwork step", text)

    def test_on_other_donors_the_step_is_recorded_and_the_chunk_stays_as_the_donor_has_it(self):
        nothing = []
        out = mk.compose_side(self.side, self.donors(), self.retail_stub(), [], "K1 (NYG, away)", nothing)
        self.assertEqual(len(out), 53 * SPAN)
        self.assertEqual(out[3 * SPAN:4 * SPAN], span())                # the donor's sleeve, as it is
        self.assertEqual(len(nothing), 1)
        row = nothing[0]
        self.assertEqual((row["side"], row["chunk"], row["texture"], row["art"]), ("K1 (NYG, away)", 3, "sleeve00", "tset"))
        self.assertIn("2026 maker marks", row["step"])
        self.assertIn("changed no texel", row["reason"])

    def test_donors_that_do_carry_the_marks_are_repainted_and_record_nothing(self):
        nothing = []
        out = mk.compose_side(self.side, self.donors(marks=True), self.retail_stub(), [], "K1 (NYG, away)", nothing)
        self.assertEqual(out[3 * SPAN:4 * SPAN], span(flag=0))           # fake_compile_texture cleared the flag
        self.assertEqual(nothing, [])
        strict = mk.compose_side(self.side, self.donors(marks=True), None, None, "K1 (NYG, away)")
        self.assertEqual(out, strict)                                      # forgiving mode changes no successful result

    def test_the_forgiving_mode_never_changes_what_the_strict_mode_composes(self):
        for side in (k1()["sides"]["H"], k2()["sides"]["A"]):
            donors = self.donors(marks=True)
            self.assertEqual(mk.compose_side(side, donors), mk.compose_side(side, donors, self.retail_stub(), [], "x", []))

    def test_a_colour_swap_with_nothing_to_move_is_named_like_an_art_step(self):
        side = {"base": "18A8", "chunks": {"4": "18A0"}, "art": [{"chunk": 4, "kind": "palette_map", "map": []}]}
        donors = self.donors(**{"18A0": package(c4=span(flag=9))})
        nothing = []
        out = mk.compose_side(side, donors, self.retail_stub(), [], "K8 (DEN, home)", nothing)
        self.assertEqual(out[4 * SPAN:5 * SPAN], span(flag=9))
        self.assertEqual([(r["chunk"], r["art"]) for r in nothing], [(4, "palette_map")])
        with self.assertRaisesRegex(ValueError, r"K8 \(DEN, home\): the colour swap for chunk 4 \(socks\) cannot be applied"):
            mk.compose_side(side, donors, None, None, "K8 (DEN, home)")

    def test_another_art_failure_still_refuses_and_is_named(self):
        def broken(chunk_span, row, donors=None, *, fixed=True):
            raise ValueError("2026 kit fixes: texture size differs")
        with mock.patch.object(fixes, "compile_texture", broken):
            with self.assertRaisesRegex(ValueError, r"K1 \(NYG, away\): the artwork step for chunk 3 \(sleeves, sleeve00\) "
                                                    r"cannot be applied: texture size differs"):
                mk.compose_side(self.side, self.donors(), self.retail_stub(), [], "K1 (NYG, away)", [])

    def test_a_kit_left_out_records_no_swaps_and_no_no_ops_of_its_good_side(self):
        # the A side is made first and has a no-op step; the H side then cannot be made at all (no retail chunk fixes a
        # base that is not a kit package): the kit is left out and the build log must not mention its A side
        kit = dict(k1(), sides={"A": k1()["sides"]["A"], "H": k1()["sides"]["H"]})
        doc = dict(document(), kits=[kit])
        donors = self.donors(**{"18H8": package(c0=span(kind=b"T"))})
        report, nothing, skipped = [], [], {}
        out = mk.compose(doc, donors, self.retail_stub(), report, skipped, nothing)
        self.assertEqual(out, {})
        self.assertEqual(sorted(skipped), ["K1"])
        self.assertIn("K1 (NYG, home): the base kit 18H8 is not a kit package", skipped["K1"])
        self.assertEqual((report, nothing), ([], []))

    def test_a_made_kit_records_its_no_ops_once(self):
        doc = dict(document(), kits=[k1(), k2()])
        report, nothing, skipped = [], [], {}
        out = mk.compose(doc, self.donors(), self.retail_stub(), report, skipped, nothing)
        self.assertEqual(sorted(out), ["07a10.iff", "07h10.iff", "18a9.iff", "18h9.iff"])
        self.assertEqual((skipped, report), ({}, []))
        self.assertEqual([(r["side"], r["chunk"]) for r in nothing], [("K1 (NYG, away)", 3)])

    def test_dry_run_gives_the_project_check_a_receipt_the_notes_can_print(self):
        doc = document()
        receipt = mk.dry_run(doc, self.donors(), self.retail_stub())
        self.assertEqual(receipt["kits"], ["07a10.iff", "07h10.iff", "18a9.iff", "18h9.iff"])
        self.assertEqual([(r["side"], r["chunk"]) for r in receipt["unchanged_art"]], [("K1 (NYG, away)", 3)])
        self.assertEqual((receipt["skipped_kits"], receipt["dropped_defaults"], receipt["substitutions"]), ({}, [], []))
        self.assertEqual(len(mk.user_notes(receipt)), 1)
        # a kit that cannot be made goes, with the classic defaults that open on it
        broken = mk.dry_run(doc, self.donors(**{"18H8": package(c0=span(kind=b"T"))}), self.retail_stub())
        self.assertEqual(broken["kits"], ["07a10.iff", "07h10.iff"])
        self.assertEqual([(d["file"], d["kit"]) for d in broken["dropped_defaults"]], [(GIANTS_2007, "K1"), (GIANTS_2011, "K1")])
        notes = mk.user_notes(broken)
        self.assertEqual(len(notes), 3)
        self.assertIn("the new kit K1 was left out", notes[0])
        self.assertTrue(all("keeps the default uniform it has, because the new kit K1 it would open on was left out." in n
                            for n in notes[1:]))
        # the shipped SOFTDRINK donors: nothing is forgiven
        with self.assertRaisesRegex(ValueError, "K1 \\(NYG, away\\): the artwork step for chunk 3"):
            mk.dry_run(doc, self.donors(), None)

    def test_compose_still_works_with_the_positional_arguments_the_project_check_uses(self):
        doc = dict(document(), kits=[k1()])
        skipped = {}
        out = mk.compose(doc, self.donors(), self.retail_stub(), [], skipped)
        self.assertEqual(sorted(out), ["18a9.iff", "18h9.iff"])
        self.assertEqual(skipped, {})


class DroppedKitTakesItsDefaults(unittest.TestCase):
    """Part 2: a left-out kit takes the classic defaults that open on its style; the file keeps the uniform it has."""

    def test_the_defaults_that_need_the_kit_go_with_it_and_nothing_else_does(self):
        doc = document()
        live = mk.without_kits(doc, {"K1": "why"})
        self.assertEqual([k["id"] for k in live["kits"]], ["K2"])
        self.assertEqual([s["row"] for s in live["selections"]], [6])
        self.assertEqual([c["file"] for c in live["classic_defaults"]], [COWBOYS_1977])
        self.assertEqual(len(doc["classic_defaults"]), 3)                  # the shipped document is untouched
        self.assertEqual(mk.dropped_defaults(doc, {"K1": "why"}),
                         [{"file": GIANTS_2007, "style": 9, "kit": "K1"}, {"file": GIANTS_2011, "style": 9, "kit": "K1"}])
        self.assertIs(mk.without_kits(doc, {}), doc)
        self.assertEqual(mk.dropped_defaults(doc, {}), [])

    def test_a_default_on_an_existing_style_stays_even_when_a_kit_of_that_file_goes(self):
        doc = document()
        doc["classic_defaults"].append({"file": "h-11-1970-colts-5.iff", "style": 2, "before": 5, "why": "reuse"})
        doc["selections"].append({"row": 20, "side": "away", "file": "h-11-1970-colts-5.iff", "before": 5, "style": 2,
                                  "reuse": "11A2"})
        live = mk.without_kits(doc, {"K1": "why"})
        self.assertIn("h-11-1970-colts-5.iff", [c["file"] for c in live["classic_defaults"]])

    def test_a_document_without_defaults_or_selections_keeps_its_shape(self):
        bare = {"kits": [{"id": "K1"}], "selections": [{"row": 1, "side": "away", "kit": "K1", "file": "x", "style": 1}]}
        live = mk.without_kits(bare, {"K1": "why"})
        self.assertEqual(live, {"kits": [], "selections": []})


class StageOnSyntheticInputs(Synthetic):
    """The whole expected() state on Edwards' situation: retail donors, the Giants files as the build copy has them."""

    def inputs(self, donors, retail="stub", **extra):
        files = {GIANTS_2007: team_file("18", {i: (2000 + i, 2000 + i) for i in range(1, 9)}, 8),
                 GIANTS_2011: team_file("18", {i: (2000 + i, 2000 + i) for i in range(1, 9)}, 8),
                 COWBOYS_1977: team_file("07", {i: (1970 + i, 1970 + i) for i in range(1, 4)}, 3)}
        inputs = dict(packages=donors, files=files, members={}, situ=bytes(4 * 2 * 60), main=b"", skipped={}, allow_skip=True,
                      retail=self.retail_stub() if retail == "stub" else retail, report=[], unchanged=[],
                      dropped_defaults=[])
        inputs.update(extra)
        return inputs

    def expected(self, inputs, doc=None):
        fields = {(r, side): (0, 4 * (2 * r + (side == "home"))) for r in range(1, 52) for side in ("away", "home")}
        # fields[(row, side)] = (kit now, file offset of the kit field)
        with mock.patch.object(mk, "_situ_fields", return_value=fields), mock.patch.object(mk, "card_sources", return_value={}):
            return mk.expected(doc or document(), inputs)

    def test_edwards_options_on_retail_donors_make_both_kits_and_open_the_giants_files_on_style_9(self):
        inputs = self.inputs(self.donors())
        packages, _members, files, situ = self.expected(inputs)
        self.assertEqual(sorted(packages), ["07a10.iff", "07h10.iff", "18a9.iff", "18h9.iff"])
        self.assertEqual(inputs["skipped"], {})
        self.assertEqual([(r["side"], r["chunk"]) for r in inputs["unchanged"]], [("K1 (NYG, away)", 3)])
        self.assertEqual(inputs["dropped_defaults"], [])
        for name in (GIANTS_2007, GIANTS_2011):
            self.assertEqual(pair_of(files[name], 9), (2007, 2011))
            self.assertEqual(default_of(files[name]), 9)
        self.assertEqual((pair_of(files[COWBOYS_1977], 10), default_of(files[COWBOYS_1977])), ((1977, 1981), 10))
        self.assertEqual(struct.unpack_from("<I", situ, 4 * (2 * 27))[0], 9)

    def test_a_kit_that_cannot_be_made_is_left_out_with_its_defaults_and_the_build_goes_on(self):
        # K1's road base is not a kit package at all: the one failure no retail chunk can fix
        donors = self.donors(**{"18A8": package(c0=span(kind=b"T"))})
        inputs = self.inputs(donors)
        packages, _members, files, situ = self.expected(inputs)           # this is the build that stopped at 6 minutes
        self.assertEqual(sorted(packages), ["07a10.iff", "07h10.iff"])
        self.assertEqual(sorted(inputs["skipped"]), ["K1"])
        for name in (GIANTS_2007, GIANTS_2011):
            self.assertEqual(files[name], inputs["files"][name])          # the file is exactly as the copy has it
            self.assertEqual(default_of(files[name]), 8)
            self.assertEqual(pair_of(files[name], 9), (0, 0))
        self.assertEqual(default_of(files[COWBOYS_1977]), 10)             # the other kit is untouched by the drop
        self.assertEqual(struct.unpack_from("<I", situ, 4 * (2 * 27))[0], 0)    # the moment side keeps the kit it had
        self.assertEqual([(d["file"], d["style"], d["kit"], d["kept"]) for d in inputs["dropped_defaults"]],
                         [(GIANTS_2007, 9, "K1", 8), (GIANTS_2011, 9, "K1", 8)])

    def test_a_default_without_its_year_pair_is_still_refused_by_the_file_edit_and_names_the_file(self):
        # the exact state Coach Edwards' build reached: the Giants file lists styles 1-8, style 9 was never labelled
        raw = team_file("18", {i: (2000 + i, 2000 + i) for i in range(1, 9)}, 8)
        with self.assertRaisesRegex(ValueError, r"h-18-2007-giants-9.iff: its default uniform is style 9 \(currently style 8\) "
                                                r"but the file has no year pair for style 9, so the classic default 9 has no "
                                                r"year pair in its team file"):
            mk.file_edit(raw, {}, 9, GIANTS_2007)
        self.assertEqual(default_of(mk.file_edit(raw, {9: (2007, 2011)}, 9, GIANTS_2007)), 9)
        self.assertEqual(default_of(mk.file_edit(raw, {}, None, GIANTS_2007)), 8)
        self.assertTrue(mk._has_pair(raw, {9: (2007, 2011)}, 9))
        self.assertFalse(mk._has_pair(raw, {}, 9))
        self.assertTrue(mk._has_pair(raw, {}, 8))

    def test_the_shipped_donors_stay_strict_all_the_way_through(self):
        inputs = self.inputs(self.donors(), retail=None)
        with self.assertRaisesRegex(ValueError, r"K1 \(NYG, away\): the artwork step for chunk 3"):
            self.expected(inputs)
        inputs = self.inputs(self.donors(**{"18A8": package(c0=span(kind=b"T"))}), retail=None)
        with self.assertRaisesRegex(ValueError, r"K1 \(NYG, (away|home)\): the base kit 18A8 is not a kit package"):
            self.expected(inputs)

    def test_the_classic_teams_own_kit_is_never_left_out_but_its_no_ops_are_still_named(self):
        doc = dict(document(), kits=[k1()], selections=[], classic_defaults=[])
        inputs = self.inputs(self.donors(), allow_skip=False)
        packages, *_ = self.expected(inputs, doc)
        self.assertEqual(sorted(packages), ["18a9.iff", "18h9.iff"])
        self.assertEqual(len(inputs["unchanged"]), 1)
        inputs = self.inputs(self.donors(**{"18A8": package(c0=span(kind=b"T"))}), allow_skip=False)
        with self.assertRaisesRegex(ValueError, "not a kit package"):
            self.expected(inputs, doc)

    def test_a_default_the_file_cannot_show_is_dropped_by_name_not_fatal(self):
        # not caused by a left-out kit: style 5 is neither listed in the file nor labelled by any selection
        doc = document()
        doc["classic_defaults"].append({"file": "h-18-1990-giants-9.iff", "style": 5, "before": 3, "why": "x"})
        inputs = self.inputs(self.donors())
        inputs["files"]["h-18-1990-giants-9.iff"] = team_file("18", {1: (1990, 1990), 2: (1991, 1991)}, 2)
        packages, _members, files, _situ = self.expected(inputs, doc)
        self.assertEqual(default_of(files["h-18-1990-giants-9.iff"]), 2)
        extra = [d for d in inputs["dropped_defaults"] if d["file"] == "h-18-1990-giants-9.iff"]
        self.assertEqual([(d["style"], d["kit"], d["kept"]) for d in extra], [(5, None, 2)])
        self.assertIn("no year pair for style 5", extra[0]["why"])
        strict = self.inputs(self.donors(marks=True), retail=None)
        strict["files"]["h-18-1990-giants-9.iff"] = team_file("18", {1: (1990, 1990), 2: (1991, 1991)}, 2)
        with self.assertRaisesRegex(ValueError, "h-18-1990-giants-9.iff: its default uniform is style 5"):
            self.expected(strict, doc)

    def test_a_second_expected_call_describes_only_itself(self):
        inputs = self.inputs(self.donors())
        self.expected(inputs)
        self.expected(inputs)
        self.assertEqual(len(inputs["unchanged"]), 1)
        self.assertEqual(inputs["report"], [])


class Messages(Synthetic):
    """Every refusal names the kit, the file or donor, the side and why."""

    def test_a_missing_donor_names_the_kit_that_needs_it(self):
        target = types.SimpleNamespace(has=lambda name: name != mk.selector_name("18A0"), get=lambda *a, **k: b"")
        with self.assertRaisesRegex(ValueError, r"the donor kit 18A0 \(18a0.iff\) is not on the disc copy; the new kit K1 "
                                                r"is made from it"):
            mk.read_inputs(target, dict(document(), kits=[k1()]))

    def test_a_missing_team_file_names_the_rows_that_need_it(self):
        target = types.SimpleNamespace(has=lambda name: name != GIANTS_2007, get=lambda *a, **k: b"")
        with self.assertRaisesRegex(ValueError, r"the team file h-18-2007-giants-9.iff is not on the disc copy; the kits "
                                                r"stage needs it for row 27 away and its classic default"):
            mk.read_inputs(target, dict(document(), kits=[k1()]))

    def test_a_chunk_that_does_not_match_names_the_donor(self):
        donors = self.donors(**{"18A0": package(c3=span(kind=b"U"))})
        with self.assertRaisesRegex(ValueError, r"K1 \(NYG, away\): chunk 3 of the donor 18A0 does not match the chunk it "
                                                r"replaces in 18A8"):
            mk.compose_side(k1()["sides"]["A"], donors, None, None, "K1 (NYG, away)")

    def test_an_allocation_overflow_names_the_kit_and_side(self):
        donors = self.donors(**{"18A0": package(c3=span(flag=MARKS), c4=span(video=VIDEO + 500))})
        with self.assertRaisesRegex(ValueError, r"K1 \(NYG, away\): composed kit allocation .* exceeds the largest existing kit"):
            mk.compose_side(k1()["sides"]["A"], donors, None, None, "K1 (NYG, away)")

    def test_without_a_label_the_base_kit_names_the_side(self):
        donors = self.donors(**{"18A8": package(c0=span(kind=b"T"))})
        with self.assertRaisesRegex(ValueError, "18A8: the base kit 18A8 is not a kit package"):
            mk.compose_side(k1()["sides"]["A"], donors)

    def test_an_index_that_is_not_free_names_the_kit(self):
        target = types.SimpleNamespace()
        inputs = dict(new_present={"18h9.iff": True, "18a9.iff": False}, packages={}, files={}, members={}, situ=b"s")
        with self.assertRaisesRegex(ValueError, "18h9.iff already exists on the disc copy, so the index for the new kit K1 is "
                                                "not free"):
            mk.compile_edits(target, dict(document(), kits=[k1()]), inputs)

    def test_no_message_has_an_em_dash(self):
        text = Path(mk.__file__).read_text(encoding="utf-8")
        self.assertNotIn("—", text)


class Notes(unittest.TestCase):
    RECEIPT = dict(
        substitutions=[dict(side="K2 (DAL, away)", reason="Anniversary moment kits: K2 (DAL, away): composed kit allocation "
                            "10752/2867776 exceeds the largest existing kit", chunks=[8, 9], from_kits=["07A2"])],
        unchanged_art=[dict(side="K1 (NYG, away)", chunk=3, texture="sleeve00", art="tset",
                            step="remove the two 2026 maker marks above the stripes (2007 sleeves carry none)",
                            reason="the art changed no texel")],
        skipped_kits={"K7": "Anniversary moment kits: K7 (SEA, home): the base kit 26H5 is not a kit package; its first "
                            "chunk is TXTR, not Unif"},
        dropped_defaults=[dict(file=GIANTS_2007, style=9, kit="K1", kept=8, why="its kit was left out"),
                          dict(file="h-18-1990-giants-9.iff", style=5, kit=None, kept=2,
                               why="the file has no year pair for style 5")])

    def test_each_kind_of_decision_is_a_plain_sentence_naming_its_kit_and_file(self):
        notes = mk.user_notes(self.RECEIPT)
        self.assertEqual(len(notes), 5)
        self.assertTrue(all(n.startswith("Anniversary moment kits: ") for n in notes))
        swap, nothing, left_out, dropped, odd = notes
        self.assertIn("uses the retail shoes of 07A2", swap)
        self.assertIn("cannot be used in a new kit: composed kit allocation 10752/2867776 exceeds", swap)
        self.assertNotIn("K2 (DAL, away): composed", swap)                       # the side is already the subject
        self.assertIn("the new kit K1 (NYG, away) uses the sleeves of your kit unchanged (chunk 3, sleeve00)", nothing)
        self.assertIn("remove the two 2026 maker marks above the stripes (2007 sleeves carry none)", nothing)
        self.assertIn("had nothing to change on it.", nothing)
        self.assertIn("the new kit K7 was left out because the base kit 26H5 is not a kit package", left_out)
        self.assertTrue(left_out.endswith("The moment sides that use it keep the kit they had."))
        self.assertNotIn("K7 (SEA, home): the base", left_out)                   # no repeated label
        self.assertEqual(dropped, f"Anniversary moment kits: the classic team file {GIANTS_2007} keeps the default uniform "
                                  "it has (style 8), because the new kit K1 it would open on was left out.")
        self.assertIn("keeps the default uniform it has (style 2), because the file has no year pair for style 5", odd)

    def test_the_classic_teams_use_their_own_name_and_no_note_has_an_em_dash(self):
        notes = mk.user_notes(self.RECEIPT, "Classic teams' kits")
        self.assertTrue(all(n.startswith("Classic teams' kits: ") for n in notes))
        self.assertNotIn("—", "".join(notes))

    def test_an_older_receipt_without_the_new_rows_still_reads(self):
        old = dict(substitutions=[], skipped_kits={"K7": "Anniversary moment kits: not a kit package"})
        self.assertEqual(len(mk.user_notes(old)), 1)
        self.assertEqual(mk.user_notes({}), [])

    def test_the_classic_teams_get_their_own_prefix_on_a_refusal(self):
        with mock.patch.object(mk, "_apply_to_image", side_effect=ValueError("Anniversary moment kits: K14 (MIA, home): x")):
            with self.assertRaisesRegex(ValueError, "^Classic teams' kits: K14 \\(MIA, home\\): x$"):
                mk.apply_to_image("x", {}, None, False, "Classic teams' kits")
            with self.assertRaisesRegex(ValueError, "^Anniversary moment kits: K14 \\(MIA, home\\): x$"):
                mk.apply_to_image("x", {}, None, True)


class Wiring(unittest.TestCase):
    def test_a_copy_that_cannot_be_read_says_why(self):
        why = []
        with mock.patch("mod_editor.core.nfl2k5_music_archive.Disc", side_effect=OSError("disc is gone")):
            self.assertEqual(mk.image_status("x.iso", {"kits": [], "selections": []}, why=why), "foreign")
        self.assertEqual(why, ["OSError: disc is gone"])
        with mock.patch("mod_editor.core.nfl2k5_music_archive.Disc", side_effect=OSError("disc is gone")):
            self.assertEqual(mk.image_status("x.iso", {"kits": [], "selections": []}), "foreign")

    def test_the_read_back_of_a_rewritten_copy_names_what_it_found(self):
        with mock.patch.object(mk, "image_status", side_effect=lambda *a, why=None, **k: (why.append("KeyError: 'x'"), "foreign")[1]):
            with self.assertRaisesRegex(ValueError, r"the rewritten disc copy reads back as foreign, not as installed \(KeyError"):
                mk._verified("p", {}, None, True)
        with mock.patch.object(mk, "image_status", return_value="applied"):
            self.assertTrue(mk._verified("p", {}, None, True))

    def test_the_build_still_prints_the_notes_of_both_stages(self):
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        self.assertIn('for note in kits_receipt.get("user_notes", ()):', text)
        self.assertIn('for note in (classic_receipt.get("authored_kits") or {}).get("user_notes", ()):', text)

    def test_the_shipped_documents_and_pins_are_not_touched_by_this_job(self):
        pins = mk.pins()                      # raises when the data changed after the pins
        self.assertEqual(len(pins["packages"]), 26)
        doc = mk.document()
        self.assertEqual((len(doc["kits"]), len(doc["selections"]), len(doc["classic_defaults"])), (13, 16, 28))


# ------------------------------------------------------------------------------------------------ real discs

class Overlay:
    """Name/identity reads from a disc with in-memory replacements (the stage's edits, without writing)."""

    def __init__(self, source):
        self.source, self.data = source, {}

    def put(self, *, name=None, identity=None, data):
        self.data[hs.name_id(name) if identity is None else identity] = data

    def _key(self, name, identity):
        return hs.name_id(name) if identity is None else identity

    def has(self, name):
        return self._key(name, None) in self.data or self.source.has(name)

    def get(self, name=None, *, identity=None):
        key = self._key(name, identity)
        return self.data[key] if key in self.data else self.source.get(name, identity=identity)

    def outer(self, name=None, *, identity=None):
        return self._key(name, identity)


def retail_donors(doc, source, retail):
    """The retail package of every donor the document reads (a historic spare, absent on retail, is the franchise's
    retail style-0 kit, which is what the historic styles step puts there)."""
    out = {}
    for selector in mk.donors(doc):
        name = mk.selector_name(selector)
        out[selector] = retail.get(name) if retail.has(name) else retail.get(mk.selector_name(selector[:3] + "0"))
    return out


@unittest.skipUnless(RETAIL.is_file(), "retail disc absent")
class RetailDonors(unittest.TestCase):
    """Every kit side of both documents on the retail disc's own packages: nothing may refuse."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_classic_teams as ct
        cls.docs = [("moment", mk.document()), ("classic", ct.authored_kits())]
        with hs.Source(RETAIL) as retail:
            cls.retail = mk.RetailPackages(RETAIL)
            cls.packages = {}
            for _name, doc in cls.docs:
                cls.packages.update(retail_donors(doc, None, retail))
            cls.retail.update(cls.packages)

    def test_the_retail_donors_are_not_the_shipped_softdrink_donors(self):
        self.assertFalse(mk._donors_pinned(self.packages))

    def test_every_kit_side_composes_and_only_k1_has_a_step_with_nothing_to_change(self):
        report, nothing, skipped = [], [], {}
        made = {}
        for _name, doc in self.docs:
            made.update(mk.compose(doc, self.packages, self.retail, report, skipped, nothing))
        self.assertEqual(skipped, {})
        self.assertEqual(len(made), 2 * (13 + 1))
        self.assertEqual([(r["side"], r["chunk"], r["texture"]) for r in nothing], [("K1 (NYG, away)", 3, "sleeve00")])
        self.assertEqual(report, [])
        # the kit is the donor's own sleeve: the new K1 away package is byte for byte its donors' chunks
        from nfl_txtr import parse_chunks
        out = parse_chunks(made["18a9.iff"])
        donor = parse_chunks(self.packages["18A0"])
        self.assertEqual(made["18a9.iff"][out[3].offset:out[3].end_offset],
                         self.packages["18A0"][donor[3].offset:donor[3].end_offset])

    def test_the_old_strict_compose_is_what_refused_k1(self):
        doc = mk.document()
        k1_doc = dict(doc, kits=[k for k in doc["kits"] if k["id"] == "K1"])
        with self.assertRaisesRegex(ValueError, r"K1 \(NYG, away\): the artwork step for chunk 3 \(sleeves, sleeve00\) cannot "
                                                r"be applied: the art changed no texel"):
            mk.compose(k1_doc, self.packages)


@unittest.skipUnless(FIXTURE.is_file() and RETAIL.is_file(), "fixture or retail disc absent")
class StageOnTheFixtureDisc(unittest.TestCase):
    """The b775 fixture disc is a SOFTDRINK disc this stage has not touched. Its team files, moment table and card
    records are the real inputs; the donors are swapped for retail ones to rebuild Coach Edwards' situation."""

    @classmethod
    def setUpClass(cls):
        cls.doc = mk.document()
        cls.src = hs.Source(FIXTURE)
        cls.retail_source = hs.Source(RETAIL)
        cls.retail_packages = retail_donors(cls.doc, None, cls.retail_source)

    @classmethod
    def tearDownClass(cls):
        cls.src.__exit__(None, None, None)
        cls.retail_source.__exit__(None, None, None)

    def overlay(self, **donor_overrides):
        overlay = Overlay(self.src)
        for selector, data in {**self.retail_packages, **donor_overrides}.items():
            overlay.put(name=mk.selector_name(selector), data=data)
        return overlay

    def inputs(self, overlay, doc=None):
        inputs = mk.read_inputs(overlay, doc or self.doc, retail=RETAIL)
        if inputs["retail"] is not None:
            inputs["retail"].update(self.retail_packages)        # no per-selector reopening of the retail disc
        return inputs

    def test_edwards_options_compose_and_the_giants_files_open_on_style_9(self):
        overlay = self.overlay()
        inputs = self.inputs(overlay)
        self.assertIsNotNone(inputs["retail"])                             # not pinned: the forgiving mode
        packages, _members, files, situ = mk.expected(self.doc, inputs)
        self.assertEqual(len(packages), 2 * 13)
        self.assertEqual(inputs["skipped"], {})
        self.assertEqual([(r["side"], r["chunk"]) for r in inputs["unchanged"]], [("K1 (NYG, away)", 3)])
        self.assertEqual(inputs["dropped_defaults"], [])
        for name in (GIANTS_2007, GIANTS_2011):
            self.assertEqual(pair_of(files[name], 9), (2007, 2011))
            self.assertEqual(default_of(files[name]), 9)
        sides = {(row + 1, side): kit for row, side, _s, _y, kit, _f in hs.situ_sides(situ)}
        self.assertEqual((sides[(27, "away")], sides[(29, "away")]), (9, 9))
        edits, appended, receipt = mk.compile_edits(overlay, self.doc, inputs)      # the receipt the build keeps
        self.assertEqual(len(receipt["unchanged_art"]), 1)
        self.assertEqual(receipt["skipped_kits"], {})
        notes = mk.user_notes(receipt)
        self.assertEqual(len(notes), 1)
        self.assertIn("K1 (NYG, away) uses the sleeves of your kit unchanged (chunk 3, sleeve00)", notes[0])
        json.dumps(receipt)                                                  # the build writes the receipt as JSON
        self.assertTrue(appended)

    def test_a_kit_left_out_on_the_real_files_leaves_the_giants_files_alone(self):
        broken = package_of_wrong_kind(self.retail_packages["18A8"])
        overlay = self.overlay(**{"18A8": broken})
        inputs = self.inputs(overlay)
        packages, members, files, situ = mk.expected(self.doc, inputs)
        self.assertEqual(sorted(inputs["skipped"]), ["K1"])
        self.assertEqual(len(packages), 2 * 12)
        before = self.inputs(self.overlay())["files"]
        for name in (GIANTS_2007, GIANTS_2011):
            self.assertEqual(files[name], before[name])
            self.assertEqual(pair_of(files[name], 9), (0, 0))
            self.assertEqual(default_of(files[name]), 8)
        self.assertEqual({d["file"] for d in inputs["dropped_defaults"]}, {GIANTS_2007, GIANTS_2011})
        sides = {(row + 1, side): kit for row, side, _s, _y, kit, _f in hs.situ_sides(situ)}
        self.assertEqual((sides[(27, "away")], sides[(29, "away")]), (8, 8))  # both moment sides keep their kit
        edits, appended, receipt = mk.compile_edits(overlay, self.doc, inputs)
        self.assertEqual(sorted(receipt["skipped_kits"]), ["K1"])
        self.assertEqual(sorted(d["file"] for d in receipt["dropped_defaults"]), [GIANTS_2007, GIANTS_2011])
        notes = mk.user_notes(receipt)
        self.assertTrue(any("the new kit K1 was left out" in n for n in notes))
        self.assertEqual(sum(1 for n in notes if "keeps the default uniform it has (style 8)" in n), 2)
        json.dumps(receipt)
        # the stage then reads its own result back as installed: nothing in the copy contradicts the left-out kit
        applied = Overlay(self.src)
        for selector, data in {**self.retail_packages, "18A8": broken}.items():
            applied.put(name=mk.selector_name(selector), data=data)
        for a in hs.AGGREGATES:
            record, cdf = inputs["members"][a["name"]]
            record, cdf = hs.grow_aggregate(record, cdf, members[a["name"]])
            applied.put(identity=a["record"], data=record)
            applied.put(identity=a["cdf"], data=cdf)
        for name, data in {**files, **packages}.items():
            applied.put(name=name, data=data)
        applied.put(identity=hs.SITU_OUTER_ID, data=situ)
        after = self.inputs(applied)
        self.assertEqual(mk.state_of(self.doc, after, applied), "applied")
        self.assertEqual(sorted(after["skipped"]), ["K1"])

    def test_the_softdrink_donors_compose_the_same_bytes_strictly_and_in_the_forgiving_mode(self):
        # the b775 disc predates sw1 and vk2, which rewrite three donors each before this stage in a real build
        # (test_b775_ek1_moment_kits runs those passes); the forgiving mode must not change any package it can make
        donors = {s: self.src.get(mk.selector_name(s)) for s in mk.donors(self.doc)}
        strict = mk.compose(self.doc, donors)
        report, nothing, skipped = [], [], {}
        lenient = mk.compose(self.doc, donors, mk.RetailPackages(RETAIL), report, skipped, nothing)
        self.assertEqual(lenient, strict)
        self.assertEqual((report, nothing, skipped), ([], [], {}))


def package_of_wrong_kind(raw):
    """A donor whose first chunk is not the Unif chunk: the one failure that no retail chunk can repair."""
    from nfl_txtr import parse_chunks
    chunks = parse_chunks(raw)
    out = bytearray(raw)
    out[chunks[0].offset:chunks[0].offset + 4] = b"TXTR"        # chunk 0 reads as a texture chunk
    return bytes(out)


if __name__ == "__main__":
    unittest.main()
