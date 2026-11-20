"""b81-retail-free-art: the b81u digit pictures the uniform lane made by editing a retail-derived glyph never ship.

Those digits (the v0.9 glyph of a kit the Studio builds from a retail donor on the user's disc, with rows and columns
repeated, strokes grown or thinned, an edge ring or an inline recoloured) are ``digit_derived`` rows: the edit ships as
operations and the Studio applies them at build time to the glyph the build holds. The pictures that were withdrawn are
listed in tools/b77/modern_art_png_catalog.py NOT_AUTHORED with their SHA-256, so the release gate refuses them if one
is put back. With the released v0.9 disc on this machine (B81_UNIFORM_DISC) every derived row rebuilds its pinned
picture and a sample compiles to its output pin."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tools/b77")]
from mod_editor.core import nfl2k5_bump_texture_writer as bump  # noqa: E402
from mod_editor.core import nfl2k5_glyph_fixes_2026 as gf  # noqa: E402
import modern_art_png_catalog as catalog  # noqa: E402

DISC = Path(os.environ.get("B81_UNIFORM_DISC", "/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.9 (2026-11-05).xiso.iso"))
ART = "data/nfl2k5_glyph_fixes_2026_b81u/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def withdrawn():
    return {path: row for path, row in catalog.NOT_AUTHORED.items() if path.startswith(ART)}


class Document(unittest.TestCase):
    def setUp(self):
        self.doc = gf.digits_b81()

    def test_no_withdrawn_picture_ships_or_is_named(self):
        gone = withdrawn()
        self.assertGreater(len(gone), 200)
        digests = {row[0] for row in gone.values()}
        allow = set((ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines())
        for path in gone:
            self.assertNotIn(path, allow)
            self.assertFalse((ROOT / path).exists(), path)
        for row in self.doc["textures"]:
            self.assertNotIn(row.get("png_sha256"), digests, row.get("png"))
        for picture in gf.art_folder(self.doc).glob("*.png"):
            self.assertNotIn(sha(picture.read_bytes()), digests, picture.name)

    def test_derived_rows_carry_operations_and_no_picture(self):
        derived = [r for r in self.doc["textures"] if r["kind"] == "digit_derived"]
        self.assertGreater(len(derived), 300)
        for row in derived:
            self.assertNotIn("png", row)
            self.assertEqual(len(row["rgba_sha256"]), 64)
            self.assertEqual(row["derive"][-1]["op"] in ("remap", "inline_fill", "inline_dark", "edge"), True)
            for op in row["derive"]:
                self.assertIn(op["op"], gf.DERIVE_OPS)

    def test_every_shipped_picture_is_catalogued(self):
        document = json.loads((ROOT / catalog.CATALOG).read_text(encoding="utf-8"))
        listed = sorted(p for p in document["files"] if p.startswith(ART))
        self.assertEqual(listed, sorted(ART + p.name for p in gf.art_folder(self.doc).glob("*.png")))
        used = sorted({r["png"] for r in self.doc["textures"] if "png" in r})
        self.assertEqual([p[len(ART):] for p in listed], used)


class Operations(unittest.TestCase):
    def glyph(self):
        a = np.zeros((16, 16, 4), np.uint8)
        a[3:13, 5:11] = (20, 20, 20, 255)          # outline
        a[4:12, 6:10] = (250, 250, 250, 255)       # fill
        return a

    def test_remap_repeats_and_clears_whole_lines(self):
        a = self.glyph()
        out = gf.derive_digit(a, [dict(op="remap", rows=list(range(16)), cols=[-1] + list(range(15)))])
        self.assertTrue(np.array_equal(out[:, 1:], a[:, :15]))
        self.assertTrue((out[:, 0] == 0).all())

    def test_embolden_grows_the_fill_and_rebuilds_the_ring(self):
        a = self.glyph()
        out = gf.derive_digit(a, [dict(op="embolden", k=1, extra=False, fill="#FAFAFA", outline="#141414", ring=1)])
        self.assertEqual(out.shape, (32, 32, 4))
        fill = (out[..., :3] == 250).all(-1)
        self.assertEqual(int(fill.sum()), 8 * 4 + 2 * (8 + 4))           # one texel more on every side, no corners
        ring = (out[..., 3] == 255) & ~fill
        self.assertTrue((out[ring, :3] == 20).all())

    def test_edge_and_inlines_recolour_only(self):
        a = self.glyph()
        edged = gf.derive_digit(a, [dict(op="edge", keep=0, edge="#141414", fill="#FAFAFA")])
        self.assertTrue(np.array_equal(edged[..., 3], a[..., 3]))
        self.assertTrue((edged[a[..., 3] == 255, :3] == 250).all())
        inl = gf.derive_digit(a, [dict(op="inline_fill", colour="#D96428", fill="#FAFAFA")])
        self.assertEqual(int((inl[..., :3] == (0xD9, 0x64, 0x28)).all(-1).sum()), 8 * 4 - 6 * 2)
        dark = gf.derive_digit(a, [dict(op="inline_dark", colour="#D96428")])
        self.assertTrue(np.array_equal(dark[..., 3], a[..., 3]))

    def test_an_unknown_operation_is_refused(self):
        with self.assertRaises(ValueError):
            gf.derive_digit(self.glyph(), [dict(op="paste")])


@unittest.skipUnless(DISC.is_file(), "the released v0.9 disc is not on this machine")
class ReleasedDisc(unittest.TestCase):
    """Every derived row rebuilds its pinned picture from the glyph the released disc holds; a sample of each
    operation kind compiles to its output pin through the digit route."""

    @classmethod
    def setUpClass(cls):
        cls.doc = gf.digits_b81()
        cls.rows = [r for r in cls.doc["textures"] if r["kind"] == "digit_derived"]
        cls.kits = {}
        wanted = {r["selector"] for r in cls.rows}
        with bump._Image.open(DISC, writable=False) as image:
            index = bump._parsed_index(image)
            for entry in index.entries:
                name = bump.logical_name_for(entry.name_id)
                if name and name[:-4] in wanted:
                    cls.kits[name[:-4]] = image.read_segments(index.sub_extents(entry, 0, entry.size))

    def span(self, row):
        raw = self.kits[row["selector"]]
        chunk = gf._chunk_for(raw, row["chunk"])
        return raw[chunk.offset:chunk.end_offset]

    def test_every_derived_row_rebuilds_its_picture(self):
        for row in self.rows:
            span = self.span(row)
            self.assertEqual(sha(span), row["before_sha256"], row["selector"])
            rgba = gf.derive_digit(gf.digit_level0(span), row["derive"])
            self.assertEqual(sha(rgba.tobytes()), row["rgba_sha256"], (row["selector"], row["chunk"]))

    def test_a_sample_of_each_operation_kind_compiles_to_its_output_pin(self):
        seen = {}
        for row in self.rows:
            seen.setdefault("+".join(op["op"] for op in row["derive"]), row)
        for kinds, row in seen.items():
            new, _detail = gf.compile_derived_digit(self.span(row), row)
            self.assertEqual(sha(new), row["after_sha256"], kinds)


if __name__ == "__main__":
    unittest.main()
