"""b81 helmet-sides: helmet number set E in the player-model growth (nfl2k5_hair_styles + numbers.json).

The owner (11/22): the 2026 Chargers' number on the sides of the helmet, "Scope it for this release". Set E = three
materials NUMBER_helmet_E_L/M/R added after the hair materials in hi_head and lo_body; each cell draws one patch on
each side of the helmet, outside both Riddell shells, with set D's records (skin, digit window) and its own
positions. A disc grown before b81 (hair only) is recognised and regrown; the hair cave's count check follows.
"""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT, ROOT / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402

from mod_editor.core import nfl2k5_hair_styles as hs  # noqa: E402
from mod_editor.core import nfl2k5_memory_budget as mb  # noqa: E402
from mod_editor.core import nfl2k5_models as models  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
PACK0 = EXTRACTION / "ESPN NFL 2K5 (USA)" / "vc_53450030" / "0"
INVENTORY = ROOT / "reports" / "assets" / "nfl2k5_resource_chunks_v2.json"
#: a standard build of beta 81 made before set E (hair cave of b775-b80); optional
BASE_XBE = os.environ.get("NFL2K5_B81_BASE_XBE", "")
_OUTER3 = None


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def retail_outer3() -> bytes:
    global _OUTER3
    if _OUTER3 is None:
        if not (PACK0.is_file() and INVENTORY.is_file()):
            raise unittest.SkipTest("private USA pack 0 required")
        src = models.ModelSource(PACK0, INVENTORY)
        entry = src.archive.entries[hs.OUTER]
        _OUTER3 = src._outer.read_entry_range(src.archive, entry, 0, entry.size)
    return _OUTER3


def scene(key: str) -> bytes:
    outer3 = retail_outer3()
    chunk = hs._chunks(outer3)[models.parse_model_key(key)[1]]
    return hs.decode_span(hs._chunk_span(outer3, chunk))


class Parsed:
    """A decoded scene through the hair generator's parser (positions, uv, selectors, triangles by material)."""

    def __init__(self, key: str, decoded: bytes):
        from nfl2k5_hair_styles_generate import Scene
        self.sc = Scene(key, decoded)

    def verts(self, name: str) -> list[int]:
        return sorted({v for t in self.sc.tris({name}) for v in t})


class DataTests(unittest.TestCase):
    def test_numbers_file_is_pinned_and_names_set_e(self):
        doc = hs.load_numbers()
        self.assertEqual(tuple(doc["materials"]), ("NUMBER_helmet_E_L", "NUMBER_helmet_E_M", "NUMBER_helmet_E_R"))
        self.assertEqual(tuple(doc["templates"]), ("NUMBER_helmet_D_L", "NUMBER_helmet_D_M", "NUMBER_helmet_D_R"))
        self.assertEqual(hs.load_pins()["numbers_sha256"], sha(hs.NUMBERS_PATH.read_bytes()))
        self.assertTrue(hs.available())
        self.assertEqual(set(doc["scenes"]), set(hs.KEYS))

    def test_hair_cave_counts_follow_the_growth(self):
        self.assertEqual(hs.N, 3)
        self.assertEqual(hs.ROWS, {0: hs.RETAIL[hs.LO]["materials"] + hs.K + hs.N,
                                   2: hs.RETAIL[hs.HI]["materials"] + hs.K + hs.N})
        va = 0x14DA000
        new, old = hs.code_for(va), hs.code_for(va, hs.K)
        self.assertEqual(len(new), len(old))
        diff = [i for i, (a, b) in enumerate(zip(new, old)) if a != b]
        # the two count immediates (one byte each differs) and the sub ecx, imm8
        self.assertEqual(len(diff), 3, diff)


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.grown = {key: hs.grow_scene(key, scene(key)) for key in hs.KEYS}

    def test_set_e_follows_the_hair_materials(self):
        for key in hs.KEYS:
            g, receipt = self.grown[key]
            self.assertEqual(hs.scene_state(key, g), "grown")
            self.assertTrue(receipt["helmet_number_set_e"])
            lay = hs.layout(key, g)
            base = hs.RETAIL[key]["materials"]
            self.assertEqual([lay.names[base + k] for k in range(hs.K + hs.N)], hs.added_names(True))
            rows = {r["name"]: r for r in lay.submesh_rows}
            for name in hs.NUMBER_MATERIALS:
                self.assertEqual(rows[name]["material"], base + hs.K + hs.NUMBER_MATERIALS.index(name))

    def test_set_e_materials_carry_the_display_word_the_game_gives_every_bound_number_set(self):
        """Review 11/22 finding 1: after the registration loop the game walks rows 0..13 of a model row and stores 0xFFFF
        in word +0xA of every bound material (0x90C08..0x90C5E; the renderer at 0x2D123 sends it times 1/32768 as a
        vertex-shader constant, about 2.0). Set E's row lies outside that walk, so its materials carry the value
        themselves; set D's records keep the file value (the game raises them at load)."""
        for key in hs.KEYS:
            g, _ = self.grown[key]
            lay = hs.layout(key, g)
            names = {v: k for k, v in lay.names.items()}
            for cell in hs.NUMBER_CELLS:
                e = lay.materials + 0x80 * names[f"NUMBER_helmet_E_{cell}"]
                d = lay.materials + 0x80 * names[f"NUMBER_helmet_D_{cell}"]
                self.assertEqual(struct.unpack_from("<H", g, e + 0xA)[0], 0xFFFF, (key, cell))
                self.assertEqual(struct.unpack_from("<H", g, d + 0xA)[0], 0x8000, (key, cell))
                self.assertEqual(g[e + 4:e + 0xA] + g[e + 0xC:e + 0x80], g[d + 4:d + 0xA] + g[d + 0xC:d + 0x80],
                                 (key, cell))

    def test_strip_gives_back_the_retail_scene(self):
        for key in hs.KEYS:
            g, _ = self.grown[key]
            self.assertEqual(hs.strip_scene(key, g), scene(key))
            self.assertEqual(hs.retail_shaped(key, g), scene(key))

    def test_previous_growth_is_recognised(self):
        for key in hs.KEYS:
            v1, receipt = hs.grow_scene(key, scene(key), numbers=False)
            self.assertFalse(receipt["helmet_number_set_e"])
            self.assertEqual(hs.scene_state(key, v1), "grown_v1")
            self.assertEqual(hs.strip_scene(key, v1), scene(key))

    def test_each_cell_draws_one_patch_on_each_side_of_the_helmet(self):
        gltf = models._tools_module("nfl_scne_gltf")
        for key in hs.KEYS:
            g, _ = self.grown[key]
            p = Parsed(key, g)
            centres = {}
            for name in hs.NUMBER_MATERIALS:
                (row,) = [s for s in p.sc.subs if s["material_name"] == name]
                batches = [b for _m, b in gltf.decode_batches(p.sc.d, row["command_offset"], row["word_count"])]
                self.assertEqual(len(batches), 4, name)            # two bands per patch, two patches
                verts = sorted({v for b in batches for v in b})
                self.assertEqual(len(verts), 18, name)
                P = p.sc.pos[verts]
                left, right = P[P[:, 0] > 0], P[P[:, 0] < 0]
                self.assertEqual((len(left), len(right)), (9, 9), name)
                self.assertTrue((np.abs(P[:, 0]) > 7.0).all(), name)  # on the sides, not the back or the face
                centres[name] = (left.mean(0), right.mean(0))
            (l_left, l_right), (r_left, r_right) = centres["NUMBER_helmet_E_L"], centres["NUMBER_helmet_E_R"]
            # reading order: on the helmet's left side (+X) the tens digit is toward the face (+Z), on the right side
            # (-X) toward the back, so both sides read correctly from outside
            self.assertGreater(l_left[2], r_left[2], key)
            self.assertLess(l_right[2], r_right[2], key)
            # the single-digit cell mirrors across the helmet's centre plane
            m_left, m_right = centres["NUMBER_helmet_E_M"]
            self.assertLess(abs(m_left[0] + m_right[0]), 0.1, key)
            self.assertLess(np.abs(m_left[1:] - m_right[1:]).max(), 0.1, key)

    def test_set_e_records_are_set_d_records_with_new_place_and_digit_coordinates(self):
        for key in hs.KEYS:
            g, _ = self.grown[key]
            p = Parsed(key, g)
            for cell in hs.NUMBER_CELLS:
                d = p.verts(f"NUMBER_helmet_D_{cell}")
                e = p.verts(f"NUMBER_helmet_E_{cell}")
                # same skin selector: the number rides the head like set D's
                self.assertEqual(set(p.sc.sel[e]), set(p.sc.sel[d[:1]]), (key, cell))
                lo, hi = p.sc.uv[d].min(0), p.sc.uv[d].max(0)
                self.assertTrue(((p.sc.uv[e] >= lo - 1e-3) & (p.sc.uv[e] <= hi + 1e-3)).all(), (key, cell))

    def test_every_number_vertex_sits_just_outside_both_shells(self):
        from nfl2k5_helmet_side_numbers_generate import ray_hits
        for key in hs.KEYS:
            g, _ = self.grown[key]
            p = Parsed(key, g)
            shells = {n: p.sc.pos[p.sc.tris({n})] for n in ("HI_HELMET_A", "HI_HELMET_C")}
            for name in hs.NUMBER_MATERIALS:
                for v in p.verts(name):
                    x = p.sc.pos[v]
                    inward = np.array([-np.sign(x[0]), 0.0, 0.0])
                    for shell, tris in shells.items():
                        t, _n = ray_hits(x, inward, tris)
                        self.assertTrue(len(t), (key, name, v, shell))
                        # 0.25 along the surface normal is 0.25 to 0.45 horizontally on the upper side of the shell
                        self.assertGreaterEqual(float(t.min()), 0.2, (key, name, v, shell))
                        self.assertLessEqual(float(t.min()), 0.8, (key, name, v, shell))

    def test_memory_budget_counts_the_growth(self):
        growth = sum(r["growth"] for _g, r in self.grown.values())
        v1 = sum(hs.grow_scene(key, scene(key), numbers=False)[1]["growth"] for key in hs.KEYS)
        self.assertEqual(v1, 26_496 + 9_856)              # the b775-b80 figures the budget carried (84,736 in all)
        self.assertEqual(mb.RESOURCE_BYTES["hair_styles"], 84_736 + growth - v1)


class CollectionTests(unittest.TestCase):
    def test_a_previous_collection_is_regrown_once(self):
        outer3 = retail_outer3()
        new, receipt = hs.compile_collection(outer3)
        self.assertEqual((receipt["status"], hs.collection_status(new)), ("applied", "applied"))
        # the collection a b775-b80 disc carries: the hair-only growth
        chunks = hs._chunks(new)
        replace = {}
        for key in hs.KEYS:
            index = models.parse_model_key(key)[1]
            span = hs._chunk_span(new, chunks[index])
            v1, _ = hs.grow_scene(key, hs.strip_scene(key, hs.decode_span(span)), numbers=False)
            replace[index] = hs.compress_scene(span, v1)
        out, cursor = bytearray(), 0
        for c in chunks:
            out += new[cursor:c.offset]
            span = hs._chunk_span(new, c)
            out += replace.get(c.index, span)
            cursor = c.offset + len(span)
        previous = bytes(out)
        self.assertEqual(hs.collection_status(previous), "previous")
        upgraded, receipt = hs.compile_collection(previous)
        self.assertEqual(receipt["status"], "upgraded")
        self.assertEqual(hs.collection_status(upgraded), "applied")
        self.assertEqual(len(hs._chunks(upgraded)), len(chunks))      # the hair textures are not appended twice
        self.assertEqual(hs.compile_collection(upgraded)[1]["status"], "already_applied")
        self.assertEqual(hs.collection_status(hs.strip_collection(upgraded)), "retail")


@unittest.skipUnless(BASE_XBE and Path(BASE_XBE).is_file(), "NFL2K5_B81_BASE_XBE (a beta 81 standard build) required")
class PreviousCaveTests(unittest.TestCase):
    def test_the_b775_b80_cave_is_upgraded_in_place(self):
        before = Path(BASE_XBE).read_bytes()
        self.assertEqual(hs.status(before), "previous")
        after, receipt = hs.apply(before)
        self.assertEqual(hs.status(after), "applied")
        self.assertEqual(len(after), len(before))
        found = hs.allocation(after)
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(after)
        code_at = image.offset(found["va"], hs.CODE_SIZE)
        in_code = [i for i in changed if code_at <= i < code_at + hs.CODE_SIZE]
        self.assertEqual(len(in_code), 3)                               # the two counts and the sub
        self.assertEqual(hs.apply(after)[0], after)


if __name__ == "__main__":
    unittest.main()
