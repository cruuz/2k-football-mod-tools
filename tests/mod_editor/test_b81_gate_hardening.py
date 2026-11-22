"""b81-retail-free-art fix 1 (the reviewer's confirmation of ce2696ef0): the release check refuses texel data in any form,
not only in `paint`, `runs` and `texels` operations.

The reviewer appended 300 coloured texels to a b81u row as one-texel `clear` boxes (threshold -1), as unit-square `poly`
operations and as a new key holding a pixel list; the gate passed all three. Each injection must now be refused, in a
b81u row, in an alternates row (a v0.9 document, frozen in the catalog) and in the moment kits. The new rules are tested
one by one so that removing any of them fails here (RELEASE_CHECK points the tests at a mutated copy of the check)."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECK = Path(os.environ.get("RELEASE_CHECK", ROOT / "packaging/check_2k5_mod_studio_release.py"))
CELLS = [(20 + i % 20, 10 + i // 20, "#%02X%02X%02X" % (i * 7 % 256, i * 13 % 256, i * 29 % 256)) for i in range(300)]
B81U = "data/nfl2k5_kit_fixes_2026_b81u.json"
ALTS = "data/nfl2k5_kit_fixes_2026_alts.json"
MOMENT = "data/nfl2k5_moment_kits.json"
SW1 = "data/nfl2k5_kit_fixes_2026_sw1.json"
GLYPH = "data/nfl2k5_glyph_fixes_2026_b81u.json"


def load_check():
    spec = importlib.util.spec_from_file_location("release_check_hardening", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def first_ops(document):
    """The first operation list in a document (the moment kits have no selector rows)."""
    pending = [document]
    while pending:
        value = pending.pop(0)
        if isinstance(value, dict):
            ops = value.get("ops")
            if isinstance(ops, list) and ops and isinstance(ops[0], dict) and "op" in ops[0]:
                return ops
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    raise AssertionError("no operation list")


def row_ops(document, selector, chunk):
    return [r for r in document["textures"] if r["selector"] == selector and r["chunk"] == chunk][0]["ops"]


class GateHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release = load_check()
        catalog = json.loads((ROOT / "packaging/nfl2k5_modern_art_pngs.json").read_text(encoding="utf-8"))
        cls.reviewed = catalog["paint"]
        cls.docs = {rel: json.loads((ROOT / rel).read_text(encoding="utf-8")) for rel in (B81U, ALTS, MOMENT, SW1, GLYPH)}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def check(self, relative, document, reviewed=None):
        path = Path(self.tmp.name) / "doc.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        self.release._check_paint(relative, path, self.reviewed if reviewed is None else reviewed)

    def refused(self, relative, document, reviewed=None):
        with self.assertRaises(self.release.ReleaseCheckError):
            self.check(relative, document, reviewed)

    def targets(self):
        b81u = copy.deepcopy(self.docs[B81U]); alts = copy.deepcopy(self.docs[ALTS]); moment = copy.deepcopy(self.docs[MOMENT])
        return [(B81U, b81u, row_ops(b81u, "14A0", 1)), (ALTS, alts, row_ops(alts, "00A7", 3)), (MOMENT, moment, first_ops(moment))]

    def test_the_shipped_documents_pass(self):
        for relative in (B81U, ALTS, MOMENT, SW1, GLYPH):
            self.check(relative, self.docs[relative])

    def test_one_texel_clear_boxes_below_threshold_zero_are_refused(self):
        for relative, document, ops in self.targets():
            ops += [dict(op="clear", boxes=[[x, y, x + 1, y + 1]], to=c, above=-1, grow=0) for x, y, c in CELLS]
            self.refused(relative, document)

    def test_unit_square_polygons_are_refused(self):
        for relative, document, ops in self.targets():
            ops += [dict(op="poly", points=[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1]], color=c) for x, y, c in CELLS]
            self.refused(relative, document)

    def test_a_new_key_holding_a_pixel_list_is_refused(self):
        for relative, document, _ops in self.targets():
            document["notes_pixels"] = [[x, y, c] for x, y, c in CELLS]
            self.refused(relative, document)

    def test_an_unknown_operation_or_operation_key_is_refused(self):
        for relative, document, ops in self.targets():
            bad = copy.deepcopy(document)
            target = first_ops(bad) if relative == MOMENT else row_ops(bad, *(("14A0", 1) if relative == B81U else ("00A7", 3)))
            target.append(dict(op="pixels", data=[[x, y, c] for x, y, c in CELLS]))
            self.refused(relative, bad)
            bad = copy.deepcopy(document)
            target = first_ops(bad) if relative == MOMENT else row_ops(bad, *(("14A0", 1) if relative == B81U else ("00A7", 3)))
            target[0] = dict(target[0], extra=[[x, y, c] for x, y, c in CELLS])
            self.refused(relative, bad)

    def test_a_large_clear_below_threshold_zero_is_texel_data(self):
        document = copy.deepcopy(self.docs[B81U])
        row_ops(document, "14A0", 1).append(dict(op="clear", boxes=[[20, 10, 40, 30]], to="#123456", above=-1, grow=0))
        self.refused(B81U, document)

    def test_a_small_polygon_piece_is_texel_data(self):
        document = copy.deepcopy(self.docs[MOMENT])
        first_ops(document).append(dict(op="multipoly", color="#123456", polys=[[[1, 1], [2, 1], [2, 2]]]))
        self.refused(MOMENT, document)

    def test_a_warp_mask_change_is_refused(self):
        document = copy.deepcopy(self.docs[SW1])
        warp = next(op for r in document["textures"] for op in r["ops"] if op["op"] == "warp")
        warp["mask"] = warp["mask"] + [[0, 0, 1]]
        self.refused(SW1, document)

    def test_a_glyph_keep_run_change_is_refused(self):
        document = copy.deepcopy(self.docs[GLYPH])
        keep = next(op for r in document["textures"] for op in r.get("derive", []) if op.get("op") == "keep")
        keep["runs"] = keep["runs"] + [[0, 0, 1]]
        self.refused(GLYPH, document)

    def test_a_one_texel_painting_box_is_refused_even_when_reviewed(self):
        document = copy.deepcopy(self.docs[B81U])
        row_ops(document, "14A0", 1).append(dict(op="clear", boxes=[[20, 10, 21, 11]], to="#123456", above=0, grow=0))
        rows = self.release._texel_rows(document)
        reviewed = copy.deepcopy(self.reviewed)
        entry = reviewed[B81U]["rows"]["14A0:1:tset"]
        entry["sha256"] = self.release.hashlib.sha256(json.dumps(rows["14A0:1:tset"], sort_keys=True, separators=(",", ":"))
                                                      .encode("ascii")).hexdigest()
        with self.assertRaisesRegex(self.release.ReleaseCheckError, "one-texel painting boxes"):
            self.check(B81U, document, reviewed)

    def test_small_boxes_over_the_edge_limit_or_unmeasured_are_refused(self):
        row = next(k for k, v in self.reviewed[B81U]["rows"].items() if v.get("small_box_texels"))
        for value in (0.3, None):
            reviewed = copy.deepcopy(self.reviewed)
            reviewed[B81U]["rows"][row]["small_box_edge_retail"] = value
            with self.assertRaisesRegex(self.release.ReleaseCheckError, "small boxes cover too much"):
                self.check(B81U, self.docs[B81U], reviewed)

    def test_the_shapes_are_the_generator_output(self):
        spec = importlib.util.spec_from_file_location("gate_shapes", ROOT / "tools/b81_uniforms/gate_shapes.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual({k: sorted(v) for k, v in self.release.DOCUMENT_SHAPES.items()}, tool.build())


if __name__ == "__main__":
    unittest.main()
