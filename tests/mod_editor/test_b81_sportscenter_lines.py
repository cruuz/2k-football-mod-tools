"""b81 sportscenter: SportsCenter's playoff picture and sign-off lines on the 2026 calendar (nfl2k5_sportscenter_lines).

The wrapup director (outer 19) is read from the retail disc (read-only) and its two events are run through a model of
the game's child selection (FUN_00269750 and its readers 0x2695A0/0x2695C0/0x269600/0x269630/0x269660, static
reading), for every combination of the director variables the two events test.

  * the release gate: on the retail director the final picture needs 17 weeks played, says the 2-seed bye line (3277,
    child 43) and calls spot 7 "on the outside looking in" (3284), and the sign-off names the division round after
    18 weeks (fails before: these are the retail bytes);
  * with the owner: everything selectable after N weeks is what retail selected after N-1 (weeks 15 to 23), except
    that child 43 is never selectable and children 50/51 only for spot 8; nothing changes before week 13;
  * the entry pins, idempotence and refusal of a foreign director; the calendar gate on real executables.

Fixtures come only from the environment (copyrighted game data, never in the repository):
  NFL2K5_RETAIL_XISO    the retail disc image (read only)
  NFL2K5_RETAIL_XBE     the retail default.xbe
  NFL2K5_B81_SC_XBE     a beta 81 standard (2026 calendar) executable
"""
from __future__ import annotations

import itertools
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_sportscenter_lines as sl

PICTURE, SIGN_OFF = 182, 165
BYE_LINE, OUTSIDE_LINES = 43, (50, 51)
FINAL_SEED_LINES = (42, 44, 45, 46, 47, 48, 49)
DIVISION_SIGN_OFF = 7


def _path(name):
    value = os.environ.get(name, "")
    if not value or not Path(value).is_file():
        raise unittest.SkipTest(f"{name} is not set to an existing file")
    return Path(value)


class Tree:
    """One fixed-slot package of a DRCT body: the rules, each child's first rule, and the rule blocks."""

    def __init__(self, package: bytes):
        self.p = package
        # relative pointers at +0x0C (tree), +0x10 (rules), +0x14 (each child's first rule): target = field + stored - 1
        fields = {at: at + struct.unpack_from("<I", package, at)[0] - 1 for at in (0x0C, 0x10, 0x14)}
        self.children = struct.unpack_from("<I", self.p, 0)[0]
        count = struct.unpack_from("<H", self.p, 4)[0]
        self.tree = fields[0x0C]
        self.rules = [struct.unpack_from("<HH", self.p, fields[0x10] + 4 * i) for i in range(count)]
        self.initial = [struct.unpack_from("<H", self.p, fields[0x14] + 2 * c)[0] for c in range(self.children)]
        self.starts = list(itertools.accumulate(length for _ins, length in self.rules))

    def _byte(self, pos):
        return self.p[self.tree + pos]

    def _offset(self, pos):
        b = self._byte(pos)
        if b < 0x80:
            return pos + b, pos + 1
        if b & 0x40:
            return pos + (b & 0x3F) + (self._byte(pos + 1) << 6) + (self._byte(pos + 2) << 14) + \
                (self._byte(pos + 3) << 22), pos + 4
        return pos + (b & 0x3F) + (self._byte(pos + 1) << 6), pos + 2

    def _entries(self, pos, op):
        n = 1
        if op & 8:
            n, pos = self._byte(pos), pos + 1
        out = []
        for _ in range(n):
            child, pos = self._byte(pos), pos + 1
            run = 1
            if child & 0x80:
                run, child, pos = child & 0x7F, self._byte(pos), pos + 1
            out += range(child, child + run)
        return out, pos

    def run(self, rule: int, value, at: list, out: set) -> None:
        """Rule ``rule`` with its instruction's value: moves children (``at``) and adds candidates (``out``)."""
        pos = self.starts[rule]
        while True:
            op = self._byte(pos)
            if op == 0xFF:
                return
            pos += 1
            if op & 0x80:                                   # leaf
                if op & 2:                                  # move children to another rule
                    target, pos = self._byte(pos), pos + 1
                    kids, pos = self._entries(pos, op)
                    for c in kids:
                        if c < len(at) and at[c] == rule:
                            at[c] = target
                else:                                       # candidates (bit 2: a chance byte first)
                    if op & 4:
                        pos += 1
                    kids, pos = self._entries(pos, op)
                    out.update(c for c in kids if c < len(at) and at[c] == rule)
                if not op & 1:
                    return
                continue
            if op & 0x20:                                   # signed-byte comparand
                cmp, pos = struct.unpack("b", bytes([self._byte(pos)]))[0], pos + 1
            else:                                           # float comparand
                cmp, pos = struct.unpack_from("<f", self.p, self.tree + pos)[0], pos + 4
            f0, f1, f2, f3, f4 = ((op >> bit) & 1 for bit in range(5))
            if not (f3 or f4):
                eq = gt = None
                if f0 and f1:
                    eq, pos = self._offset(pos)
                if f2:
                    gt, pos = self._offset(pos)
                eq = pos if eq is None else eq
                gt = pos if gt is None else gt
                eq_ok = f1
            else:
                gt = pos
                if f0 and f2:
                    gt, pos = self._offset(pos)
                if f3:
                    eq, eq_ok = pos, f0
                else:
                    eq, eq_ok = gt, f2
            if value < cmp:
                if not f0:
                    return
            elif value == cmp:
                if not eq_ok:
                    return
                pos = eq
            else:
                if not f2:
                    return
                pos = gt

    def outcomes(self, fixed: dict, values) -> set:
        """Every candidate set, with ``fixed`` {instruction: value} and every other instruction over ``values``.
        Only the rules a child reaches are run (the game evaluates a rule's instruction only then)."""
        results = set()

        def walk(rule, at, out):
            if rule == len(self.rules):
                results.add(frozenset(out))
                return
            ins = self.rules[rule][0]
            if rule not in at:
                walk(rule + 1, at, out)
                return
            for value in ((0,) if ins == 0xFFFF else (fixed[ins],) if ins in fixed else values):
                a, o = list(at), set(out)
                self.run(rule, value, a, o)
                walk(rule + 1, a, o)

        walk(0, list(self.initial), set())
        return results


#: the two events' fixed-slot packages in the DRCT body (offset, end) of the pinned retail entry (sl.ENTRY_PINS)
PACKAGES = {PICTURE: (0x5214, 0x5A84), SIGN_OFF: (0x3050, 0x31C8)}


def _trees(entry: bytes) -> dict:
    body = entry[sl.WRAPPER:]
    return {event: Tree(body[start:end]) for event, (start, end) in PACKAGES.items()}


WEEKS_INSTRUCTION = 9          # director variable 65: weeks played (0x15E8D0 = last played week + 1)
SPOT_INSTRUCTION = 57          # director variable 38: the spotlighted club's spot (0x2211F0 = rand % 7 + 1)


def _selectable(tree: Tree, weeks: int) -> dict:
    """child -> set of spots it can be chosen for after ``weeks`` weeks, over every value of the other variables."""
    out: dict[int, set] = {}
    for spot in range(1, 10):
        for outcome in tree.outcomes({WEEKS_INSTRUCTION: weeks, SPOT_INSTRUCTION: spot}, range(-1, 10)):
            for child in outcome:
                out.setdefault(child, set()).add(spot)
    return out


class LinesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = sl.read_entry(_path("NFL2K5_RETAIL_XISO"))
        cls.applied, cls.receipt = sl.patch_entry(cls.retail)
        cls.before, cls.after = _trees(cls.retail), _trees(cls.applied)
        cls.cache = {}

    def _sel(self, which, event, weeks):
        key = (which, event, weeks)
        if key not in self.cache:
            trees = self.before if which == "before" else self.after
            self.cache[key] = _selectable(trees[event], weeks)
        return self.cache[key]

    def test_retail_director_has_the_17_week_six_seed_lines(self):
        """The release gate's failing case: the retail bytes are what the owner fixes."""
        self.assertEqual(sl.entry_state(self.retail), "retail")
        final17 = self._sel("before", PICTURE, 17)
        self.assertIn(2, final17.get(BYE_LINE, set()), "retail: the 2-seed bye line after 17 weeks")
        self.assertIn(7, final17.get(OUTSIDE_LINES[0], set()), "retail: spot 7 is 'on the outside looking in'")
        self.assertFalse(set(FINAL_SEED_LINES) & set(self._sel("before", PICTURE, 18)),
                         "retail: no final picture after 18 weeks")
        self.assertIn(DIVISION_SIGN_OFF, self._sel("before", SIGN_OFF, 18),
                      "retail: 'see you for the division championships' after 18 weeks")

    def test_applied_director_follows_the_2026_calendar(self):
        for event in (PICTURE, SIGN_OFF):
            for weeks in range(0, 13):
                self.assertEqual(self._sel("after", event, weeks), self._sel("before", event, weeks),
                                 f"event {event}, {weeks} weeks: unchanged before the pictures air")
            for weeks in range(15, 24):
                want = {child: set(spots) for child, spots in self._sel("before", event, weeks - 1).items()}
                if event == PICTURE:
                    want.pop(BYE_LINE, None)
                    for child in OUTSIDE_LINES:
                        if child in want:
                            want[child] = {8} if 7 in want[child] else set()
                            if not want[child]:
                                want.pop(child)
                self.assertEqual(self._sel("after", event, weeks), want, f"event {event}, {weeks} weeks played")
        for weeks in range(0, 24):
            picture = self._sel("after", PICTURE, weeks)
            self.assertNotIn(BYE_LINE, picture, f"{weeks} weeks: the 2-seed bye line is selectable")
            for child in OUTSIDE_LINES:
                self.assertLessEqual(picture.get(child, set()), {8}, f"{weeks} weeks: child {child} for a seed")
            if set(FINAL_SEED_LINES) & set(picture):
                self.assertEqual(weeks, 18, "the final picture airs only after Week 18")
        self.assertEqual(set(self._sel("after", SIGN_OFF, 19)) - set(self._sel("after", SIGN_OFF, 17)),
                         {DIVISION_SIGN_OFF})

    def test_pins_idempotence_and_refusal(self):
        self.assertEqual(self.receipt["changed_bytes"], sl.CHANGED_BYTES)
        self.assertEqual(sl.CHANGED_BYTES, 11)
        self.assertEqual(sl.entry_state(self.applied), "applied")
        again, receipt = sl.patch_entry(self.applied)
        self.assertEqual(again, self.applied)
        self.assertTrue(receipt["already_applied"])
        changed = [i for i, (a, b) in enumerate(zip(self.retail, self.applied)) if a != b]
        self.assertEqual(changed, sorted(sl.WRAPPER + s.body_offset + k for s in sl.SITES for k in range(len(s.retail))))
        foreign = bytearray(self.retail)
        foreign[0x100] ^= 1
        self.assertEqual(sl.entry_state(bytes(foreign)), "foreign")
        with self.assertRaises(sl.SportsCenterLinesError):
            sl.patch_entry(bytes(foreign))
        with self.assertRaises(sl.SportsCenterLinesError):
            sl.patch_entry(self.retail[:-1])

    def test_calendar_gate(self):
        self.assertFalse(sl.wanted(_path("NFL2K5_RETAIL_XBE").read_bytes()), "retail calendar: retail lines stay")
        self.assertTrue(sl.wanted(_path("NFL2K5_B81_SC_XBE").read_bytes()), "18 weeks and seven seeds")


if __name__ == "__main__":
    unittest.main()
