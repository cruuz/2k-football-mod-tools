"""uf1 (b778): nameplate metrics follow the letter atlas a kit carries (Dallas Arctic Cowboy, 07H7/07A7).

SWeaR (10/21): "Last names are glitched on Dallas Alternate 1 uni". The slot wears the 2026 road kit's letters (07A0,
A at atlas offset 96) over the retail 1994 metrics (A at 128), so the compositor copied every letter from its
neighbour's cell. The gate: every kit's measured letter atlas must have its own NAME glyph layout.
"""
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_kit_fixes_2026 as fixes  # noqa: E402

# The two layouts involved, as the retail kits store them: 07A0 (2026 road, also 07H0) and 07A7 (1994 Arctic).
ROAD = [(32, 7), (64, 12)] + [(96 + 32 * i, w) for i, w in enumerate(
    (14, 12, 11, 12, 12, 12, 11, 14, 6, 12, 14, 12, 15, 14, 11, 12, 12, 13, 11, 11, 14, 14, 14, 15, 14, 11, 13))]
ARCTIC = [(32, 22), (64, 50)] + [(128 + 32 * i, w) for i, w in enumerate(
    (14, 12, 11, 12, 12, 12, 11, 14, 6, 12, 14, 12, 15, 14, 11, 12, 12, 13, 11, 11, 14, 14, 14, 15, 14, 11, 20))]


def name_span(metrics):
    """A raw 160-byte NAME chunk as the kits store it: 16-byte header, the texture name, the 29 metric pairs."""
    body = bytearray(160)
    body[12:16] = b"NAME"
    struct.pack_into("<II", body, 16, 0x11, 0x19)
    body[0x20:0x2A] = "names".encode("utf-16-le")
    struct.pack_into("<58H", body, 0x2C, *[v for pair in metrics for v in pair])
    header = struct.pack("<4s7I", b"NAME", 160, 0, 0, 0, 0, 0, 0)
    return header + bytes(body)


def starts(metrics):
    return [x for x, _ in metrics]


ROW = {"donor_selector": "07A0", "relayout": True}


class Layout(unittest.TestCase):
    def test_metrics_round_trip(self):
        self.assertEqual(fixes.name_metrics(name_span(ARCTIC)), ARCTIC)
        self.assertEqual(len(ROAD), len(ARCTIC), 29)

    def test_fit_needs_one_glyph_per_pair_at_its_offset(self):
        self.assertTrue(fixes.layout_fits(starts(ROAD), ROAD))
        self.assertTrue(fixes.layout_fits([x + 1 for x in starts(ROAD)], ROAD))       # one texel of slack
        self.assertFalse(fixes.layout_fits(starts(ROAD), ARCTIC))                     # the Dallas 7 defect
        self.assertFalse(fixes.layout_fits(starts(ROAD)[:-1], ROAD))                  # a glyph missing
        self.assertFalse(fixes.layout_fits([x + 2 for x in starts(ROAD)], ROAD))

    def test_relayout_takes_the_donor_offsets_and_widths(self):
        new, detail = fixes.compile_name(name_span(ARCTIC), name_span(ROAD), ROW, starts(ROAD))
        self.assertEqual(fixes.name_metrics(new), ROAD)
        self.assertEqual(new[:32 + 0x2C], name_span(ARCTIC)[:32 + 0x2C])               # header and name kept
        self.assertEqual((detail["offsets_changed"], detail["widths_changed"]), (27, 3))

    def test_relayout_leaves_an_atlas_that_fits_its_own_metrics(self):
        # a kit still wearing its retail 1994 letters must keep its metrics
        with self.assertRaisesRegex(ValueError, "already fits its own"):
            fixes.compile_name(name_span(ARCTIC), name_span(ROAD), ROW, starts(ARCTIC))

    def test_relayout_refuses_letters_of_a_third_layout(self):
        other = [(x + 4, w) for x, w in ROAD]
        with self.assertRaisesRegex(ValueError, "donor's glyph layout"):
            fixes.compile_name(name_span(ARCTIC), name_span(ROAD), ROW, starts(other))
        with self.assertRaisesRegex(ValueError, "measured atlas"):
            fixes.compile_name(name_span(ARCTIC), name_span(ROAD), ROW)

    def test_plain_name_rows_still_refuse_moved_offsets(self):
        with self.assertRaisesRegex(ValueError, "offsets differ"):
            fixes.compile_name(name_span(ARCTIC), name_span(ROAD), {"donor_selector": "07A0"})


class Data(unittest.TestCase):
    def setUp(self):
        self.doc = fixes.nameplates()

    def test_rows_are_the_two_arctic_cowboy_nameplates(self):
        rows = self.doc["textures"]
        self.assertEqual(sorted(r["selector"] for r in rows), ["07A7", "07H7"])
        for row in rows:
            self.assertEqual((row["kind"], row["chunk"], row["texture"], row["relayout"]), ("name", 44, "NAME", True))
            self.assertEqual(row["donor_selector"], "07A0")
            for key in ("before_sha256", "after_sha256", "donor_sha256"):
                self.assertRegex(row[key], "^[0-9a-f]{64}$")
            self.assertNotEqual(row["before_sha256"], row["after_sha256"])
            self.assertEqual(row["after_sha256"], row["donor_sha256"])     # the NAME span becomes the donor's
        self.assertNotIn("07A0", fixes.selectors(self.doc))

    def test_documents_are_separate(self):
        paths = {fixes.DATA, fixes.DATA_ALTS, fixes.DATA_UF3, fixes.DATA_SEA1, fixes.DATA_OV1, fixes.DATA_KU1,
                 fixes.DATA_SW1, fixes.DATA_NAMES}
        self.assertEqual(len(paths), 8)
        earlier = {(r["selector"], r["chunk"]) for path in paths - {fixes.DATA_NAMES}
                   for r in fixes.spec(path)["textures"]}
        self.assertFalse(earlier & {(r["selector"], r["chunk"]) for r in self.doc["textures"]})

    def test_no_private_paths_and_packaged(self):
        text = fixes.DATA_NAMES.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/media/", text)
        self.assertTrue(text.isascii())
        self.assertIn("data/nfl2k5_kit_fixes_2026_names.json",
                      (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines())

    def test_studio_runs_it_after_every_atlas_writer(self):
        text = (ROOT / "mod_editor/core/mod_build.py").read_text(encoding="utf-8")
        at = text.index("kit_fixes.apply_nameplates(target)")
        for earlier in ("kit_fixes.apply_finish(target)", "glyph_fixes.apply_to_image(target",
                        "kit_fixes.apply_swooshes(target)"):
            self.assertLess(text.index(earlier), at)
        self.assertLess(at, text.index("moment_kits.apply_to_image(target)"))

    def test_rows_need_their_donor(self):
        row = self.doc["textures"][0]
        with self.assertRaises(ValueError):
            fixes.compile_resource(row["selector"], bytes(row["resource_size"]), strict=True,
                                   document=dict(self.doc, textures=[row]))


def read_kits(disc, selectors=None):
    """Every kit package (<code><H|A><style>.IFF) of a disc image, read only."""
    from mod_editor.core import nfl2k5_bump_texture_writer as bump
    out = {}
    with bump._Image.open(Path(disc), writable=False) as image:
        index = bump._parsed_index(image)
        for entry in index.entries:
            name = bump.logical_name_for(entry.name_id) or ""
            stem = name[:-4] if name.endswith(".IFF") else ""
            if len(stem) in (4, 5) and stem[:2].isdigit() and stem[2] in "HA" and stem[3:].isdigit():
                if selectors is None or stem in selectors:
                    out[stem] = image.read_segments(index.sub_extents(entry, 0, entry.size))
    return out


RELEASE = os.environ.get("NFL2K5_V061_DISC")
RETAIL = os.environ.get("NFL2K5_RETAIL_XISO")


@unittest.skipUnless(RELEASE, "set NFL2K5_V061_DISC (the SOFTDRINK 2K28 v0.6.1 release disc, read only)")
class ReleaseDisc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = fixes.nameplates()
        cls.kits = read_kits(RELEASE)
        cls.fixed = {}
        for selector in fixes.selectors(cls.doc):
            raw = cls.kits[selector]
            parts, receipt = fixes.compile_resource(selector, raw, strict=True, document=cls.doc,
                                                    kits={"07A0": cls.kits["07A0"]})
            out = bytearray(raw)
            for at, data in parts:
                out[at:at + len(data)] = data
            cls.fixed[selector] = (parts, receipt, bytes(out))

    def test_only_the_name_metrics_change(self):
        for selector, (parts, receipt, fixed) in self.fixed.items():
            row = [r for r in self.doc["textures"] if r["selector"] == selector][0]
            self.assertEqual(len(parts), 1)
            changed = [i for i, (a, b) in enumerate(zip(self.kits[selector], fixed)) if a != b]
            self.assertTrue(changed)
            body = fixes._chunk_for(fixed, row["chunk"]).body_offset
            self.assertTrue(all(body + fixes.NAME_METRICS.start <= i < body + fixes.NAME_METRICS.stop for i in changed))
            self.assertEqual(fixes.sha(fixed[row["offset"]:row["offset"] + row["length"]]), row["after_sha256"])
            self.assertTrue(fixes.nameplate_layout(fixed)[2])
            self.assertFalse(fixes.nameplate_layout(self.kits[selector])[2])

    def test_replay_is_a_no_op(self):
        for selector, (_, _, fixed) in self.fixed.items():
            parts, receipt = fixes.compile_resource(selector, fixed, strict=True, document=self.doc,
                                                    kits={"07A0": self.kits["07A0"]})
            self.assertEqual((parts, receipt["state"]), ([], "applied"))

    def test_gate_every_kit_letter_atlas_has_its_own_glyph_layout(self):
        kits = dict(self.kits, **{s: f[2] for s, f in self.fixed.items()})
        self.assertGreater(len(kits), 650)
        wrong = [s for s, raw in sorted(kits.items()) if not fixes.nameplate_layout(raw)[2]]
        self.assertEqual(wrong, [])


@unittest.skipUnless(RETAIL, "set NFL2K5_RETAIL_XISO (the retail disc, read only)")
class RetailDisc(unittest.TestCase):
    def test_retail_arctic_cowboy_keeps_its_own_letters_and_metrics(self):
        doc = fixes.nameplates()
        kits = read_kits(RETAIL, set(fixes.selectors(doc)) | {"07A0"})
        for selector in fixes.selectors(doc):
            self.assertTrue(fixes.nameplate_layout(kits[selector])[2])
            parts, receipt = fixes.compile_resource(selector, kits[selector], strict=False, document=doc,
                                                    kits={"07A0": kits["07A0"]})
            self.assertEqual((parts, receipt["skipped_textures"]), ([], [44]))
            with self.assertRaisesRegex(ValueError, "donor's glyph layout"):
                fixes.compile_resource(selector, kits[selector], strict=True, document=doc,
                                       kits={"07A0": kits["07A0"]})

    def test_gate_every_retail_kit_fits(self):
        kits = read_kits(RETAIL)
        self.assertEqual(len(kits), 634)
        self.assertEqual([s for s, raw in sorted(kits.items()) if not fixes.nameplate_layout(raw)[2]], [])


if __name__ == "__main__":
    unittest.main()
