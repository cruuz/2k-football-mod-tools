"""Beta 81 D07: the CPU fourth-down go limit must rise smoothly with field position.

The first beta 81 cap lowered the Modern 2 table only from the own 20 to the own 49, in bands that did not line up with the
table's region boundary at the own 40. In the shipped 128 MiB v0.10 executable a tied first quarter with 7-minute quarters
punted on 4th-and-3 at the own 49 but went for it on 4th-and-6 at the 50, and went on 4th-and-2 at the own 39 but punted
it at the own 40 to 44. The current table (FOURTH_DOWN_GO_LIMITS and FOURTH_DOWN_SHIFT_CHANGES in
nfl2k5_cpu_money_downs.py) must satisfy, in every one-score game state of quarters 1 to 3:
  * the longest distance the CPU goes for never shrinks as the offense advances from its own 20 to the opponent 41,
  * and never rises by more than one yard between adjacent yard lines.
It must also keep the five reported punts, every 4th-and-1 attempt the first beta 81 table made, the published chart and
field-goal region inside the opponent 40, the late-game rules, and the published score/clock direction.
Quarter lengths 2 to 15 minutes are covered. With 1-minute quarters the third quarter is inside the game's last two
minutes, whose published late-game cells are deliberately unchanged.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cpu_money_downs as patch

YARDS = range(20, 60)   # own 20 .. opponent 41; inside the opponent 40 the field-goal region legitimately differs
QUARTER_LENGTHS = (120, 180, 300, 420, 600, 900)
SECONDS = (400, 330, 240, 150, 61)


def neutral_states():
    for quarter_seconds in QUARTER_LENGTHS:
        for quarter in (1, 2, 3):
            for seconds in SECONDS:
                if seconds > quarter_seconds or (quarter == 2 and seconds <= 120):
                    continue      # no such clock, or the first half's last two minutes (retail by design)
                for margin in range(-8, 9):
                    yield dict(quarter=quarter, seconds=seconds, score_margin=margin, quarter_seconds=quarter_seconds)


def go_limit(own_yard, state, tables=None):
    """Longest distance (yards) Modern 2 goes for at this spot; 0 = never."""
    best = 0
    original = patch.m2_tables
    if tables is not None:
        patch.m2_tables = lambda variant=None: original(tables)
    try:
        for distance in range(1, 26):
            if patch.decision(level="modern2", down=4, own_yard=own_yard, distance=distance, **state) != "go":
                break
            best = distance
    finally:
        patch.m2_tables = original
    return best


class FourthDownShapeTests(unittest.TestCase):
    def test_go_limit_rises_by_at_most_one_yard_and_never_drops_in_a_one_score_game(self):
        problems = []
        for state in neutral_states():
            limits = [go_limit(y, state) for y in YARDS]
            for i in range(1, len(limits)):
                step = limits[i] - limits[i - 1]
                if not 0 <= step <= 1:
                    problems.append((state, YARDS[i], limits[i - 1], limits[i]))
        self.assertEqual(problems[:10], [], f"{len(problems)} steps outside 0..1")

    def test_reported_d07_spots_still_punt(self):
        q1 = dict(quarter=1, seconds=400, score_margin=0)
        q3 = dict(quarter=3, seconds=330, score_margin=0)
        for quarter_seconds in (420, 900):
            for state, yard, distance in ((q1, 40, 4), (q1, 48, 5), (q1, 49, 5), (q3, 48, 7), (q3, 49, 7)):
                with self.subTest(quarter_seconds=quarter_seconds, yard=yard, distance=distance, **state):
                    self.assertEqual(patch.decision(level="modern2", down=4, own_yard=yard, distance=distance,
                                                    quarter_seconds=quarter_seconds, **state), "retail")

    def test_reported_midfield_neighbour_is_consistent_with_the_fix(self):
        state = dict(quarter=1, seconds=240, score_margin=0, quarter_seconds=420)
        self.assertEqual(patch.decision(level="modern2", down=4, own_yard=49, distance=5, **state), "retail")
        for yard in (50, 51):
            self.assertEqual(patch.decision(level="modern2", down=4, own_yard=yard, distance=6, **state), "retail")

    def test_every_fourth_and_one_the_first_beta81_table_went_for_still_goes(self):
        lost = []
        for quarter_seconds in (120, 300, 420, 900):
            for quarter in (1, 2, 3, 4):
                for seconds in (400, 300, 200, 130, 100, 30):
                    if seconds > quarter_seconds:
                        continue
                    for margin in range(-20, 21):
                        state = dict(quarter=quarter, seconds=seconds, score_margin=margin, quarter_seconds=quarter_seconds,
                                     kick_range=50, timeouts=3, defense_points=7, punt_roll=0.5)
                        for yard in range(1, 100):
                            kwargs = dict(level="modern2", down=4, own_yard=yard, distance=1, **state)
                            original = patch.m2_tables
                            patch.m2_tables = lambda variant=None: original("b81_late")
                            try:
                                before = patch.decision(**kwargs)
                            finally:
                                patch.m2_tables = original
                            if before == "go" and patch.decision(**kwargs) != "go":
                                lost.append((quarter, seconds, margin, quarter_seconds, yard))
        self.assertEqual(lost[:10], [], f"{len(lost)} fourth-and-one attempts lost")

    def test_field_goal_region_late_cells_and_published_direction_are_unchanged(self):
        limit, shift, thr = patch.m2_tables()
        published_limit, published_shift, published_thr = patch.m2_tables("b778")
        self.assertEqual(limit[:41], published_limit[:41])            # opponent 40 and in
        self.assertEqual(thr, published_thr)                          # two-point chart
        changed = {i for i in range(len(shift)) if shift[i] != published_shift[i]}
        self.assertEqual(changed, {(c * 7 + m) * 3 + r for c, m, r in patch.FOURTH_DOWN_SHIFT_CHANGES})
        for index in changed:
            clock, rest = divmod(index, 21)
            margin, region = divmod(rest, 3)
            self.assertLess(clock, 5, "the last two minutes keep the published cells")
            self.assertNotEqual(region, 2, "the field-goal region keeps the published cells")
        for clock in range(6):
            for region in range(3):
                column = [shift[(clock * 7 + m) * 3 + region] for m in range(7)]
                published = [published_shift[(clock * 7 + m) * 3 + region] for m in range(7)]
                for m in range(6):
                    if published[m] >= published[m + 1]:
                        self.assertGreaterEqual(column[m], column[m + 1], (clock, region, column))

    def test_last_two_minute_trailing_rules_are_unchanged(self):
        original = patch.m2_tables
        for margin in (-17, -8, -3, -1):
            for yard in (20, 35, 45, 55, 70):
                for distance in (1, 4, 9, 15):
                    for timeouts, points, roll in ((3, 7, 0.2), (2, 14, 0.9)):
                        state = dict(level="modern2", down=4, own_yard=yard, distance=distance, score_margin=margin,
                                     quarter=4, seconds=100, quarter_seconds=420, kick_range=50, timeouts=timeouts,
                                     defense_points=points, punt_roll=roll)
                        now = patch.decision(**state)
                        patch.m2_tables = lambda variant=None: original("b81_late")
                        try:
                            before = patch.decision(**state)
                        finally:
                            patch.m2_tables = original
                        self.assertEqual(now, before, state)


class UpgradeInPlaceTests(unittest.TestCase):
    """Beta 80 (b778_late) and first beta 81 (b81_late) installs upgrade inside the same allocations; foreign bytes refuse."""

    @classmethod
    def setUpClass(cls):
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
        from mod_editor.core import nfl2k5_xbe_space as space
        cls.space = space
        try:
            cls.retail = retail_xbe()
        except unittest.SkipTest:
            raise
        cls.fresh, cls.receipt = patch.apply(cls.retail, level="modern2")

    def older(self, variant):
        main, late, state = patch._main_row(self.fresh), patch._late_row(self.fresh), patch._late_state_row(self.fresh)
        current = patch.code_for(main["va"], "modern2", variant=patch.CURRENT_LATE, late_va=late["va"], state_va=state["va"])
        old = patch.code_for(main["va"], "modern2", variant=variant, late_va=late["va"], state_va=state["va"])
        payload, _ = self.space.install_code(self.fresh, patch.OWNER, old, previous=current)
        if variant not in patch.FAKE_VARIANTS:
            # An install before beta 81's fake-kick gate (b81f): that template's own hook displacements (its labels
            # differ from the gated template's) and the retail bytes at the gate's three sites.
            from mod_editor.core import nfl2k5_rdata_sites as rdata
            from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
            buf = bytearray(payload)
            touched = set()
            writes = [(hook, after) for _name, hook, _before, after in patch.sites(main["va"], "modern2", variant=variant)]
            writes += [(hook, before) for _name, hook, before, _after in patch._fake_sites()]
            for hook, data in writes:
                off = rdata.offset_of(payload, hook)
                buf[off:off + len(data)] = data
                touched.add(next(s.index for s in _sections(payload) if s.raw_offset <= off < s.raw_offset + s.raw_size))
            for section in _sections(payload):
                if section.index in touched:
                    buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
            payload = bytes(buf)
        return payload

    def test_fresh_install_is_the_current_table(self):
        self.assertEqual(self.receipt["variant"], patch.CURRENT_LATE)
        self.assertEqual(patch.read_settings(self.fresh)["variant"], patch.CURRENT_LATE)
        again, receipt = patch.apply(self.fresh, level="modern2")
        self.assertEqual(again, self.fresh)
        self.assertTrue(receipt["already_applied"])

    def test_beta80_and_first_beta81_installs_upgrade_in_place(self):
        for variant in ("b81s_late", "b81_late", "b778_late"):
            with self.subTest(variant=variant):
                old = self.older(variant)
                self.assertEqual(patch.read_settings(old)["variant"], variant)
                self.assertEqual(patch.status(old), "applied")
                upgraded, receipt = patch.apply(old, level="modern2")
                self.assertEqual(receipt["from_variant"], variant)
                self.assertEqual(receipt["variant"], patch.CURRENT_LATE)
                self.assertEqual(upgraded, self.fresh)

    def test_foreign_table_bytes_refuse(self):
        main = patch._main_row(self.fresh)
        labels = patch._m2(patch.CURRENT_LATE)[2]
        for variant in (patch.CURRENT_LATE, "b81_late"):
            with self.subTest(variant=variant):
                base = self.fresh if variant == patch.CURRENT_LATE else self.older(variant)
                bad = bytearray(base)
                bad[main["raw"] + labels["limit_x"] + 55] ^= 1          # own 45 entry
                self.assertEqual(patch.status(bytes(bad)), "foreign")
                with self.assertRaises(ValueError):
                    patch.apply(bytes(bad), level="modern2")


if __name__ == "__main__":
    unittest.main()
