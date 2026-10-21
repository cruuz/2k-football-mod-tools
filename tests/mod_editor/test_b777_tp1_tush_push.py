"""b777 tp1: Goal Line Sneak at retail spacing, Tush Push pushers in their own lanes, RB play names."""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]

from mod_editor.core import nfl2k5_offense_concepts as oc  # noqa: E402
from mod_editor.core import nfl2k5_offense_modern as om  # noqa: E402

#: Retail minimums over every ordinary retail offense formation (tp1 audit, 976 formations): the QB is never closer
#: than 251 cm to a back and two backs are never closer than 190 cm.
RETAIL_QB_TO_BACK_CM = 251
RETAIL_BACK_TO_BACK_CM = 190
PACKS = sorted((ROOT / "data/playbooks").glob("softdrink_*_modern.2k5book"))


def _backs(pos):
    return [p for p in pos[6:] if p[1] < -50]


class GoalLineSneakSpacing(unittest.TestCase):
    def check(self, pos, label):
        qb, backs = pos[0], _backs(pos)
        self.assertEqual(len(backs), 3, label)
        for b in backs:
            self.assertGreaterEqual(math.dist(qb, b), RETAIL_QB_TO_BACK_CM, (label, b))
        for i, a in enumerate(backs):
            for b in backs[i + 1:]:
                self.assertGreaterEqual(math.dist(a, b), RETAIL_BACK_TO_BACK_CM, (label, a, b))

    def test_generator_formation(self):
        self.check(oc.FORMATIONS["Goal Line Sneak"].positions_cm(), "generator")

    def test_shipped_packs(self):
        self.assertEqual(len(PACKS), 32)
        for path in PACKS:
            doc = json.loads(path.read_text(encoding="utf-8"))
            f = [f for f in doc["formations"] if f["custom_name"] == "Goal Line Sneak"]
            self.assertEqual(len(f), 1, path.name)
            self.check([tuple(p) for p in f[0]["slot_positions"]], path.name)


class TushPushLanes(unittest.TestCase):
    def pusher_ends(self, positions, chains):
        ends = []
        for s, ch in enumerate(chains):
            for op, v in ch or ():
                if op == 0x11 and s >= 6 and positions[s][1] < -50:
                    self.assertEqual(int(v[2]), 1, "pusher legs are relative (their own lane)")
                    self.assertEqual(float(v[5]), 0.0, "pushers drive straight ahead")
                    ends.append((positions[s][0] + v[5], positions[s][1] + v[6]))
        return ends

    def assert_apart(self, ends, label):
        self.assertGreaterEqual(len(ends), 2, label)
        for i, a in enumerate(ends):
            for b in ends[i + 1:]:
                self.assertGreaterEqual(math.dist(a, b), 150, (label, a, b))

    def test_generator_design(self):
        spec = oc.FORMATIONS["Goal Line Sneak"]
        d = om.tush_push(spec.context())
        self.assert_apart(self.pusher_ends(spec.positions_cm(), d.chains), "generator")

    def test_shipped_packs(self):
        n = 0
        for path in PACKS:
            doc = json.loads(path.read_text(encoding="utf-8"))
            plays = {p["id"]: p for p in doc["plays"]}
            for f in doc["formations"]:
                for pid in doc["menus"][f["id"]]:
                    if plays[pid]["concept"] == "Tush Push":
                        pos = [tuple(p) for p in f["slot_positions"]]
                        self.assert_apart(self.pusher_ends(pos, plays[pid]["assignments"]), path.name)
                        n += 1
        self.assertEqual(n, 32)


class RunningBackNames(unittest.TestCase):
    def test_rb_name(self):
        self.assertEqual(om.rb_name("HB Slip Screen Wk"), "RB Slip Screen Wk")
        self.assertEqual(om.rb_name("H-Back Seam"), "H-Back Seam")
        self.assertEqual(om.rb_name("RB2 Wheel"), "RB2 Wheel")
        self.assertEqual(om.rb_name("NYG HBO"), "NYG HBO")

    def test_no_hb_play_names(self):
        for path in sorted((ROOT / "data/playbooks").glob("*.2k5book")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            for p in doc.get("plays", []):
                name = p.get("custom_name") or ""
                self.assertEqual(om.rb_name(name), name, (path.name, name))

    def test_tool_reports_nothing_to_fix(self):
        from pb.v2 import tush_push_spacing as tool
        self.assertEqual(tool.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
