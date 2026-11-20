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
RETAIL = Path(os.environ.get("B81_RETAIL_DISC", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
DERIVED = ("digit_derived", "names_derived")
ART = "data/nfl2k5_glyph_fixes_2026_b81u/"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def withdrawn():
    return {path: row for path, row in catalog.NOT_AUTHORED.items() if path.startswith(ART)}


PAINTED_ROWS = 112   # rows that list texels: Giants 80 and Cowboys navy 20 (remap + paint), Ravens 4 12 (remap +
                     # clear_rgb + paint of the visible redraw); the Raiders road edge and the Jaguars strip list none


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
        derived = [r for r in self.doc["textures"] if r["kind"] in DERIVED]
        self.assertEqual(len(derived), 495)                 # R2-G: the lane's 507 less the 12 Jets 2 rows round 2 redrew as new pictures (rated A)
        self.assertEqual(sum(r["kind"] == "names_derived" for r in derived), 3)
        for row in derived:
            if row["kind"] == "names_derived":                   # the Jaguars strip: an instruction, no texel (F3)
                self.assertEqual([op["op"] for op in row["derive"]], ["thin_letters"])
        for row in derived:
            self.assertNotIn("png", row)
            self.assertEqual(len(row["rgba_sha256"]), 64)
            for op in row["derive"]:
                self.assertIn(op["op"], gf.DERIVE_OPS)
                if op["op"] == "paint":
                    for y, x0, values in op["runs"]:
                        self.assertEqual(len(values) % 8, 0)        # RRGGBBAA per texel, nothing else

    def test_every_shipped_picture_is_catalogued(self):
        document = json.loads((ROOT / catalog.CATALOG).read_text(encoding="utf-8"))
        listed = sorted(p for p in document["files"] if p.startswith(ART))
        self.assertEqual(listed, sorted(ART + p.name for p in gf.art_folder(self.doc).glob("*.png")))
        used = sorted({r["png"] for r in self.doc["textures"] if "png" in r})
        self.assertEqual([p[len(ART):] for p in listed], used)


class ReviewedPaint(unittest.TestCase):
    """Review F5: texel data inside a data file is gated like a picture: every operation that stores texels (glyph
    ``paint`` runs, kit-fix ``runs`` and ``texels``) in any data document is listed per row (SHA-256, texel count) in
    the pinned modern-art catalog, and the release check refuses any other or any change."""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("release_check", ROOT / "packaging/check_2k5_mod_studio_release.py")
        self.release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.release)
        self.catalog = json.loads((ROOT / catalog.CATALOG).read_text(encoding="utf-8"))

    def test_the_catalog_lists_exactly_the_texel_data_of_every_data_document(self):
        self.assertEqual(self.catalog["paint"], catalog.paint_section(ROOT))
        glyph = self.catalog["paint"]["data/nfl2k5_glyph_fixes_2026_b81u.json"]["rows"]
        self.assertEqual(len(glyph), PAINTED_ROWS)
        for name in ("kit_fixes_2026_b81u", "kit_fixes_2026_b81", "kit_fixes_2026_sea1", "kit_fixes_2026_sw1",
                     "kit_fixes_2026_uf3"):
            self.assertIn("data/nfl2k5_%s.json" % name, self.catalog["paint"])
        for relative in self.catalog["paint"]:                      # the release check's walk finds the same rows
            document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            self.assertEqual(sorted(self.release._texel_rows(document)), sorted(self.catalog["paint"][relative]["rows"]))

    def test_the_gate_refuses_unreviewed_or_changed_texel_data(self):
        import tempfile
        reviewed = self.catalog["paint"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "doc.json"
            for relative, kind in (("data/nfl2k5_glyph_fixes_2026_b81u.json", "paint"),
                                   ("data/nfl2k5_kit_fixes_2026_b81u.json", "texels")):
                document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
                path.write_text(json.dumps(document), encoding="utf-8")
                self.release._check_paint(relative, path, reviewed)                     # as shipped: passes
                rows = document["textures"]
                op = next(o for r in rows for o in (r.get("derive") or r.get("ops") or []) if o["op"] == kind)
                if kind == "paint":
                    op["runs"].append([0, 0, "FFFFFFFF"])                                 # one more texel
                else:
                    op["points"].append([0, 0])
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.assertRaises(self.release.ReleaseCheckError):
                    self.release._check_paint(relative, path, reviewed)
            for stray in ({"rows": [{"op": "paint", "runs": [[1, 2, "00000000"]]}]},
                          {"textures": [{"selector": "00H0", "chunk": 1, "ops": [{"op": "runs", "rows": [[0, 0, "000000"]]}]}]},
                          {"x": {"op": "texels", "color": "#000000", "points": [[0, 0]]}}):
                path.write_text(json.dumps(stray), encoding="utf-8")
                with self.assertRaises(self.release.ReleaseCheckError):                   # texels in any other file
                    self.release._check_paint("data/other.json", path, reviewed)


class Operations(unittest.TestCase):
    def test_clear_rgb_and_hidden_recolour_touch_only_what_they_say(self):
        """Review rule: the colour stored under clear texels moves by rule (``clear_rgb``, ``recolour`` with ``hidden``),
        never by listing the clear surround's texels (round 2's Raiders and Ravens rows listed about 2,400 each)."""
        a = np.zeros((8, 8, 4), np.uint8)
        a[..., :3] = (200, 199, 199)
        a[2:6, 2:6] = (200, 199, 199, 255)
        a[3:5, 3:5] = (10, 10, 10, 255)
        out = gf.derive_digit(a, [dict(op="clear_rgb", colour="#000000")])
        self.assertTrue((out[a[..., 3] == 0, :3] == 0).all() and np.array_equal(out[a[..., 3] > 0], a[a[..., 3] > 0]))
        seen = gf.derive_digit(a, [dict(op="recolour", pairs=[["#C8C7C7", "#A5ADB0"]])])
        both = gf.derive_digit(a, [dict(op="recolour", pairs=[["#C8C7C7", "#A5ADB0"]], hidden=True)])
        self.assertTrue((seen[0, 0, :3] == (200, 199, 199)).all() and (both[0, 0, :3] == (165, 173, 176)).all())
        self.assertTrue(np.array_equal(seen[a[..., 3] > 0], both[a[..., 3] > 0]))

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
        cls.rows = [r for r in cls.doc["textures"] if r["kind"] in DERIVED]
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
        if row["kind"] == "names_derived":                  # pinned to the strip the nameplate pass leaves
            import b81_uniform_pass as up
            if not hasattr(type(self), "_retail"):
                type(self)._retail = up.retail_kits_for_nameplates(RETAIL)
            raw = up.after_nameplate_pass(row["selector"], raw, self._retail)
        chunk = gf._chunk_for(raw, row["chunk"])
        return raw[chunk.offset:chunk.end_offset]

    def base(self, row, span):
        return gf.names_level0(span) if row["kind"] == "names_derived" else gf.digit_level0(span)

    def test_every_derived_row_rebuilds_its_picture(self):
        for row in self.rows:
            if row["kind"] == "names_derived" and not RETAIL.is_file():
                continue
            span = self.span(row)
            self.assertEqual(sha(span), row["before_sha256"], row["selector"])
            rgba = gf.derive_digit(self.base(row, span), row["derive"])
            self.assertEqual(sha(rgba.tobytes()), row["rgba_sha256"], (row["selector"], row["chunk"]))

    def test_a_paint_ships_no_texel_equal_to_the_base_and_never_traces_its_shape(self):
        """Review F3/F4: erasures are instructions, additions are pixels. A paint texel always differs from what the
        operations before it made, and the shipped texels cover at most a quarter of the base's edge texels (the
        generator's EDGE_OVERLAP_LIMIT); the Jaguars strip ships no texel at all (``thin_letters``)."""
        sys.path.insert(0, str(ROOT / "tools/b81_uniforms"))
        import glyph_derive as tool
        painted = 0
        for row in self.rows:
            ops = row["derive"]
            if row["kind"] == "names_derived":
                self.assertEqual([op["op"] for op in ops], ["thin_letters"])
                continue
            if not any(op["op"] == "paint" for op in ops):
                continue
            base = self.base(row, self.span(row))
            for at, op in enumerate(ops):                   # a paint after other operations (the Ravens 4) differs
                if op["op"] != "paint":                     # from the picture those operations make
                    continue
                before = gf.derive_digit(base, ops[:at])
                for y, x0, values in op["runs"]:
                    shipped = np.frombuffer(bytes.fromhex(values), np.uint8).reshape(-1, 4)
                    here = before[y, x0:x0 + len(shipped)]
                    self.assertTrue((shipped != here).any(-1).all(), (row["selector"], row["chunk"], y, x0))
            self.assertLessEqual(tool.edge_overlap(base, ops), tool.EDGE_OVERLAP_LIMIT, (row["selector"], row["chunk"]))
            painted += 1
        self.assertEqual(painted, PAINTED_ROWS)

    def test_a_sample_of_each_operation_kind_compiles_to_its_output_pin(self):
        seen = {}
        for row in self.rows:
            seen.setdefault(row["kind"] + ":" + "+".join(op["op"] for op in row["derive"]), row)
        for kinds, row in seen.items():
            if row["kind"] == "names_derived" and not RETAIL.is_file():
                continue
            compile_row = gf.compile_derived_names if row["kind"] == "names_derived" else gf.compile_derived_digit
            new, _detail = compile_row(self.span(row), row)
            self.assertEqual(sha(new), row["after_sha256"], kinds)


if __name__ == "__main__":
    unittest.main()
