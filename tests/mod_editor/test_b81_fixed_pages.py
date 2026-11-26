"""b81 integration task 1 (SportsCenter review S2): the fixed pages above the quarterback span are stepped over by one
loop, not one step-over per lane. Synthetic requests only (no game files)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402

PAGES = space.POST_SPAN_PAGES
FIRST, LAST_END = PAGES[0][1], PAGES[-1][1] + PAGES[-1][2]


def offset(va):
    return va - space.POOL_VA


class FixedPageTable(unittest.TestCase):
    def test_the_table_holds_every_lane_page_in_address_order_above_the_span(self):
        self.assertEqual([owner for owner, _va, _size in PAGES],
                         [space.MODERN_NUMBERS_OWNER, space.AWARDS_OWNER, space.CLASSIC_CROWD_OWNER,
                          space.SPORTSCENTER_NEWS_OWNER, space.SIM_OUTCOMES_OWNER])
        self.assertEqual([va for _owner, va, _size in PAGES], [0x1530000, 0x1531000, 0x1532000, 0x1533000, 0x1534000])
        self.assertGreaterEqual(FIRST, space.FIXED_SPAN_END)
        for (_a, va, size), (_b, next_va, _s) in zip(PAGES, PAGES[1:]):
            self.assertLessEqual(va + size, next_va)
        for owner, _va, _size in PAGES:
            self.assertIn(owner, space.FIXED_PAGE_OWNERS)

    def test_each_page_owner_gets_its_own_page(self):
        for owner, va, _size in PAGES:
            with self.subTest(owner=owner):
                self.assertEqual(space._post_span_pages_at(owner, 0, space.PAGE, space.PAGE), offset(va))


class Straddle(unittest.TestCase):
    def test_an_owner_that_straddles_every_page_lands_after_the_last(self):
        # from the span's end, an owner large enough to cover all five pages at once
        at = space._post_span_pages_at("synthetic_straddler", offset(space.FIXED_SPAN_END), LAST_END - FIRST, 16)
        self.assertEqual(at, offset(LAST_END))

    def test_from_just_below_each_page_an_owner_steps_past_every_page_it_would_touch(self):
        for size in (64, space.PAGE, 3 * space.PAGE, 0x20000):
            for _owner, va, _psize in PAGES:
                with self.subTest(size=size, page=hex(va)):
                    at = space._post_span_pages_at("synthetic", offset(va) - 16, size, 16)
                    for _o, other, other_size in PAGES:
                        self.assertFalse(at < offset(other) + other_size and at + size > offset(other), hex(other))
                    self.assertGreaterEqual(at, offset(va) - 16)

    def test_the_result_does_not_depend_on_the_order_the_pages_are_listed_in(self):
        # the old chain was one pass in the order the lanes merged; the loop rescans until nothing overlaps
        reversed_pages = tuple(reversed(PAGES))
        for start in range(offset(space.FIXED_SPAN_END) - 0x2000, offset(LAST_END) + 0x1000, 0x800):
            for size in (16, space.PAGE + 16, 0x6000):
                with self.subTest(start=hex(start), size=size):
                    self.assertEqual(space._post_span_pages_at("synthetic", start, size, 16),
                                     space._post_span_pages_at("synthetic", start, size, 16, pages=reversed_pages))

    def test_an_owner_clear_of_every_page_does_not_move(self):
        below = offset(FIRST) - 0x100
        self.assertEqual(space._post_span_pages_at("synthetic", below, 0x100, 16), below)
        self.assertEqual(space._post_span_pages_at("synthetic", offset(LAST_END), 0x1000, 16), offset(LAST_END))

    def test_the_planner_places_a_straddler_after_every_fixed_page(self):
        filler = ("aa_synthetic_filler", "code", 0x1529000 - 0x80 - space.POOL_VA - space.PAGE, space.PAGE)
        # larger than the v3 code run holds (as in test_b81_qb_room_owner), so it goes whole to the pool after the filler,
        # reaches the span's end and covers every page above it
        size = max(0x20000, LAST_END - space.FIXED_SPAN_END + 0x1000)
        straddle = ("ab_synthetic_straddle", "code", size, 16)
        rows = space.plan([filler, straddle])["allocations"]
        placed = next(r for r in rows if r["owner"] == straddle[0])
        self.assertEqual(placed["va"], LAST_END)
        for _owner, va, size in PAGES:
            self.assertFalse(placed["va"] < va + size and placed["va"] + placed["size"] > va, hex(va))


if __name__ == "__main__":
    unittest.main()
