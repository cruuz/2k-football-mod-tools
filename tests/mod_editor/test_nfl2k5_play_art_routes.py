"""b776 pa2: play art routes at their real length (late xbe_space owner, hook 0x181676).

Byte tests use the private USA retail default.xbe; native tests run the game's own play-art draw
path (tools/b77/pa2_play_art_draw.py, Unicorn optional) on the retail CHI book from the private pack.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_play_art_routes as pa  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core import nfl2k5_play_codec as codec  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, HAVE_UC, XBE  # noqa: E402


def retail_book(team="CHI"):
    pack = XBE.parent / "vc_53450030"
    if not pack.exists():
        raise unittest.SkipTest("private USA retail pack is absent")
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with OuterImage(pack) as archive:
        return archive.read_entry(BOOK_ENTRIES[team])


class Wiring(unittest.TestCase):
    def test_recipe_key_presets_and_late_owner(self):
        from mod_editor.core.nfl2k5_build_settings import FEATURE_KEYS
        self.assertIn("play_art_routes", FEATURE_KEYS)
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["play_art_routes"])
        self.assertTrue(mod_build.PRESETS["softdrink_advanced"]["play_art_routes"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["play_art_routes"])
        self.assertTrue(mod_build.BuildPlan("a", "b", play_art_routes=True).wants_xbe_patch())
        self.assertEqual(space.LATE_OWNERS[-12:-1], (pa.OWNER, "nfl2k5_team_number_scale", "nfl2k5_run_blocking", "nfl2k5_qb_accuracy", "nfl2k5_formation_art_spacing", "nfl2k5_force_out", "nfl2k5_practice_injuries", "nfl2k5_ball_carrier_ai", "nfl2k5_star_retention", "nfl2k5_star_career", "nfl2k5_draft_clock"))  # int2: ns1 follows; int7: b777-ol1, then b777-qb3 last
        self.assertIn("play_art_routes", mod_build.availability())

    def test_owned_code_layout(self):
        code = pa.code_bytes()
        self.assertEqual(len(code), pa.CODE_SIZE)
        self.assertEqual(code[pa.DATA_OFFSET - 2:pa.DATA_OFFSET], b"\xcc\xcc")
        # the code addresses its data from the call/pop base at +0x1E: table at base + 0x1A2
        self.assertEqual(code[0x19:0x1F], bytes.fromhex("e800000000") + b"\x5e")
        self.assertIn(bytes.fromhex("8d94d6a2010000"), code)
        self.assertEqual(0x1E + 0x1A2, pa.DATA_OFFSET)
        table = struct.unpack("<14f", code[pa.DATA_OFFSET:pa.DATA_OFFSET + 56])
        for kind, (lat, dep) in enumerate(pa.DIRECTIONS):
            self.assertAlmostEqual(table[2 * kind], lat, places=6)
            self.assertAlmostEqual(table[2 * kind + 1], dep, places=6)
            self.assertAlmostEqual(math.hypot(lat, dep), 1.0, places=6)
        self.assertEqual(code.count(bytes.fromhex("870424ffe0")), 1)  # xchg eax,[esp]; jmp eax (acts as the push)


class Bytes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.after, cls.receipt = pa.apply(cls.retail)

    def test_retail_apply_replay(self):
        self.assertEqual(pa.status(self.retail), "retail")
        self.assertEqual(pa.status(self.after), "applied")
        again, receipt = pa.apply(self.after)
        self.assertEqual(again, self.after)
        self.assertTrue(receipt["already_applied"])
        image = XbeImage(self.after)
        row = pa.allocation(self.after)
        self.assertEqual(image.read(row["va"], pa.CODE_SIZE), pa.code_bytes())
        self.assertEqual(image.read(pa.HOOK_VA, 5), b"\xe8" + struct.pack("<i", row["va"] - pa.HOOK_VA - 5))

    def test_only_the_hook_changes_in_retail_code(self):
        before, after = XbeImage(self.retail), XbeImage(self.after)
        text = next(s for s in before.sections if s.name == ".text")
        a = before.read(text.start, text.raw_size)
        b = after.read(text.start, text.raw_size)
        diff = [text.start + i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        self.assertTrue(diff and min(diff) >= pa.HOOK_VA and max(diff) < pa.HOOK_VA + 5, [hex(v) for v in diff])

    def test_appends_after_an_installed_allocator_without_moving_owners(self):
        grown, _ = space.apply(self.retail, (), scaleout=True)
        before = {r["owner"]: (r["va"], r["size"]) for r in space.layout(grown)["allocations"]}
        after, _ = pa.apply(grown)
        rows = {r["owner"]: (r["va"], r["size"]) for r in space.layout(after)["allocations"]}
        self.assertTrue(all(rows[k] == v for k, v in before.items()))
        self.assertEqual(pa.status(after), "applied")

    def test_foreign_bytes_are_refused(self):
        buf = bytearray(self.retail)
        off = XbeImage(self.retail).offset(0x181650)
        buf[off] ^= 1
        self.assertEqual(pa.status(bytes(buf)), "foreign")
        with self.assertRaises(ValueError):
            pa.apply(bytes(buf))
        buf = bytearray(self.retail)
        off = XbeImage(self.retail).offset(pa.HOOK_VA)
        buf[off:off + 5] = b"\x90" * 5
        self.assertEqual(pa.status(bytes(buf)), "foreign")
        with self.assertRaises(ValueError):
            pa.apply(bytes(buf))


@unittest.skipUnless(HAVE_UC, "Unicorn is an optional test dependency")
class Native(unittest.TestCase):
    """The game's own draw path on real retail plays, before vs after."""

    @classmethod
    def setUpClass(cls):
        import b77.pa2_play_art_draw as art
        from mod_editor.core import nfl2k5_playbook_inspector as inspector
        cls.art = art
        cls.retail = retail_bytes()
        cls.after = pa.apply(cls.retail)[0]
        cls.raw = retail_book("CHI")
        cls.book = inspector.parse_playbook_resource(cls.raw)

    def _pair(self, formation, play, flip=0):
        fi, pi = self.art.find_play(self.book, formation, play)
        return (self.art.draw(self.retail, self.raw, fi, pi, flip=flip),
                self.art.draw(self.after, self.raw, fi, pi, flip=flip))

    def _final_lines(self, result):
        """slot -> (start, end) of the main (non-shadow) line of the chain's capped final route segment."""
        out = {}
        for slot, (_desc, nodes) in enumerate(result["chains"]):
            if not nodes:
                continue
            last = codec.Node.from_bytes(nodes[-1])
            if last.op != 0x12 or int(last.operands[0]) > 6 or last.operands[2] <= 304.8:
                continue
            quads = [p for p in result["prims"] if p["slot"] == slot and p["node"] == len(nodes) - 1
                     and not p["shadow"] and p["kind"] != "mark"]
            if quads:
                v = quads[0]["v"]  # the line quad: two start corners, two end corners
                out[slot] = (last, v)
        return out

    def _check_play(self, formation, play, flip=0):
        before, after = self._pair(formation, play, flip)
        self.assertEqual(before["errors"], after["errors"])
        self.assertEqual(len(before["prims"]), len(after["prims"]))
        finals_b, finals_a = self._final_lines(before), self._final_lines(after)
        changed_slots = set()
        for pb, pa_ in zip(before["prims"], after["prims"]):
            if pb["v"] != pa_["v"]:
                changed_slots.add(pa_["slot"])
                nodes = after["chains"][pa_["slot"]][1]
                self.assertEqual(pa_["node"], len(nodes) - 1, "only the final route segment may change")
                if not pa_["shadow"]:
                    self.assertTrue(all(self.art.inside_panel(x, z) for x, _y, z in pa_["v"]),
                                    f"{play} slot {pa_['slot']} leaves the panel")
        lengths = {}
        for slot, (node, v) in finals_a.items():
            def length(quad):
                (x0, _, z0), (x1, _, z1), (x2, _, z2), (x3, _, z3) = quad
                return math.hypot((x2 + x3 - x0 - x1) / 2, (z2 + z3 - z0 - z1) / 2)
            lb, la = length(finals_b[slot][1]), length(v)
            self.assertAlmostEqual(lb, 304.8, delta=2.0)        # retail: always 10 ft (line quad within 2 cm)
            self.assertGreaterEqual(la, lb - 2.0)               # never shorter than retail
            self.assertLessEqual(la, node.operands[2] + 2.0)    # never longer than authored
            lengths[slot] = la
        return changed_slots, lengths

    def test_go_routes_reach_up_the_panel(self):
        for formation, play in (("Bunch", "50 H Screen Strong"), ("Bunch", "50 Z Deep Comeback")):
            with self.subTest(play=play):
                changed, lengths = self._check_play(formation, play)
                self.assertTrue(changed)
                self.assertGreater(max(lengths.values()), 3 * 304.8)  # a go drawn to ~12 yd, not 3.3

    def test_drags_cross_the_formation(self):
        for formation, play in (("Bunch", "50 Z Drag Rub"), ("Doubles", "50 Y Seam")):
            with self.subTest(play=play):
                for flip in (0, 1):
                    changed, lengths = self._check_play(formation, play, flip)
                    self.assertTrue(changed)
                    self.assertTrue(any(v > 2 * 304.8 for v in lengths.values()))

    def test_runs_and_blocks_are_unchanged(self):
        for formation, play in (("Bunch", "Weak Dive"), ("Bunch", "Strong Lead T-Toss")):
            with self.subTest(play=play):
                before, after = self._pair(formation, play)
                self.assertEqual([p["v"] for p in before["prims"]], [p["v"] for p in after["prims"]])


if __name__ == "__main__":
    unittest.main()
