"""b81-retail-free-art, fix 1 of the re-check of f9ac917c4: every data document that holds operations, and every data
JSON added after the list began, is pinned by its whole-document SHA-256 in the generator-written, hash-pinned catalog;
an unlisted data JSON or a changed document is refused (the PNG catalog's rule). Non-integer box coordinates count as
boxes (fix 2).

The reviewer's 15 attempts that passed f9ac917c4 (rev-retail-free/r3/bin/attacks.py, attacks2.py: A1 to A3, A6, A7b,
A8 to A11, A14 to A17, A18, A19) are gate tests here: each must now be refused by the gate's own checks, run in the
order the gate runs them (document pin, then the paint check). RELEASE_CHECK points the tests at a mutated copy of the
check (tools in the lane folder: gate_mutations.py)."""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECK = Path(os.environ.get("RELEASE_CHECK", ROOT / "packaging/check_2k5_mod_studio_release.py"))
PIX = [((200 + i % 20), (100 + i // 20), "#%02X%02X%02X" % (i * 7 % 256, i * 13 % 256, i * 29 % 256)) for i in range(300)]
HEXDUMP = "".join(c[1:] for _x, _y, c in PIX)
B81U = "data/nfl2k5_kit_fixes_2026_b81u.json"
ALTS = "data/nfl2k5_kit_fixes_2026_alts.json"
SW1 = "data/nfl2k5_kit_fixes_2026_sw1.json"
GLY = "data/nfl2k5_glyph_fixes_2026_b81u.json"
UF3 = "data/nfl2k5_kit_fixes_2026_uf3.json"
NEWDOC = "data/nfl2k5_new_pixels.json"


def load_check():
    spec = importlib.util.spec_from_file_location("release_check_pins", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(d, sel, ch):
    return [r for r in d["textures"] if r["selector"] == sel and str(r["chunk"]) == str(ch)][0]


def a1(d):
    r = row(d, "14A0", 1)
    for x, y, c in sorted(PIX, key=lambda p: (p[1], p[0])):
        r["ops"].append(dict(op="clear", boxes=[[x, y, x + 16, y + 1]], to=c, above=0, grow=0))


def a2(d):
    r = row(d, "14A0", 1)
    for i in range(75):
        x, y = 200 + 4 * (i % 15), 100 + 4 * (i // 15)
        r["ops"].append(dict(op="clear", boxes=[[x, y, x + 4, y + 4]], to=PIX[i][2], above=0, grow=0))


def a3(d):
    r = d["textures"][0]
    for x, y, c in sorted(PIX, key=lambda p: (p[1], p[0])):
        r["ops"].append(dict(op="poly", points=[[x, y], [x + 16.5, y], [x + 16.5, y + 1], [x, y + 1]], color=c))


def a6(d):
    pts = [[round(250 + (40 + 8 * math.sin(7 * t)) * math.cos(t), 2), round(120 + (40 + 8 * math.sin(7 * t)) * math.sin(t), 2)]
           for t in (2 * math.pi * k / 200 for k in range(200))]
    d["textures"][0]["ops"].append(dict(op="poly", points=pts, color="#123456"))


def a7b(d):
    for r in d["textures"]:
        for o in r["ops"]:
            if o["op"] == "warp":
                n = json.loads(json.dumps(o))
                n["mask"] = []
                n["nodes"]["use"] = "".join("1" if (i * 37) % 5 < 2 else "0" for i in range(300))
                n["nodes"]["dst"] = [[x, y] for x, y, _c in PIX]
                r["ops"].append(n)
                return


def a8(d):
    row(d, "14A0", 1)["note"] += " " + HEXDUMP


def a9(d):
    [r for r in d["textures"] if r.get("donors")][0]["donors"]["999"] = HEXDUMP


def a10(d):
    r = [r for r in d["textures"] if "ints" in r][0]
    r["ints"] = list(r["ints"]) + [int(c[i:i + 2], 16) for _x, _y, c in PIX for i in (1, 3, 5)]


def a11(d):
    for r in d["textures"]:
        for o in r.get("derive", []):
            if o["op"] == "remap":
                o["rows"] = list(o["rows"]) + [int(c[i:i + 2], 16) for _x, _y, c in PIX for i in (1, 3, 5)]
                return


def a14(d):
    r = row(d, "14A0", 1)
    for x, y, c in PIX:
        r["ops"].append(dict(op="clear", boxes=[[float(x), float(y), x + 1.0, y + 1.0]], to=c, above=0, grow=0))


def a15(d):
    for o in row(d, "00A7", 3)["ops"]:
        if o["op"] in ("poly", "multipoly"):
            if o["op"] == "poly":
                o["points"][0][0] += 1
            else:
                o["polys"][0][0][0] += 1
            return


def a16(d):
    for r in d["textures"]:
        for o in r["ops"]:
            if o["op"] in ("recolor", "poly") and "color" in o:
                o["color"] = "#ABCDEF"
                return


def a17(d):
    ref = d.get("references")
    if isinstance(ref, dict):
        ref["ZZ_pixels"] = HEXDUMP
    else:
        d["references"].append(HEXDUMP)


EDITS = [("A1", B81U, a1), ("A2", B81U, a2), ("A3", ALTS, a3), ("A6", ALTS, a6), ("A7b", SW1, a7b), ("A8", B81U, a8),
         ("A9", B81U, a9), ("A10", UF3, a10), ("A11", GLY, a11), ("A14", B81U, a14), ("A15", ALTS, a15), ("A16", ALTS, a16),
         ("A17", GLY, a17)]
NEW_DOCUMENTS = [("A18", {"schema": "x/v1", "pixels": [[x, y, c] for x, y, c in PIX]}),
                 ("A19", {"schema": "nfl2k5_kit_fixes_2026/v1", "method": "x", "source": "x",
                          "textures": [dict(selector="14A0", chunk=1, kind="tset",
                                            ops=[dict(op="clear", boxes=[[x, y, x + 16, y + 1]], to=c, above=0, grow=0)
                                                 for x, y, c in PIX])]})]


class DocumentPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = load_check()
        catalog = json.loads((ROOT / "packaging/nfl2k5_modern_art_pngs.json").read_text(encoding="utf-8"))
        cls.paint = catalog["paint"]
        cls.documents = catalog["documents"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def gate(self, relative, data: bytes):
        """The gate's data-document checks, in the gate's order."""
        path = Path(self.tmp.name) / "doc.json"
        path.write_bytes(data)
        self.release._check_document_pin(relative, path, self.documents)
        self.release._check_paint(relative, path, self.paint)

    def test_every_shipped_data_json_passes_and_every_document_with_operations_is_pinned(self):
        declared = [line.strip() for line in (ROOT / "packaging/release-allowlist.txt").read_text(encoding="utf-8").splitlines()
                    if line.strip().startswith("data/") and line.strip().endswith(".json")]
        self.assertEqual(sorted(declared), sorted(self.documents))
        for relative in declared:
            data = (ROOT / relative).read_bytes()
            self.gate(relative, data)
            if self.release._edits_textures(json.loads(data.decode("utf-8"))):
                self.assertIsNotNone(self.documents[relative], relative)

    def test_the_reviewers_fifteen_passing_attempts_are_refused(self):
        for name, relative, edit in EDITS:
            document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            edit(document)
            with self.subTest(name), self.assertRaises(self.release.ReleaseCheckError):
                self.gate(relative, json.dumps(document).encode("utf-8"))
        for name, document in NEW_DOCUMENTS:
            with self.subTest(name), self.assertRaisesRegex(self.release.ReleaseCheckError, "does not list"):
                self.gate(NEWDOC, json.dumps(document).encode("utf-8"))

    def test_texture_documents_without_operations_are_pinned_too(self):
        """sea1 (a colour map), the relief and sideline passes, the v0.9 glyph document: no `op` key, but they write
        textures, so they are pinned whole; the reviewer's A8 (a note carrying a hex dump) in any of them is refused."""
        for relative in ("data/nfl2k5_kit_fixes_2026_sea1.json", "data/nfl2k5_relief_2026_b81u.json",
                         "data/nfl2k5_sideline_2026_b81u.json", "data/nfl2k5_glyph_fixes_2026.json"):
            self.assertIsNotNone(self.documents[relative], relative)
            document = json.loads((ROOT / relative).read_text(encoding="utf-8"))
            document["note"] = HEXDUMP
            with self.subTest(relative), self.assertRaisesRegex(self.release.ReleaseCheckError, "differs from its reviewed"):
                self.gate(relative, json.dumps(document).encode("utf-8"))

    def test_a_reformatted_document_is_refused_too(self):
        """The pin is the whole document: the same content written another way is a different document."""
        data = (ROOT / B81U).read_bytes()
        with self.assertRaisesRegex(self.release.ReleaseCheckError, "differs from its reviewed hash"):
            self.gate(B81U, json.dumps(json.loads(data)).encode("utf-8") + b" ")

    def test_texture_edits_in_a_document_listed_without_a_hash_are_refused(self):
        name_only = next(k for k, v in self.documents.items() if v is None)
        for carrier in ({"schema": "x/v1", "ops": [{"op": "clear"}]}, {"schema": "x/v1", "map": {"1": 2}},
                        {"schema": "x/v1", "rows": [{"before_sha256": "0" * 64}]}):
            with self.subTest(carrier), self.assertRaisesRegex(self.release.ReleaseCheckError, "no reviewed hash"):
                self.release._check_document_pin(name_only, self._write(carrier), self.documents)

    def _write(self, document):
        path = Path(self.tmp.name) / "doc.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_non_integer_box_coordinates_are_boxes(self):
        op = dict(op="clear", boxes=[[20.0, 10.0, 21.0, 11.0]], to="#123456", above=0, grow=0)
        self.assertTrue(self.release._is_box(op["boxes"][0]))
        self.assertEqual(self.release._op_texels(op), 1)
        self.assertEqual(self.release._one_texel_painting_boxes([op]), 1)
        half = dict(op, boxes=[[20.25, 10.0, 20.75, 10.5]])
        self.assertEqual(self.release._one_texel_painting_boxes([half]), 1)
        self.assertFalse(self.release._is_box([0, 0, float("nan"), 1]))

    def test_float_boxes_are_refused_by_the_paint_check_alone(self):
        """Fix 2 stands without fix 1: the reviewer's A14 fails the paint check even with the document pin set aside."""
        document = json.loads((ROOT / B81U).read_text(encoding="utf-8"))
        a14(document)
        path = self._write(document)
        with self.assertRaisesRegex(self.release.ReleaseCheckError, "texel data|one-texel painting"):
            self.release._check_paint(B81U, path, self.paint)


if __name__ == "__main__":
    unittest.main()
