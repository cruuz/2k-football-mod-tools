"""b81 sportscenter: SportsCenter news for the mod's injuries (nfl2k5_sim_rb_injuries news row, nfl2k5_sportscenter_news).

Owner: static recognition, states and idempotence on real executables (retail, the released v0.8 and v0.9, and the
beta 81 standard candidate), the page and the sites.

Franchise image (Unicorn): a kept stage-8 franchise image (week-10 kickoff, 2026) on the executable it was made with,
then the same image with this branch's owners applied to that executable (the owners' bytes written over the image's
copy of the original executable). The game's own weekly tick 0x133C50 and the injury segment's begin 0x21E2E0 run
natively; the test reads the news ledger at 0xE3F070 and the segment's lists.
  * the halfback roll posts one kind-10 row per halfback it hurts, with his club (fails before: no row at all);
  * the Injured Reserve page holds only season-ending placements (the game's own duration class 0x21DA50 >= 2), and
    every other injured man is listed with his own club (fails before: every placement of the week on the IR page,
    an IR player off his club filed under the last club walked).
Loader (Unicorn): the front-office loader's span at 0x2D0EE3 restores both saved window starts (fails before: they
stay where they were, 0 after a cold load).

Fixtures come only from the environment (copyrighted game data, never in the repository):
  NFL2K5_RETAIL_XBE                 the retail default.xbe
  NFL2K5_B81_SC_XBE                 the beta 81 standard candidate p2-candidate-9edd1353.xbe
  NFL2K5_B81_SC_IMAGE               its kept image no-qb-2505-2026-w10-kickoff.b81mem.gz
  NFL2K5_V08_XBE, NFL2K5_V09_RELEASED_XBE   the released v0.8 and v0.9 executables (previous revisions)
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import unittest

from mod_editor.core import nfl2k5_sim_rb_injuries as rb
from mod_editor.core import nfl2k5_sportscenter_news as sc
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

CANDIDATE_SHA = "9edd1353bedfbca6b4ce35faa2acc3cb68b8a74521d3313e3b1873e6b12c7c3d"
IMAGE_SHA = "1f725ff50fe01e920bd5043892b597901c8ce0665de8f56ab839522d1bef1b4e"
LEDGER, CURSOR, THIS_WINDOW, LAST_WINDOW = 0xE3F070, 0xE3F06C, 0xE3F064, 0xE3F068
LEAGUE_TYPE = 0xE576A0     # read by 0xC4B80: 2 = franchise
IR_PAGE, MAJOR, NFC, AFC, NFL = 0xC13C90, 0xC13CCC, 0xC13CD8, 0xC13D14, 0xC13D50


def _fixture(name, digest=None):
    value = os.environ.get(name, "")
    path = Path(value) if value else None
    if path is None or not path.is_file():
        raise unittest.SkipTest(f"{name} is not set to an existing file")
    data = path.read_bytes()
    if digest is not None and hashlib.sha256(data).hexdigest() != digest:
        raise unittest.SkipTest(f"{name} is not the pinned file")
    return path, data


def _have_unicorn():
    try:
        import unicorn  # noqa: F401
    except ImportError:
        return False
    return True


def _section_diffs(original: bytes, new: bytes):
    """(va, bytes) runs where the executable ``new`` differs from ``original`` (grown sections: their new tails)."""
    a, b = XbeImage(original), XbeImage(new)
    out = []
    for s in b.sections:
        if not s.raw_size:
            continue
        nb = b.read(s.start, s.raw_size)
        old = next((t for t in a.sections if t.start == s.start), None)
        if old is None:
            out.append((s.start, nb))
            continue
        ob = a.read(s.start, min(old.raw_size, s.raw_size))
        if len(ob) < len(nb):
            out.append((s.start + len(ob), nb[len(ob):]))
            nb = nb[:len(ob)]
        i = 0
        while i < len(nb):
            if nb[i] == ob[i]:
                i += 1
                continue
            j = i
            while j < len(nb) and nb[j] != ob[j]:
                j += 1
            out.append((s.start + i, nb[i:j]))
            i = j
    return out


class _Franchise:
    """The kept image on ``xbe``: the image's RAM, then ``xbe``'s own changes over the image's copy of the original."""

    def __init__(self, xbe: bytes, original: bytes, regions):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        self.m = m = Machine(xbe, trace_writes=False)
        for lo, data in regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        for va, blob in _section_diffs(original, xbe):
            m.uc.mem_write(va, blob)
        m.uc.ctl_flush_tb()

    def u8(self, at):
        return self.m.uc.mem_read(at, 1)[0]

    def get(self, at):
        return self.m.get(at)

    def clubs(self):
        count = self.m.call(0xC6430)
        return [self.m.call(0xC4C50, ecx=i) for i in range(min(count, 32))]

    def roster(self, club):
        return [self.get(club + 4 * k) for k in range(self.u8(club + 0x11C))]

    def health(self, player):
        return self.get(player + 0x20), self.get(player + 0x24)

    def rows(self, start, end):
        out = []
        i = start
        while i != end:
            at = LEDGER + 12 * i
            out.append((self.get(at) & 31, self.get(at + 4), self.get(at + 8)))
            i = (i + 1) % 600
        return out

    def raw_rows(self, start, end):
        """(dword0, player, club) per row: dword0 = kind | a16 << 5 | (b10 & 0x3FF) << 21 | last << 31 (0x2BFDF0)."""
        out = []
        i = start
        while i != end:
            at = LEDGER + 12 * i
            out.append((self.get(at), self.get(at + 4), self.get(at + 8)))
            i = (i + 1) % 600
        return out

    def entries(self, base, count):
        return [(self.get(base + 12 * k), self.get(base + 12 * k + 4)) for k in range(count) if self.get(base + 12 * k)]

    def duration_class(self, player):
        return self.m.call(0x21DA50, args=(player,), budget=2_000_000)


@unittest.skipUnless(_have_unicorn(), "unicorn is not installed")
class FranchiseImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools import franchise_invariants as fi
        _path, cls.original = _fixture("NFL2K5_B81_SC_XBE", CANDIDATE_SHA)
        image, _ = _fixture("NFL2K5_B81_SC_IMAGE", IMAGE_SHA)
        cls.regions = fi.load_memory(image).regions
        cls.patched = sc.apply(rb.apply(cls.original)[0])[0]

    def _tick(self, xbe, league_type=None):
        f = _Franchise(xbe, self.original, self.regions)
        if league_type is not None:
            f.m.uc.mem_write(LEAGUE_TYPE, struct.pack("<I", league_type))
        backs = {}
        for club in f.clubs():
            for p in f.roster(club):
                if f.u8(p + 0x35) == 7:
                    backs[p] = (club, f.health(p))
        start = f.get(CURSOR)
        f.m.call(0x133C50, budget=50_000_000)
        rolled = {p: club for p, (club, (w20, w24)) in backs.items()
                  if not w20 & 0xBFC00000 and not w24 & 0x70000000
                  and f.get(p + 0x20) >> 31 and (f.get(p + 0x24) >> 28) & 7 == 4}
        self.last_raw = f.raw_rows(start, f.get(CURSOR))
        return f, rolled, f.rows(start, f.get(CURSOR))

    def test_the_halfback_roll_posts_one_injury_row_per_back_it_hurts(self):
        self.assertEqual(rb.status(self.original), "previous")      # the beta-80 / v0.9 cave, no news row
        _f, rolled, rows = self._tick(self.patched)
        self.assertTrue(rolled, "the kept image's next tick rolls no halfback (the image changed?)")
        self.assertEqual(sorted((p, c) for k, p, c in rows if k == 10), sorted(rolled.items()))
        self.assertEqual([k for k, _p, _c in rows], [10] * len(rolled))

    def test_the_news_row_fields_are_the_merge_poster_s(self):
        """0x247160's row, as the end-of-game merge posts it: kind 10, a16 = min((w >> 10) & 7, w >> 13) of the player's
        word +0x28, b10 = 0, last = 1, the club the roll walked."""
        f, rolled, _rows = self._tick(self.patched)
        self.assertTrue(rolled)
        self.assertEqual(len(self.last_raw), len(rolled))
        for dword0, player, club in self.last_raw:
            word = f.get(player + 0x28) & 0xFFFF
            self.assertEqual(dword0 & 31, 10)
            self.assertEqual((dword0 >> 5) & 0xFFFF, min((word >> 10) & 7, word >> 13), f"{player:#x}: a16")
            self.assertEqual((dword0 >> 21) & 0x3FF, 0)
            self.assertEqual(dword0 >> 31, 1)
            self.assertEqual(club, rolled[player])

    def test_outside_franchise_mode_the_roll_posts_no_row(self):
        """The stub posts only when 0xC4B80 (the league type [0xE576A0]) reads 2, franchise: the tick also runs in other
        modes (the retail tick tests 2 itself at 0x133C8C)."""
        f = _Franchise(self.patched, self.original, self.regions)
        self.assertEqual(f.get(LEAGUE_TYPE), 2)
        for league_type in (0, 1):
            with self.subTest(league_type=league_type):
                _f, rolled, rows = self._tick(self.patched, league_type=league_type)
                self.assertTrue(rolled, "the roll itself runs outside franchise mode too")
                self.assertEqual([r for r in rows if r[0] == 10], [])

    def test_a_return_in_the_super_bowl_week_is_not_season_ending(self):
        """Review N3: FUN_0021da50 (the class R2a reads) calls a player back after the Super Bowl from the return week
        weeks played + weeks out >= 22 (17 + 5). With 18 weeks the Super Bowl is week 22, so a return then read "out for
        the season" (class 3). nfl2k5_season_length.repair_injury_season_end moves the boundary to 23 (class 1 then)."""
        from mod_editor.core import nfl2k5_season_length as season
        repaired, receipt = season.repair_injury_season_end(self.patched)
        self.assertEqual((receipt["before"], receipt["return_week"], receipt["already_applied"]), (22, 23, False))
        for xbe, at_22 in ((self.patched, 3), (repaired, 1)):
            f = _Franchise(xbe, self.original, self.regions)
            played = f.m.call(0x15E8D0)
            player = next(p for club in f.clubs() for p in f.roster(club)
                          if not f.get(p + 0x20) & 0xBFC00000 and not f.get(p + 0x24) & 0x70000000)
            for back, expected in ((21, 1), (22, at_22), (23, 3)):
                with self.subTest(boundary=22 if xbe is self.patched else 23, return_week=back):
                    word = (f.get(player + 0x20) & ~0x3FC00000) | 0x80000000 | ((back - played) << 22)
                    f.m.uc.mem_write(player + 0x20, struct.pack("<I", word))
                    self.assertEqual(f.duration_class(player), expected)

    def test_a_preseason_injury_counts_the_four_preseason_weeks(self):
        """Review N8: in the Preseason stage (7) FUN_0021da50 turns preseason weeks played into regular-season weeks
        with lea edi,[eax+esi-5] (retail's 5 preseason weeks). The 2026 preseason is 4 weeks (stage table 0x5151B4),
        so a back hurt for 18 weeks after the last preseason week misses all 18 regular weeks: "rest of the regular
        season" (class 1). With -5 he read 1 week short (class 0)."""
        from mod_editor.core import nfl2k5_season_length as season
        repaired, receipt = season.repair_injury_season_end(self.patched)
        self.assertEqual((receipt["preseason_weeks"], receipt["preseason_before"]), (4, -5))
        for xbe, expected in ((self.patched, 0), (repaired, 1)):
            with self.subTest(offset=-5 if xbe is self.patched else -4):
                f = _Franchise(xbe, self.original, self.regions)
                f.m.uc.mem_write(0xE576A4, struct.pack("<I", 7))           # the Preseason stage
                f.m.uc.mem_write(0xE576B0, struct.pack("<I", 4))           # its row bound (stage table row 7 +4)
                self.assertEqual(f.m.call(0x15E8D0), 4)                     # all four preseason weeks played
                player = next(p for club in f.clubs() for p in f.roster(club)
                              if not f.get(p + 0x20) & 0xBFC00000 and not f.get(p + 0x24) & 0x70000000)
                word = (f.get(player + 0x20) & ~0x3FC00000) | 0x80000000 | (18 << 22)
                f.m.uc.mem_write(player + 0x20, struct.pack("<I", word))
                self.assertEqual(f.duration_class(player), expected)

    def test_before_the_news_row_the_roll_posted_nothing(self):
        _f, rolled, rows = self._tick(self.original)
        self.assertTrue(rolled)
        self.assertEqual(rows, [])                                  # what SportsCenter never saw

    def _segment(self, xbe):
        f = _Franchise(xbe, self.original, self.regions)
        f.m.call(0x21E2E0, ecx=0, budget=200_000_000)
        return f

    def test_the_ir_page_keeps_only_season_ending_placements_and_everyone_else_is_listed_with_his_club(self):
        f = self._segment(self.patched)
        page = f.entries(IR_PAGE, 5)
        for player, _club in page:
            self.assertGreaterEqual(f.duration_class(player), 2, "a short IR stint on the season-ending page")
        on_roster = {p: club for club in f.clubs() for p in f.roster(club)}
        rows = {p: c for k, p, c in f.rows(f.get(LAST_WINDOW), f.get(CURSOR)) if k == 10}
        listed = f.entries(MAJOR, 1) + f.entries(NFC, 5) + f.entries(AFC, 5) + f.entries(NFL, 5)
        self.assertTrue(listed)
        for player, club in listed:
            self.assertNotIn(player, [p for p, _c in page])
            self.assertEqual(club, on_roster.get(player, rows.get(player)), f"{player:#x} under the wrong club")
        # this window's short-stint placements (off their clubs, on modern IR) are now on the lists
        placed = {p: c for k, p, c in f.rows(f.get(THIS_WINDOW), f.get(CURSOR)) if k == 12}
        short = [p for p in placed if p in rows and f.duration_class(p) < 2]
        self.assertTrue(short, "the kept image has no short-stint placement this window")
        names = {p for p, _c in listed}
        self.assertTrue(set(short) & names)

    def test_before_the_fix_short_stints_were_on_the_season_ending_page(self):
        f = self._segment(self.original)
        page = f.entries(IR_PAGE, 5)
        self.assertTrue(any(f.duration_class(p) < 2 for p, _c in page))


@unittest.skipUnless(_have_unicorn(), "unicorn is not installed")
class LoaderTests(unittest.TestCase):
    """The loader span 0x2D0EE3..0x2D0EEE alone, on a front-office block in the fixture arena."""

    @classmethod
    def setUpClass(cls):
        _path, cls.original = _fixture("NFL2K5_B81_SC_XBE", CANDIDATE_SHA)
        cls.patched = sc.apply(cls.original)[0]

    def _load(self, xbe, saved):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(xbe, trace_writes=False)
        block = m.ARENA + 0x1000
        m.uc.mem_write(block + 0x3324, struct.pack("<III", *saved))
        for at in (THIS_WINDOW, LAST_WINDOW, CURSOR):
            m.put(at, 0)
        m.reg("EBP", block)
        m.reg("ESP", m.STACK)
        m.uc.emu_start(0x2D0EE3, 0x2D0EEE, count=10_000)
        return m.get(THIS_WINDOW), m.get(LAST_WINDOW), m.get(CURSOR)

    def test_both_window_starts_come_back_from_the_save(self):
        self.assertEqual(self._load(self.patched, (367, 332, 408)), (367, 332, 408))
        self.assertEqual(self._load(self.patched, (590, 20, 31)), (590, 20, 31))   # across the wrap

    def test_a_value_that_is_no_ring_slot_keeps_retail_behaviour(self):
        self.assertEqual(self._load(self.patched, (600, 332, 408)), (0, 0, 408))
        self.assertEqual(self._load(self.patched, (367, 0xFFFFFFFF, 408)), (0, 0, 408))

    def test_before_the_fix_only_the_cursor_came_back(self):
        self.assertEqual(self._load(self.original, (367, 332, 408)), (0, 0, 408))


class OwnerTests(unittest.TestCase):
    """Recognition and install on real executables."""

    def test_page_and_sites(self):
        # the page claimed in the lanes' page register (0x152E000..0x152FFFF is the CPU trades owner's); its own
        # step-over, the quarterback span untouched
        self.assertEqual((space.SPORTSCENTER_NEWS_VA, space.SPORTSCENTER_NEWS_SIZE), (0x1533000, space.PAGE))
        self.assertEqual(sc.REQUESTS, (space.SPORTSCENTER_NEWS_REQUEST,))
        self.assertIn(space.SPORTSCENTER_NEWS_REQUEST, space.dormant_union())     # review S1: the manifest's union
        self.assertIn(sc.OWNER, space.FIXED_PAGE_OWNERS)
        self.assertEqual(space.FIXED_SPAN_END, space.HELMET_SIDES_VA + space.HELMET_SIDES_SIZE)
        self.assertEqual(space.LATE_OWNERS[-4:], (sc.OWNER, space.QB_ROOM_OWNER, space.QB_TRADES_OWNER,
                                                  space.HELMET_SIDES_OWNER))
        va = space.SPORTSCENTER_NEWS_VA
        self.assertEqual([s[1] for s in sc.sites(va, 0)], [sc.RELOAD_VA])
        self.assertEqual([s[1] for s in sc.sites(va, sc.MODE_IR)], [sc.RELOAD_VA, sc.IR_PAGE_VA, sc.IR_SKIP_VA, sc.CLUB_VA])
        for _label, _va, retail, after in sc.sites(va, sc.MODE_IR):
            self.assertEqual(len(retail), len(after))
        for mode in (0, sc.MODE_IR):
            page = sc.code_for(va, mode)
            self.assertEqual(len(page), sc.CODE_SIZE)
            self.assertEqual(page[:8], sc.MARKER)
        self.assertEqual(sc.code_for(va, 0)[sc.OFF_IR_PAGE:sc.OFF_IR_PAGE + 64], b"\xcc" * 64)

    def test_the_page_sits_at_its_address_and_every_other_pool_owner_steps_over_it(self):
        for name, requests in (("alone", [space.SPORTSCENTER_NEWS_REQUEST]),
                               ("dormant union", list(space.dormant_union()))):
            with self.subTest(case=name):
                rows = space.plan(requests)["allocations"]
                row = next(r for r in rows if r["owner"] == sc.OWNER)
                self.assertEqual((row["va"], row["size"], row["align"]), (0x1533000, space.PAGE, space.PAGE))
                for other in rows:
                    if other["owner"] != sc.OWNER:
                        self.assertFalse(other["va"] < 0x1534000 and other["va"] + other["size"] > 0x1533000, other)
        # an owner that would cover the page (whether or not the news page is requested) lands after it
        filler = ("aa_synthetic_filler", "code", 0x1533000 - 0x80 - space.POOL_VA - space.PAGE, space.PAGE)
        straddle = ("ab_synthetic_straddle", "code", 0x20000, 16)
        for requests in ([filler, straddle], [filler, straddle, space.SPORTSCENTER_NEWS_REQUEST]):
            with self.subTest(news=space.SPORTSCENTER_NEWS_REQUEST in requests):
                rows = space.plan(requests)["allocations"]
                for other in rows:
                    if other["owner"] != sc.OWNER:
                        self.assertFalse(other["va"] < 0x1534000 and other["va"] + other["size"] > 0x1533000, other)
        with self.assertRaisesRegex(ValueError, "SportsCenter news has one fixed page"):
            space.plan([(sc.OWNER, "code", 0x2000, space.PAGE)])

    def test_retail_reads_retail(self):
        _path, retail = _fixture("NFL2K5_RETAIL_XBE")
        self.assertEqual(sc.status(retail), "retail")
        self.assertEqual(rb.status(retail), "retail")

    def test_candidate_install_both_modes_idempotence_and_removal(self):
        _path, xbe = _fixture("NFL2K5_B81_SC_XBE", CANDIDATE_SHA)
        self.assertEqual(sc.status(xbe), "retail")
        self.assertEqual(sc.wanted_mode(xbe), sc.MODE_IR)
        out, receipt = sc.apply(xbe)
        self.assertEqual((sc.status(out), sc.read_settings(out)["mode"]), ("applied", sc.MODE_IR))
        self.assertEqual(receipt["code_va"], hex(space.SPORTSCENTER_NEWS_VA))
        again, receipt = sc.apply(out)
        self.assertEqual((again, receipt["already_applied"]), (out, True))
        # an install of the other mode (as if modern injured reserve came or went) is switched in place
        from unittest import mock
        with mock.patch.object(sc, "modern_injured_reserve", return_value=False):
            retail_mode, receipt = sc.apply(xbe)
            self.assertEqual((sc.status(retail_mode), sc.read_settings(retail_mode)["mode"]), ("applied", 0))
            self.assertEqual(XbeImage(retail_mode).read(sc.IR_PAGE_VA, 5), sc.IR_PAGE_RETAIL)
            self.assertEqual(sc.apply(retail_mode)[1]["already_applied"], True)
        switched, receipt = sc.apply(retail_mode)
        self.assertEqual(switched, out)
        self.assertEqual(receipt["switched_from_mode"], 0)
        with mock.patch.object(sc, "modern_injured_reserve", return_value=False):
            self.assertEqual(sc.apply(out)[0], retail_mode)             # and back
        back, _ = sc.remove(out)
        self.assertEqual(sc.status(back), "retail")

    def test_foreign_code_around_a_site_or_a_mixed_install_is_refused(self):
        _path, xbe = _fixture("NFL2K5_B81_SC_XBE", CANDIDATE_SHA)
        out, _ = sc.apply(xbe)
        image = XbeImage(out)
        for va in (0x21E2E8, sc.CLUB_VA):                           # inside the segment guard; a site of ours
            broken = bytearray(out)
            broken[image.offset(va, 1)] ^= 0xFF
            self.assertEqual(sc.status(bytes(broken)), "foreign")
            with self.assertRaises(sc.SportsCenterNewsError):
                sc.apply(bytes(broken))

    def test_rb_previous_revisions_upgrade_in_place(self):
        for name, revision in (("NFL2K5_V08_XBE", "b779"), ("NFL2K5_V09_RELEASED_XBE", "b780"),
                               ("NFL2K5_B81_SC_XBE", "b780")):
            with self.subTest(name):
                _path, xbe = _fixture(name)
                self.assertEqual((rb.status(xbe), rb.previous_revision(xbe)), ("previous", revision))
                out, receipt = rb.apply(xbe)
                self.assertEqual((rb.status(out), receipt["previous_revision"]), ("applied", revision))
                cave = rb.allocation(out)["va"]
                self.assertEqual(XbeImage(out).read(cave, rb.CODE_SIZE), rb.code_for(cave))
                self.assertEqual(rb.apply(out)[1]["status"], "already_applied")

    def test_the_build_step_needs_the_2026_season_or_modern_injured_reserve(self):
        """Round 2 S5: a 128 MB Custom plan with modern injured reserve and no 2026 season still gets SportsCenter news
        (mode 1, R2 + R3); a plan with neither is left alone (the six minimal-build tests); 64 MB never. The memory
        model counts the page under the same condition."""
        import tempfile
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_memory_budget as budget
        _path, xbe = _fixture("NFL2K5_B81_SC_XBE", CANDIDATE_SHA)
        # every plan here has a scale-out option (modern IR or the halfback roll), as a real 128 MB build reaching this
        # step does; the target is an already scale-out executable
        cases = ((dict(console_memory=128, modern_injured_reserve=True, season_2026=False), "applied"),
                 (dict(console_memory=128, modern_injured_reserve=False, season_2026=True, sim_rb_injuries=True),
                  "applied"),
                 (dict(console_memory=128, modern_injured_reserve=False, season_2026=False, sim_rb_injuries=True),
                  "retail"),
                 (dict(console_memory=64, modern_injured_reserve=True, season_2026=True), "retail"))
        for options, expected in cases:
            with self.subTest(**options), tempfile.TemporaryDirectory() as temp:
                source, target = Path(temp) / "source.xbe", Path(temp) / "target.xbe"
                source.write_bytes(xbe)
                target.write_bytes(xbe)
                plan = mod_build.BuildPlan(str(source), str(target), **options)
                receipt = {"steps": [], "result": {}}
                mod_build._apply_sportscenter_news(plan, target, receipt, lambda *_: None)
                built = target.read_bytes()
                self.assertEqual(sc.status(built), expected)
                if expected == "applied":
                    self.assertEqual(sc._state(built)[1], sc.MODE_IR)
                    self.assertEqual(receipt["result"]["sportscenter_news"], "applied")
                else:
                    self.assertEqual(built, xbe)
                found = budget.owners(budget.options(plan), options["console_memory"])
                self.assertEqual("sportscenter_news" in found, expected == "applied")

    def test_the_calendar_owner_s_injury_boundary_repair(self):
        """Review N3: nfl2k5_season_length.repair_injury_season_end, the calendar owner's in-place upgrade (like its
        repair_awards_timing): 17 weeks keep 22, 18 weeks get 23 (one byte and the section digest), idempotent,
        refused on foreign bytes; the season groups still validate and SportsCenter news accepts either value."""
        from mod_editor.core import nfl2k5_season_length as season
        _path, retail = _fixture("NFL2K5_RETAIL_XBE")
        self.assertEqual(season.repair_injury_season_end(retail), (retail, season.repair_injury_season_end(retail)[1]))
        self.assertTrue(season.repair_injury_season_end(retail)[1]["already_applied"])
        for name in ("NFL2K5_V09_RELEASED_XBE", "NFL2K5_B81_SC_XBE"):
            with self.subTest(name):
                _path, xbe = _fixture(name)
                out, receipt = season.repair_injury_season_end(xbe)
                self.assertEqual((receipt["before"], receipt["return_week"]), (22, 23))
                self.assertEqual((receipt["preseason_before"], receipt["preseason_weeks"]), (-5, 4))   # review N8
                image = XbeImage(out)
                self.assertEqual(image.read(0x21DA97, 5), bytes.fromhex("83ff177d32"))
                self.assertEqual(image.read(0x21DA72, 6), bytes.fromhex("8d7c30fceb09"))
                changed = [i for i, (a, b) in enumerate(zip(xbe, out)) if a != b]
                boundary = XbeImage(xbe).offset(season.INJURY_SEASON_END_VA)
                preseason = XbeImage(xbe).offset(season.INJURY_PRESEASON_OFFSET_VA)
                self.assertIn(boundary, changed)
                self.assertIn(preseason, changed)
                # besides the two bytes, only the section's 20-byte digest in the headers
                others = [i for i in changed if i not in (boundary, preseason)]
                self.assertLessEqual(len(others), 20)
                self.assertTrue(all(i < XbeImage(xbe).headers_size for i in others))
                self.assertEqual(season.repair_injury_season_end(out), (out, season.repair_injury_season_end(out)[1]))
                self.assertEqual(season.group_status(out, "season_length"), "applied")
                self.assertEqual(sc.status(out), sc.status(xbe))
                bad = bytearray(out)
                bad[XbeImage(out).offset(0x21DA9A)] = 0x7C                 # jl instead of jge: no comparison of ours
                with self.assertRaises(ValueError):
                    season.repair_injury_season_end(bytes(bad))
                bad = bytearray(out)
                bad[XbeImage(out).offset(0x21DA75)] = 0xFA                 # -6: no preseason offset of ours
                with self.assertRaises(ValueError):
                    season.repair_injury_season_end(bytes(bad))

    def test_rb_upgrade_keeps_the_weekly_jump_parked_by_simulated_qb_injuries(self):
        """The v0.9 update's order: Simulated QB injuries (current revision) park the weekly jump at 0x133CC9 first,
        then the SportsCenter chain upgrades the halfback roll. Fails before: "RB injury site 0x133cc9 is not the
        b780 hook" (the upgrade judged the raw bytes, the state the physical view)."""
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        _path, xbe = _fixture("NFL2K5_B81_SC_XBE", CANDIDATE_SHA)
        parked, _ = qb.apply(xbe, "realistic")
        self.assertEqual(XbeImage(parked).read(rb.WEEKLY_SITE, 5), rb.WEEKLY_BEFORE)      # the game's own tail
        self.assertEqual((rb.status(parked), rb.previous_revision(parked)), ("previous", "b780"))
        out, receipt = rb.apply(parked)
        self.assertEqual(rb.status(out), "applied")
        self.assertEqual(XbeImage(out).read(rb.WEEKLY_SITE, 5), rb.WEEKLY_BEFORE)         # still parked
        self.assertEqual([e.get("parked_by") for e in receipt["edits"]], ["nfl2k5_sim_qb_injuries"])
        cave = rb.allocation(out)["va"]
        self.assertEqual(XbeImage(out).read(cave, rb.CODE_SIZE), rb.code_for(cave))
        self.assertEqual(qb.read_settings(out)["status"], "applied")
        self.assertEqual(qb.read_settings(out)["mode"], "realistic")
        chained, upgrade = mod_build._sportscenter_news_upgrade(parked)
        self.assertEqual(sorted(upgrade), ["injury_season_end", "sim_rb_injuries", "sportscenter_news"])
        self.assertEqual(XbeImage(chained).read(0x21DA99, 1), b"\x17")
        self.assertEqual(XbeImage(chained).read(0x21DA75, 1), b"\xfc")
        self.assertEqual((rb.status(chained), sc.status(chained), qb.read_settings(chained)["status"]),
                         ("applied", "applied", "applied"))


if __name__ == "__main__":
    unittest.main()
