"""b81 modern jersey numbers (owner nfl2k5_modern_numbers; modern-numbers/DESIGN.txt 5.1, T1-T10).

Owner's words: "i notice rookie rbs and wrs use old numbers... make sure new additions can use modern position numbers...
a top rookie wr prob wants single digit with exceptions, rbs too, edge, db, etc". Coordinator: a joiner never takes a
number a club-mate wears (active list, practice squad or injured reserve) while another is free.

Every native test runs the game's own jersey routine 0x2BD260 in the harness CPU with the owner's page installed by its
own apply(): on synthetic clubs on the retail executable (Synthetic*), and on a kept 2027 opening image of the standard
build (KeptImage*: real clubs, practice squads and the modern IR store). Each class fails on c4406481b (no owner module);
the later rules' tests name the commit they fail on. There is no mutation class here: the independent review's 12 page
mutants (11 killed; the overflow-row mutant killed once T7 moved to a club without retired numbers) are recorded in
modern-numbers/evidence. The Python rule nfl2k5_modern_numbers.pick is checked against the page.
"""
from __future__ import annotations

import collections
import hashlib
import os
import random
import struct
import unittest
from pathlib import Path
from unittest.mock import patch

from mod_editor.core import nfl2k5_modern_numbers as mn
from mod_editor.core import nfl2k5_modern_numbers_code as mn_code
from mod_editor.core import nfl2k5_xbe_space as space
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

ROOT = Path(__file__).resolve().parents[2]
RETAIL_XBE = os.environ.get("NFL2K5_RETAIL_XBE")
# A kept regular-season opening (2027, stage 8, week 0) of the standard build's ten-season handover panel and the
# executable it ran on (the QB room's 383 candidate, rookie faces applied, modern IR, practice squad).
KEPT_IMAGE = Path(os.environ.get("NFL2K5_B81_NUMBERS_IMAGE", "/media/noah/Storage/2K5-project/qb34-builds/"
                                 "trades-handover-openings/candidate/2501/opening-2027.b81mem.gz"))
KEPT_IMAGE_SHA = "8793067abf927107eb284264b573d8a7a2e67d60d05415774517ee093507a34d"
KEPT_XBE = Path(os.environ.get("NFL2K5_B81_NUMBERS_XBE", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/builds/"
                               "trades-handover/candidate-383/default.xbe"))
KEPT_XBE_SHA = "adb55ab91206367836d277e3829bca417968f7765c58b4c0398e0d0166ff619c"
PAGE = space.MODERN_NUMBERS_VA
POS = {name: k for k, name in enumerate(mn.POSITIONS)}
SIGNING_RET = 0x322DA8                                # the CPU signing's jersey call returns here (a game path)
PAGE_RET = 0x1508000                                  # a return address in an owner's page (MyCareer, modern IR)
RNG_BLOCKS = ((0xE5FCA0, 448), (0xB12680, 448))      # the league and match generators


def _need_retail():
    if not RETAIL_XBE or not Path(RETAIL_XBE).is_file():
        raise unittest.SkipTest("set NFL2K5_RETAIL_XBE to the retail default.xbe")
    if not HAVE_UC:
        raise unittest.SkipTest("unicorn is not installed")


def _need(path, digest):
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise unittest.SkipTest(f"{path.name} is absent or differs (set the NFL2K5_B81_NUMBERS_* fixtures)")


_CACHE = {}


def retail_with_owner():
    if "retail+mn" not in _CACHE:
        _CACHE["retail+mn"] = mn.apply(Path(RETAIL_XBE).read_bytes())[0]
    return _CACHE["retail+mn"]


class League:
    """A synthetic league on the executable: root object, player table, 32 clubs (the reads the page and 0xC4CA0 make)."""

    def __init__(self, payload):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        self.m = m = Machine(payload, trace_writes=False)
        a = m.ARENA
        self.root, self.table, self.teams = a + 0x100, a + 0x10000, a + 0x100000
        self.block = a + 0x1F0000                          # the arena tail (the practice squad's overflow rows)
        m.put(0xB72918, self.root)
        m.put(self.root, 4000)
        m.put(self.root + 4, self.table)
        m.put(self.root + 0x18, 32)
        m.put(self.root + 0x1C, self.teams)
        m.put(0xB72808, self.block + 0x400 - self.root)
        m.put(0xE576AC, 32)                                # in a league (modes 1-3) 0xC4BE0 / 0xC4C50 read these
        for c in range(32):
            m.put(0xE5786C + 4 * c, self.teams + 500 * c)
        self.mode(0)
        self.when(stage=8, season=1)

    def mode(self, value):
        self.m.put(0xE576A0, value)

    def when(self, *, stage, season=1):
        self.m.put(0xE576A4, stage)
        self.m.put(0xE576B8, season)

    def player(self, index, position, number, *, years=5, cue=0):
        p = self.table + 0x54 * index
        self.m.uc.mem_write(p, bytes(0x54))
        self.m.put(p + 0x20, number << 3)
        self.m.uc.mem_write(p + 4, struct.pack("<H", cue))
        self.m.uc.mem_write(p + 0x25, bytes((years,)))
        self.m.uc.mem_write(p + 0x35, bytes((position,)))
        return p

    def club(self, c, active=(), practice=(), overflow=()):
        t = self.teams + 500 * c
        self.m.uc.mem_write(t, bytes(500))
        slots = list(active) + list(practice)
        for k, p in enumerate(slots[:65]):
            self.m.put(t + 4 * k, p)
        self.m.uc.mem_write(t + 0x11C, bytes((len(active),)))
        if practice or overflow:
            self.m.uc.mem_write(t + 0x19B, b"\x01")
            self.m.uc.mem_write(t + 0x1F2, bytes((len(practice) + len(overflow),)))
            self.m.uc.mem_write(t + 0x1F3, b"\xa5")
        if overflow:
            self.m.uc.mem_write(self.block, b"2K5RSV2\0")
            for k, p in enumerate(overflow):
                self.m.uc.mem_write(self.block + 32 + 10 * c + 2 * k, struct.pack("<H", (p - self.table) // 0x54))
        return t

    def injured_reserve(self, c, players):
        self.m.uc.mem_write(0xE421E0 + 20 * c, bytes(20))
        for k, p in enumerate(players[:5]):
            self.m.put(0xE421E0 + 20 * c + 4 * k, p)

    def number(self, p):
        return (self.m.get(p + 0x20) >> 3) & 0x7F

    def join(self, p, t, *, keep=1, frame=None):
        """Call 0x2BD260 (ECX = player, EDX = club, keep) with the caller's frame: [return, keep, ...] (default: the CPU
        signing's return address; the run stops there)."""
        m = self.m
        words = list(frame) if frame else [SIGNING_RET, keep]
        m.uc.mem_write(m.STACK, struct.pack("<%dI" % len(words), *words))
        for name, value in dict(ECX=p, EDX=t, ESP=m.STACK, EBX=0x11111111, ESI=0x22222222, EDI=0x33333333,
                                EBP=0x44444444, EFLAGS=0x202).items():
            m.reg(name, value)
        m.uc.emu_start(0x2BD260, words[0], count=5_000_000)
        if m.reg("EIP") != words[0]:
            raise AssertionError(f"the jersey routine did not return ({m.reg('EIP'):#x})")
        if m.reg("ESP") != m.STACK + 8:
            raise AssertionError("the jersey routine did not pop its one argument")
        saved = {name: m.reg(name) for name in ("EBX", "ESI", "EDI", "EBP")}   # review N2: callee-saved registers
        if saved != dict(EBX=0x11111111, ESI=0x22222222, EDI=0x33333333, EBP=0x44444444):
            raise AssertionError(f"the jersey routine did not preserve the callee-saved registers: {saved}")
        return self.number(p)


def draft_frame(round_, slot=3, caller=mn.DRAFT_CALLERS[0]):
    """The stack FUN_00325B50 leaves at its jersey call: return 0x325B6C, keep 0, its saved EDI and ESI, its own return
    (into one of the three draft paths) and its pick word (round << 5 | slot)."""
    return [mn.DRAFT_JOIN_RET, 0, 0x33333333, 0x22222222, caller, round_ << 5 | slot]


def run_to(m, start, stop):
    m.uc.emu_start(start, stop, count=5_000_000)
    if m.reg("EIP") != stop:
        raise AssertionError(f"stopped at {m.reg('EIP'):#x}")


# ------------------------------------------------------------------------------------------------ the rule's data
class RuleTables(unittest.TestCase):
    def test_legal_numbers_follow_todays_rule(self):
        """DESIGN 3.1 (DE: the edge-as-LB and the DL rule together, so every 2004-range number stays legal)."""
        legal = lambda name: [n for n in range(100) if mn.legal(POS[name], n)]  # noqa: E731
        self.assertEqual(legal("QB"), list(range(20)))
        for name in ("K", "P"):
            self.assertEqual(legal(name), list(range(50)) + list(range(90, 100)))
        for name in ("WR", "TE", "HB", "FB"):
            self.assertEqual(legal(name), list(range(50)) + list(range(80, 90)))
        for name in ("CB", "FS", "SS"):
            self.assertEqual(legal(name), list(range(50)))
        for name in ("OLB", "ILB"):
            self.assertEqual(legal(name), list(range(60)) + list(range(90, 100)))
        for name in ("C", "G", "T"):
            self.assertEqual(legal(name), list(range(50, 80)))
        self.assertEqual(legal("DT"), list(range(50, 80)) + list(range(90, 100)))
        self.assertEqual(legal("DE"), list(range(80)) + list(range(90, 100)))
        # every number of the 2004 range table (0x521B90 / 0x521BD8) is legal
        retail = {"QB": (1, 19), "K": (1, 19), "P": (1, 19), "WR": (80, 89), "TE": (80, 89), "CB": (20, 49),
                  "FS": (20, 49), "SS": (20, 49), "HB": (20, 49), "FB": (20, 49), "OLB": (50, 59), "ILB": (50, 59),
                  "C": (50, 59), "G": (60, 79), "T": (60, 79), "DT": (60, 79), "DE": (60, 79)}
        for name, (low, high) in retail.items():
            self.assertTrue(all(mn.legal(POS[name], n) for n in range(low, high + 1)), name)
        # a weight is never given to a decade the position may not wear, nor a single digit to OL and DL
        for pos in range(17):
            g = mn.GROUP_OF[pos]
            for d in range(10):
                if mn.WEIGHTS[g][d] and d:
                    self.assertTrue(mn.LEGAL_DECADES[pos] >> d & 1, (mn.POSITIONS[pos], d))
            if not mn.LEGAL_DECADES[pos] & 1:
                self.assertEqual(set(mn.SINGLE_DIGIT[g]), {0}, mn.POSITIONS[pos])

    def test_the_page_holds_the_rules_tables(self):
        page = mn.code_for(PAGE)
        for label, blob in (("legal", struct.pack("<17H", *mn.LEGAL_DECADES)), ("groups", bytes(mn.GROUP_OF)),
                            ("weights", b"".join(struct.pack("<10H", *row) for row in mn.WEIGHTS)),
                            ("single digits", b"".join(bytes(row) for row in mn.SINGLE_DIGIT)),
                            ("thresholds", b"".join(bytes(row) for row in mn.THRESHOLDS)),
                            *((f"draft caller {va:#x}", struct.pack("<I", va)) for va in mn.DRAFT_CALLERS),
                            ("draft join return", struct.pack("<I", mn.DRAFT_JOIN_RET))):
            self.assertTrue(blob in page, label)          # the callers are compare immediates in the code
        self.assertLessEqual(mn_code.CODE_BYTES, mn_code.CODE_LIMIT)
        self.assertEqual(page[mn_code.CODE_BYTES:mn_code.CODE_LIMIT], b"\xcc" * (mn_code.CODE_LIMIT - mn_code.CODE_BYTES))

    def test_the_generated_module_is_current(self):
        import shutil
        import subprocess
        import sys
        if not all(shutil.which(t) for t in ("gcc", "as", "ld")):
            raise unittest.SkipTest("GNU toolchain absent")
        try:
            import elftools  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pyelftools absent")
        subprocess.run([sys.executable, "-B", str(ROOT / "tools/modern_numbers/build.py"), "--check"], check=True)


# ------------------------------------------------------------------------------------------------ synthetic clubs
class SyntheticDraft(unittest.TestCase):
    """T1: drafted rookies, 2,000 synthetic joins per cell, clubs with free single digits."""

    @classmethod
    def setUpClass(cls):
        _need_retail()
        cls.league = League(retail_with_owner())

    def shares(self, position, round_, joins=2000):
        lg = self.league
        mates = [lg.player(100 + k, POS["QB"], n) for k, n in enumerate((12, 15))]   # two club-mates, 12 and 15
        single = 0
        out = []
        for k in range(joins):
            c = k % 32
            t = lg.club(c, mates)
            p = lg.player(1000 + k, position, 81, years=0)
            n = lg.join(p, t, frame=draft_frame(round_, slot=c))
            self.assertTrue(mn.legal(position, n), (mn.POSITIONS[position], n))
            self.assertNotIn(n, (12, 15))
            out.append(n)
            single += n <= 9
        return single / joins, out

    def test_veteran_quarterbacks_draw_single_digits_like_todays_veterans(self):
        """A veteran QB whose number is taken at his new club takes a single digit about as often as today's veteran
        QBs (46 percent of 54, nflverse 2026 roster): every veteran QB who draws is tier A (50 percent). Before, most were
        tier D by rating (14 percent; the ten-season panel's QB joiners: 19.5 percent single digits against 37
        league-wide). Fails on 532759774."""
        lg = self.league
        mates = [lg.player(100 + k, POS["QB"], n) for k, n in enumerate((12, 15))]
        single = 0
        for k in range(1000):
            c = k % 32
            t = lg.club(c, mates)
            n = lg.join(lg.player(3000 + k, POS["QB"], 12, years=6), t)          # his own 12 is a club-mate's
            self.assertTrue(mn.legal(POS["QB"], n) and n not in (12, 15), n)
            single += n <= 9
        self.assertLess(abs(single / 1000 - 0.50), 0.05, single)

    def test_single_digits_by_round_follow_the_real_draft(self):
        for name, round_, low, high in (("WR", 0, 0.50, 0.80), ("WR", 4, 0.05, 0.20), ("CB", 0, 0.40, 0.70),
                                        ("FS", 1, 0.25, 0.55), ("HB", 0, 0.40, 0.70), ("DE", 0, 0.10, 0.35),
                                        ("ILB", 0, 0.03, 0.20), ("TE", 0, 0.0, 0.12), ("QB", 0, 0.35, 0.65)):
            with self.subTest(position=name, round=round_ + 1):
                share, _ = self.shares(POS[name], round_)
                self.assertGreaterEqual(share, low)
                self.assertLessEqual(share, high)
        for name in ("C", "G", "T", "DT", "FB"):
            with self.subTest(position=name):
                share, numbers = self.shares(POS[name], 0, joins=400)
                self.assertEqual(share, 0)
        _, numbers = self.shares(POS["FB"], 0, joins=400)
        self.assertTrue(all(30 <= n <= 49 for n in numbers))                       # fullbacks take 30s and 40s

    def test_the_rest_follow_the_2026_decades(self):
        """WR rookies outside the single digits: 10s and 80s as the 2026 rosters (118 : 120 : few 20s-40s)."""
        _, numbers = self.shares(POS["WR"], 4)
        bands = collections.Counter(n // 10 for n in numbers if n > 9)
        total = sum(bands.values())
        self.assertAlmostEqual(bands[1] / total, 118 / 250, delta=0.06)
        self.assertAlmostEqual(bands[8] / total, 120 / 250, delta=0.06)

    def test_draft_detection_needs_one_of_the_three_draft_paths(self):
        """A frame that returns to 0x325B6C but whose caller is none of 0x325C40 / 0x3265C2 / 0x322FBE is not a draft:
        a veteran-style join (he keeps his legal free number)."""
        lg = self.league
        t = lg.club(4, [])
        for k in range(12):
            want = mn.pick(POS["WR"], 84, set(), (3000 + k, 4, 1, 8), draft_round=0)
            for caller in mn.DRAFT_CALLERS:
                p = lg.player(3000 + k, POS["WR"], 84, years=5)
                self.assertEqual(lg.join(p, t, frame=draft_frame(0, caller=caller)), want)
            for caller in (0x325C41, 0x12345678):
                p = lg.player(3000 + k, POS["WR"], 84, years=5)
                self.assertEqual(lg.join(p, t, frame=draft_frame(0, caller=caller)), 84)


class SyntheticRule(unittest.TestCase):
    """T3, T4, T5, T6, T7, T8 on synthetic clubs, and the page against the Python rule."""

    @classmethod
    def setUpClass(cls):
        _need_retail()
        cls.league = League(retail_with_owner())
        cls.retail = League(Path(RETAIL_XBE).read_bytes())

    def setUp(self):
        self.league.mode(0)
        self.league.when(stage=8)

    def test_the_page_is_the_python_rule(self):
        lg, rng = self.league, random.Random(81)
        for trial in range(600):
            pos, c, own = rng.randrange(17), rng.randrange(32), rng.randrange(100)
            mates = [lg.player(100 + k, rng.randrange(17), rng.randrange(100)) for k in range(rng.randrange(60))]
            taken = {lg.number(q) for q in mates}
            stage = rng.choice((3, 7, 8, 9))
            lg.when(stage=stage, season=trial % 10)
            t = lg.club(c, mates)
            index = 2000 + trial
            if rng.random() < 0.3:
                round_ = rng.randrange(7)
                p = lg.player(index, pos, own, years=0)
                got = lg.join(p, t, frame=draft_frame(round_, slot=c, caller=rng.choice(mn.DRAFT_CALLERS)))
                want = mn.pick(pos, own, taken, (index, c, trial % 10, stage), draft_round=round_)
            else:
                years = rng.choice((0, 1, 2, 6))
                p = lg.player(index, pos, own, years=years)
                got = lg.join(p, t)
                want = mn.pick(pos, own, taken, (index, c, trial % 10, stage), rookie_preseason=years <= 1 and stage < 8)
            if want >= 0:
                self.assertEqual(got, want, dict(trial=trial, pos=mn.POSITIONS[pos], own=own, stage=stage))

    def test_t3_the_one_free_legal_number(self):
        lg = self.league
        holders = [lg.player(200 + k, POS["CB"], n) for k, n in enumerate(n for n in range(50) if n != 37)]
        t = lg.club(6, holders)
        for years in (6, 1):
            p = lg.player(900, POS["CB"], 24, years=years)
            self.assertEqual(lg.join(p, t), 37)

    def test_t3_none_free_runs_the_retail_routine_with_keep_1(self):
        """Every legal number taken at a club outside the league (slot 40: 0xC4CA0 gives no league index; a league club
        draws from the nearest decade instead, SyntheticClubNumbers): the retail walk with keep = 1, the same as the
        unhooked routine."""
        for lg in (self.league, self.retail):
            holders = [lg.player(300 + k, POS["G"], n) for k, n in enumerate(range(50, 80))]
            lg.club(40, holders)
        for own in (55, 64, 72, 90):
            hooked = self.league.join(self.league.player(901, POS["G"], own), self.league.teams + 500 * 40)
            retail = self.retail.join(self.retail.player(901, POS["G"], own), self.retail.teams + 500 * 40)
            self.assertEqual(hooked, retail, own)
            # the retail random fallback drew from the league generator in both executables alike
            self.assertEqual(bytes(self.league.m.uc.mem_read(0xE5FCA0, 448)), bytes(self.retail.m.uc.mem_read(0xE5FCA0, 448)))

    def test_t4_a_veteran_keeps_his_legal_free_number(self):
        lg = self.league
        t = lg.club(8, [lg.player(400, POS["WR"], 17), lg.player(401, POS["TE"], 87)])
        for own in (84, 11, 0, 3):
            self.assertEqual(lg.join(lg.player(902, POS["WR"], own, years=7), t), own)
        for own in (17, 87):                                             # taken: a fresh draw, never a club-mate's
            for k in range(40):
                n = lg.join(lg.player(903 + k, POS["WR"], own, years=7), t)
                self.assertTrue(mn.legal(POS["WR"], n) and n not in (17, 87), n)
        for own in (55, 72, 95):                                          # illegal for a WR: a fresh draw
            n = lg.join(lg.player(950, POS["WR"], own, years=7), t)
            self.assertTrue(mn.legal(POS["WR"], n) and n not in (17, 87), n)
        # a DE with a 2004 60s number keeps it (every 2004-range number is legal)
        self.assertEqual(lg.join(lg.player(951, POS["DE"], 66, years=7), t), 66)

    def test_t4_rookies_before_the_season_always_draw(self):
        lg = self.league
        t = lg.club(9, [])
        lg.when(stage=5)
        seen = {lg.join(lg.player(1500 + k, POS["WR"], 84, years=1), t) for k in range(60)}
        self.assertGreater(len(seen), 5)
        lg.when(stage=8)                                                  # in season he keeps his own
        self.assertEqual(lg.join(lg.player(1600, POS["WR"], 84, years=1), t), 84)

    def test_t5_nothing_else_changes(self):
        lg = self.league
        mates = [lg.player(500 + k, POS["WR"], n) for k, n in enumerate((10, 11, 80, 81))]
        ps = [lg.player(510, POS["CB"], 21)]
        t = lg.club(10, mates, practice=ps)
        lg.injured_reserve(10, [lg.player(520, POS["HB"], 22)])
        p = lg.player(990, POS["WR"], 10, years=6, cue=9010)
        regions = [(lg.m.ARENA, 0x200000), (0xE421E0, 32 * 20), *RNG_BLOCKS]
        before = [bytes(lg.m.uc.mem_read(a, n)) for a, n in regions]
        record = bytes(lg.m.uc.mem_read(p, 0x54))
        n = lg.join(p, t)
        after = [bytes(lg.m.uc.mem_read(a, n2)) for a, n2 in regions]
        self.assertNotEqual(n, 10)
        changed = [regions[k][0] + i for k in range(len(regions)) for i in range(len(before[k]))
                   if before[k][i] != after[k][i]]
        self.assertTrue(changed)
        self.assertTrue(all(p + 4 <= a < p + 6 or p + 0x20 <= a < p + 0x22 for a in changed), [hex(a) for a in changed])
        new = bytes(lg.m.uc.mem_read(p, 0x54))
        old_word, new_word = (struct.unpack_from("<I", r, 0x20)[0] for r in (record, new))
        self.assertEqual(old_word & ~0x3F8, new_word & ~0x3F8)            # only bits 3..9 of +0x20

    def test_t6_deterministic_and_no_game_rng(self):
        lg = self.league
        t = lg.club(11, [lg.player(600, POS["CB"], 1)])
        rng_before = [bytes(lg.m.uc.mem_read(a, n)) for a, n in RNG_BLOCKS]
        lg.when(stage=4, season=3)
        a = lg.join(lg.player(991, POS["CB"], 1, years=0), t, frame=draft_frame(0, slot=11))
        b = lg.join(lg.player(991, POS["CB"], 1, years=0), t, frame=draft_frame(0, slot=11))
        self.assertEqual(a, b)
        self.assertEqual([bytes(lg.m.uc.mem_read(x, n)) for x, n in RNG_BLOCKS], rng_before)
        lg.when(stage=4, season=4)                                        # another season, another draw stream
        others = {lg.join(lg.player(991 + k, POS["CB"], 1, years=0), t, frame=draft_frame(0, slot=11))
                  for k in range(30)}
        self.assertGreater(len(others), 3)

    def test_t7_practice_squad_and_injured_reserve_count_as_taken(self):
        """Every legal number but one is held by the club's practice squad (incl. an overflow row) or IR: the joiner
        gets the one; the retail routine (active list only) would have taken a held one."""
        lg = self.league
        lg.mode(2)                                                        # franchise: the IR table is read
        try:
            free = 33
            # The overflow men wear 20 and 21: outside 0-19, which the quarterback reserve closes for a corner here,
            # and not retired at Atlanta. So only the overflow rows hold them (review S1, rounds 1 and 2: at Miami the
            # retired 12/13, then the 0-19 reserve, hid the check).
            held_overflow = [20, 21]
            numbers = [n for n in range(50) if n != free and n not in held_overflow]
            ps = [lg.player(700 + k, POS["CB"], n) for k, n in enumerate(numbers[:12])]
            overflow = [lg.player(730 + k, POS["CB"], n) for k, n in enumerate(held_overflow)]
            ir = [lg.player(740 + k, POS["CB"], n) for k, n in enumerate(numbers[12:17])]
            active = [lg.player(760 + k, POS["CB"], n) for k, n in enumerate(numbers[17:])]
            active += [lg.player(800 + k, POS["G"], 50 + k) for k in range(53 - len(active))]   # 53 + 12 fill the 65 slots
            t = lg.club(14, active, practice=ps, overflow=overflow)     # Atlanta: no retired numbers
            lg.injured_reserve(14, ir)
            for years in (7, 0):
                self.assertEqual(lg.join(lg.player(992, POS["CB"], numbers[0], years=years), t), free)
            for k, own in enumerate(held_overflow):                     # an overflow man's
                self.assertEqual(lg.join(lg.player(993 + k, POS["CB"], own, years=7), t), free)
            self.assertEqual(lg.join(lg.player(995, POS["CB"], numbers[13], years=7), t), free)   # an IR man's
        finally:
            lg.mode(0)
            lg.injured_reserve(14, [])

    def test_t8_the_cue_follows_the_number(self):
        lg = self.league
        t = lg.club(13, [lg.player(850, POS["HB"], 26)])
        p = lg.player(995, POS["HB"], 26, years=6, cue=9026)
        n = lg.join(p, t)
        self.assertEqual(struct.unpack("<H", bytes(lg.m.uc.mem_read(p + 4, 2)))[0], 9000 + n)
        p = lg.player(996, POS["HB"], 26, years=6, cue=4321)
        lg.join(p, t)
        self.assertEqual(struct.unpack("<H", bytes(lg.m.uc.mem_read(p + 4, 2)))[0], 4321)


class SyntheticClubNumbers(unittest.TestCase):
    """Retired and legacy numbers (data/nfl2k5_modern_numbers/numbers.json): never handed out automatically, the
    first-round skill exceptions (NYG 1, TEN 1), DAL 88 for a wide receiver. Synthetic clubs on retail + the owner; the
    club is its league slot. Fail on 866fe3a8d (no retired or legacy numbers)."""

    @classmethod
    def setUpClass(cls):
        _need_retail()
        cls.league = League(retail_with_owner())
        cls.idx = mn.DATA["club_index"]

    def joins(self, club, position, frames, *, own=50, years=6, mates=(), start=6000):
        lg = self.league
        t = lg.club(club, [lg.player(5000 + k, POS["QB"], n) for k, n in enumerate(mates)])
        out = []
        for k, frame in enumerate(frames):
            p = lg.player(start + k, position, own, years=years)
            out.append(lg.join(p, t, frame=frame))
        return out

    def test_the_data_and_its_sources(self):
        d = mn.DATA
        self.assertEqual(sorted(d["club_index"].values()), list(range(32)))
        self.assertTrue(d["retired"]["source"]["url"].startswith("https://en.wikipedia.org/"))
        self.assertEqual(len(d["retired"]["source"]["wikitext_sha256"]), 64)
        chi = [r["number"] for r in d["retired"]["clubs"]["CHI"]]
        self.assertEqual(chi, [3, 5, 7, 28, 34, 40, 41, 42, 51, 56, 61, 66, 77, 89])
        for e in d["retired_exceptions"]:
            self.assertTrue(mn.retired(self.idx[e["club"]], e["number"]), e)
            self.assertTrue(e["source"] and e["precedent"])
        self.assertEqual([(e["club"], e["number"], e["position"]) for e in d["legacy"]], [("DAL", 88, "WR")])
        self.assertFalse(any(mn.retired(c, n) for c, n, _ in mn.LEGACY))

    def test_retired_numbers_are_never_handed_out(self):
        rng = random.Random(5)
        for club in ("CHI", "NYG", "SF", "KC"):
            c = self.idx[club]
            for position in ("QB", "HB", "WR", "CB", "ILB", "DE", "DT", "G", "TE", "K"):
                frames = [draft_frame(rng.randrange(7), slot=c) for _ in range(30)] + [None] * 30
                got = self.joins(c, POS[position], frames, own=rng.randrange(100), years=0)
                bad = [n for n in got if mn.retired(c, n)
                       and not (club == "NYG" and n == 1)]                 # the exception: checked below
                self.assertFalse(bad, (club, position))
        chi = self.idx["CHI"]
        self.assertNotEqual(self.joins(chi, POS["HB"], [None], own=34)[0], 34)   # not even as a veteran's own number
        self.assertEqual(self.joins(self.idx["ATL"], POS["HB"], [None], own=34)[0], 34)

    def test_the_first_round_skill_exception(self):
        singles = list(range(2, 10)) + [0]                                  # every other single digit taken
        for club, position in (("NYG", "WR"), ("TEN", "QB")):
            c = self.idx[club]
            r1 = self.joins(c, POS[position], [draft_frame(0, slot=c) for _ in range(80)], mates=singles)
            r2 = self.joins(c, POS[position], [draft_frame(1, slot=c) for _ in range(80)], mates=singles)
            vet = self.joins(c, POS[position], [None] * 40, own=1)
            self.assertIn(1, r1, club)                                     # a first-round skill rookie may get it
            self.assertNotIn(1, r2, club)
            self.assertNotIn(1, vet, club)
        nyg = self.idx["NYG"]
        cb = self.joins(nyg, POS["CB"], [draft_frame(0, slot=nyg) for _ in range(80)], mates=singles)
        self.assertNotIn(1, cb)                                            # a corner is not a skill position

    def test_a_page_call_keeps_the_users_own_number(self):
        """MyCareer signs the user's own created player through the jersey routine from its page: he keeps the number he
        chose while no club-mate wears it (rookie before the season, a retired or legacy number included); taken, a draw
        that follows every rule."""
        lg = self.league
        chi, dal = self.idx["CHI"], self.idx["DAL"]
        lg.when(stage=5)
        try:
            self.assertEqual(self.joins(chi, POS["HB"], [[PAGE_RET, 1]], own=34, years=1)[0], 34)
            self.assertEqual(self.joins(dal, POS["TE"], [[PAGE_RET, 1]], own=88, years=1)[0], 88)
            self.assertEqual(self.joins(chi, POS["WR"], [[PAGE_RET, 1]], own=17, years=1)[0], 17)
            got = self.joins(chi, POS["HB"], [[PAGE_RET, 1]] * 40, own=12, years=1, mates=(12,))
            self.assertFalse([n for n in got if n == 12 or mn.retired(chi, n)])
            self.assertNotEqual(self.joins(chi, POS["HB"], [None], own=34, years=6)[0], 34)   # a game path never
        finally:
            lg.when(stage=8)

    def test_nothing_legal_free_never_hands_out_rights_or_retired_numbers(self):
        """The panel's case (ten3, root 72003, 2026: Miami, the Jets and Washington signing quarterbacks): every legal
        number is worn by a club-mate, held by an IR or practice-squad man, or retired. The retail routine (active list
        only) gave an IR man's 11 or a retired 12; the owner's rules allow neither. The joiner gets a number from the
        nearest decade nobody on the club wears, holds or has retired; the Python rule agrees. Fails on d4a055ce3."""
        lg = self.league
        lg.mode(2)                                                        # franchise: the IR table is read
        try:
            for club, position, legal_numbers, ir_numbers, ps_numbers, near in (
                    ("MIA", "QB", range(0, 20), (11,), (10,), range(20, 30)),
                    ("NYJ", "QB", range(0, 20), (4, 11), (15,), range(20, 30)),
                    ("WAS", "QB", range(0, 20), (5,), (), range(20, 30)),
                    ("ARI", "G", range(50, 80), (66,), (71,), list(range(40, 50)) + list(range(80, 90)))):
                c = self.idx[club]
                open_ = [n for n in legal_numbers if not mn.retired(c, n)]
                ir = [lg.player(7100 + k, POS[position], n) for k, n in enumerate(ir_numbers)]
                ps = [lg.player(7120 + k, POS[position], n) for k, n in enumerate(ps_numbers)]
                worn = [n for n in open_ if n not in ir_numbers and n not in ps_numbers]
                active = [lg.player(7140 + k, POS[position], n) for k, n in enumerate(worn)]
                t = lg.club(c, active, practice=ps)
                lg.injured_reserve(c, ir)
                claimed = set(open_)
                for k, frame in enumerate([None] * 12 + [draft_frame(r, slot=c) for r in range(7)]):
                    index = 7200 + k
                    own = open_[k % len(open_)]
                    got = lg.join(lg.player(index, POS[position], own, years=0 if frame else 6), t, frame=frame)
                    where = dict(club=club, own=own, got=got, frame=frame)
                    self.assertNotIn(got, claimed, where)                  # no club-mate's, no IR or squad man's
                    self.assertFalse(mn.retired(c, got), where)            # no retired number
                    self.assertIn(got, near, where)                        # the nearest decade(s) with a free number
                    want = mn.pick(POS[position], own, claimed, (index, c, 1, 8),
                                   draft_round=frame[5] >> 5 if frame else None)
                    self.assertEqual(got, want, where)
                lg.injured_reserve(c, [])
        finally:
            lg.mode(0)

    def test_0_19_kept_for_quarterbacks_when_short(self):
        """Review S4 (coordinator 11/25): at a league club with fewer than 3 numbers free in 0-19, a joiner who is not a
        QB, K or P takes none of them, his own number included; a quarterback (or kicker) still may. With 3 free, the
        draw is as before. Fails on c02a1b9ae (a first-round WR took 5 or 11)."""
        atl = self.idx["ATL"]
        two = [n for n in range(20) if n not in (5, 11)]
        r1 = self.joins(atl, POS["WR"], [draft_frame(0, slot=atl) for _ in range(60)], mates=two)
        self.assertFalse([n for n in r1 if n < 20], r1)
        for position in ("CB", "HB", "TE", "OLB", "DE"):
            got = self.joins(atl, POS[position], [draft_frame(r % 7, slot=atl) for r in range(40)] + [None] * 10,
                             own=11, mates=two)
            self.assertFalse([n for n in got if n < 20], position)        # a veteran's own free 11 included
        self.assertIn(self.joins(atl, POS["QB"], [None], own=12, mates=two)[0], (5, 11))
        self.assertIn(self.joins(atl, POS["K"], [None], own=12, mates=two)[0], (5, 11))
        self.assertEqual(self.joins(atl, POS["QB"], [None], own=11, mates=two)[0], 11)   # a QB keeps his free own
        three = [n for n in range(20) if n not in (5, 11, 17)]
        r1 = self.joins(atl, POS["WR"], [draft_frame(0, slot=atl) for _ in range(60)], mates=three)
        self.assertTrue([n for n in r1 if n < 20], r1)                     # 3 free: single digits as before
        self.assertEqual(self.joins(atl, POS["WR"], [None], own=11, mates=three)[0], 11)

    def test_dallas_88(self):
        dal = self.idx["DAL"]
        self.assertEqual(self.joins(dal, POS["WR"], [draft_frame(0, slot=dal)])[0], 88)   # a first-round WR
        self.assertEqual(self.joins(dal, POS["WR"], [draft_frame(1, slot=dal)])[0], 88)
        later = self.joins(dal, POS["WR"], [draft_frame(4, slot=dal) for _ in range(150)])
        self.assertNotIn(88, later)                                        # left for a better newcomer
        for position in ("TE", "HB", "QB", "CB"):
            got = self.joins(dal, POS[position], [draft_frame(r % 7, slot=dal) for r in range(150)] + [None] * 30,
                             own=88)
            self.assertNotIn(88, got, position)                            # another position never gets it
        self.assertEqual(self.joins(dal, POS["WR"], [None], own=88)[0], 88)  # a veteran WR keeps his own 88
        self.assertEqual(self.joins(dal, POS["WR"], [draft_frame(0, slot=dal)], mates=(88,))[0] != 88, True)
        other = self.idx["NYJ"]
        self.assertEqual(self.joins(other, POS["TE"], [None], own=88)[0], 88)   # elsewhere 88 is any WR or TE's


class SyntheticRookieFaces(unittest.TestCase):
    """T9: with Rookie faces' two jersey edits (the draft's push 1 at 0x325B61, the DT/DE walk at 0x2BD2F7) the modern
    path gives the same numbers; the two owners install in either order and either one's Retail leaves the other."""

    @classmethod
    def setUpClass(cls):
        _need_retail()
        from mod_editor.core import nfl2k5_rookie_faces as rf
        cls.rf = rf
        from tests.mod_editor.test_b778_rh1_rookie_faces import shipped_pool, toy_bank
        retail = Path(RETAIL_XBE).read_bytes()
        firsts, lasts = shipped_pool()
        cls.faces = rf.xbe_apply(retail, rf.tables(firsts, lasts, toy_bank()))[0]
        cls.both = mn.apply(cls.faces)[0]

    def test_same_numbers_with_and_without_rookie_faces(self):
        a, b = League(retail_with_owner()), League(self.both)
        rng = random.Random(9)
        for trial in range(300):
            pos, own = rng.randrange(17), rng.randrange(100)
            for lg in (a, b):
                mates = [lg.player(100 + k, (k * 7) % 17, (k * 13 + trial) % 100) for k in range(30)]
                lg.club(trial % 32, mates)
            frame = draft_frame(rng.randrange(7)) if trial % 3 == 0 else None
            na = a.join(a.player(4000, pos, own, years=0), a.teams + 500 * (trial % 32), frame=frame)
            nb = b.join(b.player(4000, pos, own, years=0), b.teams + 500 * (trial % 32), frame=frame)
            self.assertEqual(na, nb, trial)

    def test_install_order_and_retail(self):
        rf = self.rf
        other_order = self.rf.xbe_apply(retail_with_owner(), self.rf.xbe_tables(self.faces))[0]
        self.assertEqual(other_order, self.both)
        self.assertEqual((mn.status(self.both), rf.xbe_status(self.both)), ("applied", "applied"))
        ours_off = mn.remove(self.both)[0]
        self.assertEqual((mn.status(ours_off), rf.xbe_status(ours_off)), ("retail", "applied"))
        self.assertEqual(rf.xbe_tables(ours_off), rf.xbe_tables(self.both))
        # Rookie faces' two jersey edits back to their retail bytes (sealed): ours still reads applied
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        theirs_off = rdata.apply(self.both, [("rf", va, patched, retail) for va, retail, patched in mn.ROOKIE_FACES_SPANS],
                                 "test")[0]
        self.assertEqual(mn.status(theirs_off), "applied")


# ------------------------------------------------------------------------------------------------ a kept image
class KeptImage(unittest.TestCase):
    """T2 and T7 on real clubs: the 2027 opening of the standard build's handover panel (practice squads, the modern
    IR store), the owner's page and site written into its memory exactly as apply() writes them into the executable."""

    @classmethod
    def setUpClass(cls):
        _need_retail()
        _need(KEPT_IMAGE, KEPT_IMAGE_SHA)
        _need(KEPT_XBE, KEPT_XBE_SHA)
        from tools import franchise_invariants as fi
        from tests.nfl2k5_supersim_draft_fixture import Machine
        cls.fi = fi
        cls.memory = fi.load_memory(KEPT_IMAGE)
        xbe = mn.apply(KEPT_XBE.read_bytes())[0]
        cls.m = m = Machine(xbe, trace_writes=False)
        mapped = [(a, b) for a, b, _ in m.uc.mem_regions()]
        for low, data in cls.memory.regions:
            if low >= 0x3000000:
                continue
            page = low & ~0xFFF
            while page < low + len(data):
                if not any(a <= page <= b for a, b in mapped):
                    m.uc.mem_map(page, 0x1000)
                    mapped.append((page, page + 0xFFF))
                page += 0x1000
            m.uc.mem_write(low, data)
        m.uc.mem_write(PAGE, mn.code_for(PAGE))
        m.uc.mem_write(mn.SITE_VA, mn.site_bytes(PAGE))
        m.uc.ctl_flush_tb()
        cls.root = m.get(0xB72918)
        cls.table, cls.teams = m.get(cls.root + 4), m.get(cls.root + 0x1C)

    def setUp(self):
        self.reset()
        self.view = self.fi.view_from_memory(lambda a, n: bytes(self.m.uc.mem_read(a, n)), search=self.memory.find)

    @classmethod
    def reset(cls):
        """The whole kept image again, with the owner's page and site."""
        for low, data in cls.memory.regions:
            if low < 0x3000000:
                cls.m.uc.mem_write(low, data)
        cls.m.uc.mem_write(PAGE, mn.code_for(PAGE))
        cls.m.uc.mem_write(mn.SITE_VA, mn.site_bytes(PAGE))
        cls.m.uc.ctl_flush_tb()

    def number(self, i):
        return (self.m.get(self.table + 0x54 * i + 0x20) >> 3) & 0x7F

    def held(self, c, minus=None):
        club = self.view.clubs[c]
        ir = [i for i, _ in self.view.ir.clubs[c] if i >= 0]
        return {self.number(i) for i in club.active + club.practice + ir if i != minus}

    def call(self, p, t, words):
        m = self.m
        m.uc.mem_write(m.STACK, struct.pack("<%dI" % len(words), *words))
        for name, value in dict(ECX=p, EDX=t, ESP=m.STACK, EFLAGS=0x202).items():
            m.reg(name, value)
        run_to(m, mn.SITE_VA, words[0])

    def test_t2_every_caller_gives_a_legal_free_number(self):
        """The hook sees the caller only through its return address: the draft (three paths), the CPU signing, both
        trade sides, offseason free agency, the user signing paths; MyCareer's call returns into its own page."""
        self.assertEqual(self.view.ir.kind, "store")
        returns = {"cpu signing 0x322DA3": 0x322DA8, "trade side A 0x2BC740": 0x2BC745, "trade side B 0x2BC790": 0x2BC795,
                   "offseason FA 0x323BFB": 0x323C00, "offers 0x32401E": 0x324023, "signing 0x2B83AE": 0x2B83B3,
                   "UI 0x319BF6": 0x319BFB, "user FA 0x36F881": 0x36F886, "user FA 0x36FA9F": 0x36FAA4,
                   "MyCareer (its page)": PAGE_RET}
        stop = self.m.STOP
        fas = self.view.free_agents
        rng = random.Random(2)
        for label, ret in returns.items():
            for k in range(24):
                c = rng.randrange(32)
                i = fas[rng.randrange(len(fas))]
                record = bytes(self.m.uc.mem_read(self.table + 0x54 * i, 0x54))
                held = self.held(c)
                self.call(self.table + 0x54 * i, self.teams + 500 * c, [ret, 1])
                n, pos = self.number(i), self.m.uc.mem_read(self.table + 0x54 * i + 0x35, 1)[0]
                self.assertTrue(mn.legal(pos, n), (label, pos, n))
                self.assertNotIn(n, held, label)
                self.m.uc.mem_write(self.table + 0x54 * i, record)
        for caller in mn.DRAFT_CALLERS:                                   # the draft: a fresh draw for each
            for k in range(24):
                c = rng.randrange(32)
                i = fas[rng.randrange(len(fas))]
                record = bytes(self.m.uc.mem_read(self.table + 0x54 * i, 0x54))
                held = self.held(c)
                self.call(self.table + 0x54 * i, self.teams + 500 * c, draft_frame(k % 7, slot=c, caller=caller))
                pos = self.m.uc.mem_read(self.table + 0x54 * i + 0x35, 1)[0]
                self.assertTrue(mn.legal(pos, self.number(i)) and self.number(i) not in held)
                self.m.uc.mem_write(self.table + 0x54 * i, record)

    def test_t2_the_native_draft_join_and_cpu_signing(self):
        """FUN_00325B50 (a drafted player joins: contract, jersey, append, transaction) entered from a draft path's
        frame, and the native CPU signing 0x322BB0(club, position, 0xFFFF, menu 0) after the native release 0x2BD900
        made room: the new player's number is legal and no club-mate wears it."""
        m, stop = self.m, self.m.STOP
        fas = [i for i in self.view.free_agents if m.uc.mem_read(self.table + 0x54 * i + 0x35, 1)[0] == POS["WR"]]
        for c in (0, 9, 21):
            self.reset()
            team = self.teams + 500 * c
            last = m.get(team + 4 * (m.uc.mem_read(team + 0x11C, 1)[0] - 1))
            m.uc.mem_write(m.STACK, struct.pack("<3I", stop, 1, 0))
            for name, value in dict(ECX=team, EDX=last, ESP=m.STACK).items():
                m.reg(name, value)
            run_to(m, 0x2BD900, stop)                                     # release one (room for the join)
            view = self.fi.view_from_memory(lambda a, n: bytes(m.uc.mem_read(a, n)), search=self.memory.find)
            self.view = view
            held = self.held(c)
            i = fas[c]
            p = self.table + 0x54 * i
            m.uc.mem_write(m.STACK, struct.pack("<2I", mn.DRAFT_CALLERS[0], 0 << 5 | c))
            for name, value in dict(ECX=p, EDX=team, ESP=m.STACK).items():
                m.reg(name, value)
            run_to(m, 0x325B50, mn.DRAFT_CALLERS[0])
            self.assertIn(p, [m.get(team + 4 * k) for k in range(m.uc.mem_read(team + 0x11C, 1)[0])])
            self.assertTrue(mn.legal(POS["WR"], self.number(i)) and self.number(i) not in held, self.number(i))
        self.reset()
        team = self.teams
        last = m.get(team + 4 * (m.uc.mem_read(team + 0x11C, 1)[0] - 1))
        m.uc.mem_write(m.STACK, struct.pack("<3I", stop, 1, 0))
        for name, value in dict(ECX=team, EDX=last, ESP=m.STACK).items():
            m.reg(name, value)
        run_to(m, 0x2BD900, stop)
        self.view = self.fi.view_from_memory(lambda a, n: bytes(m.uc.mem_read(a, n)), search=self.memory.find)
        held = self.held(0)
        m.uc.mem_write(m.STACK, struct.pack("<5I", stop, team, POS["WR"], 0xFFFF, 0))
        m.reg("ESP", m.STACK)
        run_to(m, 0x322BB0, stop)
        self.assertEqual(m.reg("EAX"), 1)
        new = m.get(team + 4 * (m.uc.mem_read(team + 0x11C, 1)[0] - 1))
        n = (m.get(new + 0x20) >> 3) & 0x7F
        self.assertTrue(mn.legal(POS["WR"], n) and n not in held, n)

    def test_t7_real_squads_and_ir(self):
        """On every club, a joiner wearing the number of a practice-squad or IR man never keeps it."""
        stop = self.m.STOP
        fas = self.view.free_agents
        checked = 0
        for c in range(32):
            club = self.view.clubs[c]
            hidden = [i for i in club.practice] + [i for i, _ in self.view.ir.clubs[c] if i >= 0]
            for h in hidden[:4]:
                i = fas[(c * 7 + checked) % len(fas)]
                p = self.table + 0x54 * i
                record = bytes(self.m.uc.mem_read(p, 0x54))
                hpos = self.m.uc.mem_read(self.table + 0x54 * h + 0x35, 1)[0]
                word = self.m.get(p + 0x20)
                self.m.put(p + 0x20, (word & ~0x3F8) | self.number(h) << 3)    # he arrives wearing the hidden man's
                self.m.uc.mem_write(p + 0x35, bytes((hpos,)))
                self.m.uc.mem_write(p + 0x25, b"\x06")
                self.call(p, self.teams + 500 * c, [SIGNING_RET, 1])
                self.assertNotIn(self.number(i), self.held(c, minus=i))
                self.m.uc.mem_write(p, record)
                checked += 1
        self.assertGreaterEqual(checked, 90)


# ------------------------------------------------------------------------------------------------ owner states
class OwnerStates(unittest.TestCase):
    """T10: retail / applied / previous / foreign; added in place to a built executable moving nobody; Retail leaves
    the source plus the empty reservation; the allocator places the page at 0x1530000 in every order."""

    @classmethod
    def setUpClass(cls):
        _need_retail()
        cls.retail = Path(RETAIL_XBE).read_bytes()
        cls.applied = retail_with_owner()

    def test_states(self):
        self.assertEqual(mn.status(self.retail), "retail")
        self.assertEqual(mn.status(self.applied), "applied")
        removed = mn.remove(self.applied)[0]
        self.assertEqual(mn.status(removed), "retail")
        self.assertEqual(mn.apply(removed)[0], self.applied)
        self.assertEqual(mn.apply(self.applied)[0], self.applied)        # idempotent
        settings = mn.read_settings(self.applied)
        self.assertEqual((settings["status"], settings["mode"], settings["page_va"]), ("applied", "modern", hex(PAGE)))

    @staticmethod
    def _patched(_self, payload, va, data):
        """``data`` written at ``va`` with the section digest resealed (a foreign edit, not a broken file)."""
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        return rdata.apply(payload, [("test", va, XbeImage(payload).read(va, len(data)), data)], "test")[0]

    def test_foreign(self):
        site_only = self._patched(self, mn.remove(self.applied)[0], mn.SITE_VA, mn.site_bytes(PAGE))
        self.assertEqual(mn.status(site_only), "foreign")                 # site without the page
        page = bytearray(mn.code_for(PAGE))
        page[0x200] ^= 1
        self.assertEqual(mn.status(self._patched(self, self.applied, PAGE, bytes(page))), "foreign")
        self.assertEqual(mn.status(self._patched(self, self.applied, 0x2BD300, b"\x90")), "foreign")   # guarded body
        self.assertEqual(mn.status(self._patched(self, self.applied, 0x325C3B, b"\x90" * 5)), "foreign")  # a draft call
        self.assertEqual(mn.status(self._patched(self, self.retail, mn.SITE_VA, b"\x90" * 6)), "foreign")
        for bad in (self.applied[:-1], b""):
            self.assertEqual(mn.status(bad), "foreign")

    def test_previous_revisions_upgrade_in_place(self):
        """No revision has shipped (PREVIOUS_TEMPLATES is empty); the state machine is proved with a stand-in one."""
        old = bytearray(mn.code_for(PAGE))
        old[mn_code.CODE_BYTES - 1] ^= 0x55
        stand_in = self._patched(self, self.applied, PAGE, bytes(old))
        self.assertEqual(mn.status(stand_in), "foreign")
        with patch.object(mn, "PREVIOUS_TEMPLATES", (bytes(old),)):
            from mod_editor.core import nfl2k5_xbe_space as sp
            sealed = sp.install_code(self.applied, mn.OWNER, bytes(old), previous=mn.code_for(PAGE))[0]
            self.assertEqual(mn.status(sealed), "previous")
            upgraded, receipt = mn.apply(sealed)
            self.assertEqual((mn.status(upgraded), receipt["upgraded_from"]), ("applied", "previous"))
            self.assertEqual(upgraded, self.applied)

    def test_in_place_on_a_built_executable(self):
        _need(KEPT_XBE, KEPT_XBE_SHA)
        built = KEPT_XBE.read_bytes()
        self.assertEqual(mn.status(built), "retail")
        after, receipt = mn.apply(built)
        self.assertEqual(mn.status(after), "applied")
        key = lambda a: (a["owner"], a["kind"], a.get("owner_offset", 0))  # noqa: E731
        old = {key(a): a for a in space.layout(built)["allocations"] if a["owner"] != space.DIRECTORY_OWNER}
        new = {key(a): a for a in space.layout(after)["allocations"]}
        self.assertTrue(all(new[k] == a for k, a in old.items()))
        self.assertEqual(new[(mn.OWNER, "code", 0)]["va"], PAGE)
        back = mn.remove(after)[0]
        self.assertEqual(mn.status(back), "retail")
        # Realistic then Retail = the source plus the empty reservation (same reservation, page 0xCC, site retail)
        self.assertEqual(len(back), len(after))
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual(XbeImage(back).read(PAGE, mn.CODE_SIZE), b"\xcc" * mn.CODE_SIZE)
        self.assertEqual(XbeImage(back).read(mn.SITE_VA, 6), mn.SITE_RETAIL)
        text = XbeImage(built).sections[0]
        self.assertEqual(XbeImage(back).read(text.start, text.raw_size), XbeImage(built).read(text.start, text.raw_size))

    def test_the_page_is_fixed_in_every_order(self):
        union = list(space.dormant_union())
        request = space.MODERN_NUMBERS_REQUEST
        for label, requests in (("alone", [request]), ("first", [request] + union), ("last", union + [request])):
            with self.subTest(label):
                rows = space.plan(requests)["allocations"]
                ours = [r for r in rows if r["owner"] == mn.OWNER]
                self.assertEqual([(r["va"], r["size"]) for r in ours], [(PAGE, 0x1000)])
                for r in rows:
                    if r["owner"] != mn.OWNER:
                        self.assertFalse(r["va"] < PAGE + 0x1000 and r["va"] + r["size"] > PAGE, r)
        without = {(r["owner"], r["kind"], r.get("owner_offset", 0)): r for r in space.plan(union)["allocations"]
                   if r["owner"] != space.DIRECTORY_OWNER}
        with_ours = {(r["owner"], r["kind"], r.get("owner_offset", 0)): r
                     for r in space.plan(union + [request])["allocations"]}
        self.assertTrue(all(with_ours[k] == r for k, r in without.items()))
        # a pool owner bumped over the quarterback span lands at its end; one that would then straddle the page steps
        # past it, whether or not the page is requested (as the quarterback room test places them)
        filler = ("aa_synthetic_filler", "code", 0x1529000 - 0x80 - space.POOL_VA - space.PAGE, space.PAGE)
        straddle = ("ab_synthetic_straddle", "code", 0x20000, 16)
        for requests in ([filler, straddle], [filler, straddle, request]):
            rows = space.plan(requests)["allocations"]
            self.assertEqual(next(r for r in rows if r["owner"] == straddle[0])["va"], PAGE + 0x1000)
        self.assertEqual(PAGE, 0x1530000)
        self.assertGreaterEqual(PAGE, space.FIXED_SPAN_END)


class NumberZero(unittest.TestCase):
    """Number 0 on the uniform: the selector 0x8E910 (every jersey, shoulder and helmet number goes through it) binds a
    number below 10 to the M cell with digit texture n of the family and slot; 0 is not special-cased (0xFF, not 0, is
    "no material", in the binder). So #0 shows the very texture the ones digit of 10, 20, ... 90 already shows."""

    def test_zero_binds_the_same_glyph_as_the_zero_of_ten(self):
        _need_retail()
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(Path(RETAIL_XBE).read_bytes(), trace_writes=False)
        model, mats = m.ARENA + 0x1000, m.ARENA + 0x2000
        m.put(model + 0x1C, 8)
        m.put(model + 0x20, mats)
        for k in range(90):                                 # the digit texture table (3 x (digit + 10 x family) + slot)
            m.put(0xA86C04 + 4 * k, 0x7000 + k)
        for lod in range(4):
            m.uc.mem_write(0xA86D6C + 3 * lod, bytes((1, 2, 3)))   # row 0 (NUMBER_): L, M, R material indexes

        def bind(number, family, slot):
            m.uc.mem_write(mats, bytes(8 * 128))
            m.call(0x8E910, eax=number, ecx=0, edx=family, args=(model, 0, 0, slot))
            return [m.get(mats + 128 * idx + 0x30) for idx in (1, 2, 3)]   # L, M, R textures

        for family in (0xC, 0xD, 0xE):                      # jersey, helmet, shoulder fonts
            for slot in (0, 1):                             # home and road packages
                zero = bind(0, family, slot)
                self.assertEqual((zero[0], zero[2]), (0, 0))
                self.assertNotEqual(zero[1], 0)
                for tens in range(1, 10):
                    self.assertEqual(bind(10 * tens, family, slot)[2], zero[1], (family, slot, tens))


# ------------------------------------------------------------------------------------------------ IR returns
class InjuredReserveReturns(unittest.TestCase):
    """The duplicate the panel traced (control 2026: 58 of 59 new active-list duplicates): a man on injured reserve keeps
    his number, the retail jersey routine (active list only) gives it to a signing while he is out, and his return (no
    jersey call) makes two. The shipped roster already holds one such pair (LAR K #19, Grupe on IR, McManus active), which
    surfaces at week 9 in every root. Modern IR (this revision) sends a returner whose number a club-mate wears through
    the jersey routine first; a returner whose number is free keeps it. The game's own code on retail + modern IR and the
    retail roster (as tests/mod_editor/test_nfl2k5_injured_reserve.GameTests); with and without the numbers owner.
    Fails on d849800cc (the earlier IR revision)."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_injured_reserve as ir
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes, retail_roster
        _need_retail()
        data = retail_bytes()
        cls.ir = ir
        cls.with_ir = ir.apply(data, "modern")[0]
        cls.both = mn.apply(cls.with_ir)[0]
        cls.body = retail_roster()

    def boot(self, payload):
        from tests.mod_editor.test_nfl2k5_injured_reserve import GameTests
        helper = GameTests()
        helper.payload, helper.body = payload, self.body
        helper.store_va = self.ir.store_va(payload)
        m = helper.boot(payload, human=0)
        return helper, m

    def numbers(self, m, roster):
        return [(m.get(p + 0x20) >> 3) & 0x7F for p in roster]

    def pair(self, helper, m, c):
        """Two active club-mates of one position (A goes on IR, then B takes A's number)."""
        roster = helper.roster(m, c)
        by = collections.defaultdict(list)
        for p in roster:
            by[m.uc.mem_read(p + 0x35, 1)[0]].append(p)
        pos = next(k for k in (3, 4, 15) if len(by[k]) >= 2)
        return by[pos][0], by[pos][1]

    def give(self, m, p, number):
        m.put(p + 0x20, (m.get(p + 0x20) & ~0x3F8) | number << 3)

    def check(self, helper, m, c, a, own):
        """He is back, wears his own number, and no two club-mates share one."""
        roster = helper.roster(m, c)
        self.assertIn(a, roster)
        nums = self.numbers(m, roster)
        self.assertEqual(len(nums), len(set(nums)), sorted(nums))
        self.assertEqual((m.get(a + 0x20) >> 3) & 0x7F, own)

    def test_the_rollover_return(self):
        for label, payload in (("modern IR", self.with_ir), ("modern IR + modern numbers", self.both)):
            with self.subTest(label):
                helper, m = self.boot(payload)
                c = 12
                a, b = self.pair(helper, m, c)
                own = (m.get(a + 0x20) >> 3) & 0x7F
                helper.hurt(m, a, 9)
                helper.week(m)
                self.assertEqual(helper.store(m, c)[2][0][0], a)
                self.give(m, b, own)                                       # an older build gave his number away
                m.call(0x246F90, budget=400_000_000)
                self.check(helper, m, c, a, own)
                b_new = (m.get(b + 0x20) >> 3) & 0x7F
                self.assertNotEqual(b_new, own)                            # the club-mate gets another one
                if payload is self.both:
                    self.assertTrue(mn.legal(m.uc.mem_read(b + 0x35, 1)[0], b_new))

    def test_the_rollover_keeps_the_rights_of_a_man_who_stays_on_ir(self):
        """Review S2: at the rollover the club is full after the first returner (A), so the second IR man (C) stays on
        IR. A quarterback club-mate (B) wears A's number and is renumbered; every other 0-19 number is worn, so C's
        number is the only one a page reading the store too early would see free. The renumbering runs after the store
        is rebuilt: B gets a number nobody on the club wears or holds, never C's. Fails on c02a1b9ae (B got C's)."""
        from mod_editor.core import nfl2k5_modern_numbers as numbers
        helper, m = self.boot(self.both)
        c = next(k for k in range(32) if not any(numbers.retired(k, n) for n in range(30))
                 and any(m.uc.mem_read(p + 0x35, 1)[0] == 0 for p in helper.roster(m, k)))
        roster = helper.roster(m, c)
        b = next(p for p in roster if m.uc.mem_read(p + 0x35, 1)[0] == 0)
        hurt = [p for p in roster if p != b][:2]
        for p in hurt:
            helper.hurt(m, p, 9)
        helper.week(m)
        stored = [e[0] for e in helper.store(m, c)[2]]
        self.assertEqual(sorted(stored), sorted(hurt))
        a, c_man = stored                                                  # the store's order: A returns first
        x, y = 3, 7
        self.give(m, a, x)
        self.give(m, c_man, y)
        self.give(m, b, x)                                                 # an older build gave A's number away
        others = [p for p in helper.roster(m, c) if p != b]
        wanted = [n for n in range(20) if n not in (x, y)]
        for k, p in enumerate(others):                                     # 0-19 but C's 7 is worn; the rest 30 and up
            self.give(m, p, wanted[k] if k < len(wanted) else 30 + k % 60)
        club = helper.club(m, c)
        agents = m.get(m.root + 0x3C)
        k = 0
        while len(helper.roster(m, c)) < 64:                               # A's return takes the 65th slot
            p = m.get(agents + 4 * k)
            k += 1
            if p and p not in helper.roster(m, c):
                self.give(m, p, 30 + k % 60)
                m.call(0xC3EE0, ecx=club, edx=p)
        m.call(0x246F90, budget=400_000_000)
        self.assertIn(a, helper.roster(m, c))
        n, _returns, entries = helper.store(m, c)
        self.assertEqual((n, entries[0][0]), (1, c_man))                   # C stays on IR, with his number
        self.assertEqual((m.get(c_man + 0x20) >> 3) & 0x7F, y)
        self.assertEqual((m.get(a + 0x20) >> 3) & 0x7F, x)
        got = (m.get(b + 0x20) >> 3) & 0x7F
        self.assertNotIn(got, (x, y))
        worn = [(m.get(p + 0x20) >> 3) & 0x7F for p in helper.roster(m, c) if p != b]
        self.assertNotIn(got, worn)

    def test_the_weekly_return_and_a_free_number_untouched(self):
        for label, payload in (("modern IR", self.with_ir), ("modern IR + modern numbers", self.both)):
            for taken in (True, False):
                with self.subTest(label, taken=taken):
                    helper, m = self.boot(payload)
                    c = 5
                    a, b = self.pair(helper, m, c)
                    own, b_own = (m.get(a + 0x20) >> 3) & 0x7F, (m.get(b + 0x20) >> 3) & 0x7F
                    helper.hurt(m, a, 6)
                    helper.week(m)
                    self.assertEqual(helper.store(m, c)[2][0][0], a)
                    if taken:
                        self.give(m, b, own)
                    helper.heal(m, a)
                    helper.play(m, c, 4)
                    helper.week(m)
                    self.assertEqual(helper.store(m, c)[0], 0)
                    self.check(helper, m, c, a, own)
                    b_now = (m.get(b + 0x20) >> 3) & 0x7F
                    self.assertNotEqual(b_now, own)                         # the club-mate never keeps the returner's
                    if not taken:
                        self.assertEqual(b_now, b_own)                      # and is not touched when he had his own

    def test_burrow(self):
        """The owner's case: the starting QB goes on injured reserve, the club signs players (QBs who arrive wearing his
        number), he comes back and wears his own number. With modern numbers nobody is given it while he is out; with
        modern IR alone (a 2004 jersey routine) the club-mate who was given it is renumbered at his return."""
        from tests.nfl2k5_supersim_draft_fixture import Machine  # noqa: F401
        for label, payload in (("modern IR + modern numbers", self.both), ("modern IR", self.with_ir)):
            with self.subTest(label):
                helper, m = self.boot(payload)
                c = 2
                team = helper.club(m, c)
                qbs = [p for p in helper.roster(m, c) if m.uc.mem_read(p + 0x35, 1)[0] == 0]
                burrow = qbs[0]
                own = (m.get(burrow + 0x20) >> 3) & 0x7F
                helper.hurt(m, burrow, 6)
                helper.week(m)
                self.assertEqual(helper.store(m, c)[2][0][0], burrow)
                root = m.get(0xB72918)
                table, count = m.get(root + 4), m.get(root)
                for p in [q for q in helper.roster(m, c) if m.uc.mem_read(q + 0x35, 1)[0] != 0][-3:]:
                    m.call(0xC3EB0, ecx=team, edx=p)                       # room: three released, so nobody is cut
                signed = []
                for i in range(count - 1, 0, -1):                          # free agents of the league table
                    p = table + 0x54 * i
                    if len(signed) == 3:
                        break
                    if p in helper.roster(m, c) or m.uc.mem_read(p + 0x35, 1)[0] != 0:
                        continue
                    m.put(p + 0x20, (m.get(p + 0x20) & ~0x3F8) | own << 3)  # he arrives wearing the starter's number
                    m.uc.mem_write(p + 0x25, b"\x06")
                    m.uc.mem_write(m.STACK, struct.pack("<2I", SIGNING_RET, 1))
                    for name, value in dict(ECX=p, EDX=team, ESP=m.STACK).items():
                        m.reg(name, value)
                    m.uc.emu_start(0x2BD260, SIGNING_RET, count=5_000_000)  # the signing's jersey call
                    m.call(0xC3EE0, ecx=team, edx=p)                       # and onto the active list
                    signed.append(p)
                numbers = [(m.get(p + 0x20) >> 3) & 0x7F for p in signed]
                if payload is self.both:
                    self.assertNotIn(own, numbers)                         # nobody is given his number while he is out
                else:
                    self.assertIn(own, numbers)                            # the 2004 routine gave it away
                helper.heal(m, burrow)
                helper.play(m, c, 4)
                helper.week(m)
                self.assertEqual(helper.store(m, c)[0], 0)
                self.assertTrue(all(p in helper.roster(m, c) for p in signed))   # nobody was cut to make room
                self.check(helper, m, c, burrow, own)

    def test_earlier_beta_81_installs_read_previous_and_update_in_place(self):
        _need(KEPT_XBE, KEPT_XBE_SHA)
        from mod_editor.core import nfl2k5_injured_reserve_code_b81_pre_numbers as pre
        built = KEPT_XBE.read_bytes()
        self.assertEqual(self.ir.status(built), "previous")
        self.assertIs(self.ir.installed_revision(built), pre)
        upgraded = self.ir.apply(built, "modern", standard_guard=True)[0]
        self.assertEqual(self.ir.status(upgraded), "applied")
        self.assertEqual(self.ir.apply(upgraded, "modern", standard_guard=True)[0], upgraded)
        both = mn.apply(upgraded)[0]
        self.assertEqual((self.ir.status(both), mn.status(both)), ("applied", "applied"))


# ------------------------------------------------------------------------------------------------ the Studio
class StudioWiring(unittest.TestCase):
    """T10 (Studio): the plan field, presets, recipes, the full-build step, the in-place route and the Build tab."""

    def test_plan_presets_and_recipes(self):
        from mod_editor.core import mod_build as build
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("modern_numbers", settings.FEATURE_KEYS)
        for name in build.PRESETS:
            with self.subTest(preset=name):
                plan = build.apply_preset(build.BuildPlan("a.iso", "b.iso"), name)
                self.assertEqual(build._modern_numbers_level(plan), "modern" if plan.season_2026 else None)
        plan = build.apply_preset(build.BuildPlan("a.iso", "b.iso"), "softdrink_experimental")
        self.assertEqual(plan.modern_numbers, "modern")
        self.assertEqual(plan.to_recipe()["modern_numbers"], "modern")
        level = build._modern_numbers_level
        self.assertNotIn("modern_numbers", build.BuildPlan("a.iso", "b.iso").to_recipe())   # None follows season_2026
        self.assertEqual(level(build.BuildPlan("a", "b", season_2026=True)), "modern")
        self.assertIsNone(level(build.BuildPlan("a", "b")))
        self.assertEqual(level(build.BuildPlan("a", "b", modern_numbers="retail", season_2026=True)), "retail")
        self.assertIsNone(level(build.BuildPlan("a", "b", modern_numbers=False, season_2026=True)))   # box left clear
        self.assertEqual(level(build.BuildPlan("a", "b", modern_numbers=True)), "modern")
        with self.assertRaises(ValueError):
            level(build.BuildPlan("a", "b", modern_numbers="bogus"))
        self.assertTrue(build.BuildPlan("a", "b", modern_numbers="retail").wants_xbe_patch())
        self.assertEqual(build.modern_numbers_disc_edit("a", "b").modern_numbers, "modern")
        with self.assertRaises(ValueError):
            build.modern_numbers_disc_edit("a", "b", mode="aggressive")

    def test_the_in_place_route_on_a_built_executable(self):
        """edit-modern-numbers (preflight on the built executable): Modern adds the page and site, Retail empties them,
        and the route writes exactly the owner's bytes."""
        _need(KEPT_XBE, KEPT_XBE_SHA)
        from mod_editor.core import mod_build as build
        base = KEPT_XBE.read_bytes()
        applied = mn.apply(base)[0]
        for mode, source, expected in (("modern", base, applied), ("retail", applied, mn.remove(applied)[0]),
                                       ("modern", applied, applied)):
            with self.subTest(mode=mode):
                plan = build.modern_numbers_disc_edit("in.iso", "out.iso", mode=mode)
                self.assertTrue(build._only_modern_numbers_changes(plan))
                receipt = {"steps": []}
                self.assertTrue(build._edit_installed_modern_numbers(plan, plan.source, plan.target, source, receipt,
                                                                     lambda *_: None, preflight=True, consume=False,
                                                                     reference=None))
                update = receipt["modern_numbers_source_update"]
                self.assertEqual(update["result_sha256"], hashlib.sha256(expected).hexdigest())
        plan = build.modern_numbers_disc_edit("in.iso", "out.iso")
        foreign = OwnerStates._patched(None, base, mn.SITE_VA, b"\x90" * 6)
        with self.assertRaisesRegex(ValueError, "changed by another tool"):
            build._edit_installed_modern_numbers(plan, plan.source, plan.target, foreign, {"steps": []},
                                                 lambda *_: None, preflight=True, consume=False, reference=None)

    def test_64_mb_builds_leave_modern_numbers_out(self):
        """Review M1: the page needs the 128 MB scale-out pool. At 64 MB every preset and the recommended 64 MB profile
        leave the option out, the memory model lists it among the 128 MB options, an explicit Modern is refused, and
        the in-place route refuses a disc built without the 128 MB requirement. Fails on c02a1b9ae (the presets
        set "modern" at 64 MB and the build failed at its last executable step)."""
        from unittest import mock
        from mod_editor.core import mod_build as build
        from mod_editor.core import nfl2k5_memory_budget as budget
        level = build._modern_numbers_level
        self.assertIn("modern_numbers", budget.REQUIRES_128)
        for name in build.PRESETS:
            with self.subTest(preset=name):
                small = build.apply_preset(build.BuildPlan("a.iso", "b.iso", console_memory=64), name)
                self.assertIs(small.modern_numbers, False)
                self.assertIsNone(level(small))
                big = build.apply_preset(build.BuildPlan("a.iso", "b.iso"), name)
                profile = budget.profile_64_plan(big)
                self.assertFalse(budget.on(profile, "modern_numbers"))
                self.assertNotIn("modern_numbers", budget.forced_off(profile, 64))
                self.assertIn("modern_numbers", budget.forced_off({**budget.options(big), "modern_numbers": "modern"}, 64))
        self.assertIsNone(level(build.BuildPlan("a", "b", console_memory=64, season_2026=True)))   # follows: left out
        for value in (True, "modern"):
            with self.assertRaisesRegex(ValueError, "128 MB"):
                level(build.BuildPlan("a", "b", console_memory=64, modern_numbers=value))
        self.assertIsNone(level(build.BuildPlan("a", "b", console_memory=64, modern_numbers=False)))
        _need(KEPT_XBE, KEPT_XBE_SHA)
        base = KEPT_XBE.read_bytes()
        plan = build.modern_numbers_disc_edit("in.iso", "out.iso")
        with mock.patch.object(build.tt.k128_patch, "read_settings", return_value={"status": "applied", "require_128": False}):
            for mode in ("modern", "retail"):
                plan = build.modern_numbers_disc_edit("in.iso", "out.iso", mode=mode)
                with self.assertRaisesRegex(ValueError, "128 MB standard disc"):
                    build._edit_installed_modern_numbers(plan, plan.source, plan.target, base, {"steps": []},
                                                         lambda *_: None, preflight=True, consume=False, reference=None)

    def test_the_cli_route(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("modpack_cli", ROOT / "tools/nfl2k5_modpack.py")
        text = (ROOT / "tools/nfl2k5_modpack.py").read_text(encoding="utf-8")
        self.assertIn('"edit-modern-numbers"', text)
        self.assertIn("modern_numbers_disc_edit(args.source, args.out, mode=args.mode)", text)
        del spec

    def test_build_tab(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication
        except ImportError:
            raise unittest.SkipTest("PyQt5 absent")
        import tempfile
        from mod_editor.core import mod_build as build
        from mod_editor.gui import build_panel_qt
        app = type(self)._qt_app = QApplication.instance() or QApplication([])
        self.assertIn("modern_numbers", build_panel_qt.BUILD_KEYS)
        self.assertEqual(build_panel_qt.PREVIOUS_UPGRADE_KEYS.get("modern_numbers"), "modern jersey numbers")
        panel = build_panel_qt.BuildPanel()
        try:
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "disc.xiso.iso"
                source.write_bytes(b"x" * 4096)
                box = panel._boxes()["modern_numbers"]
                self.assertEqual(box.text().replace("&&", "&"), mn.BUILD_CAPTION)
                for state, enabled, badge in (("retail", True, None), ("previous", True, "Needs update"),
                                              ("applied", False, "Already installed"),
                                              ("foreign", False, "Unrecognized source data")):
                    values = {key: "retail" for key in panel._boxes()}
                    values.update(path=str(source), container="xiso", throw=None, speed_threshold="retail",
                                  modern_numbers=state)
                    panel.apply_state(values)
                    app.processEvents()
                    self.assertEqual(box.isEnabled(), enabled, state)
                    if badge:
                        self.assertEqual(panel._badges["modern_numbers"].text(), badge)
                values = {key: "retail" for key in panel._boxes()}
                values.update(path=str(source), container="xiso", throw=None, speed_threshold="retail")
                panel.apply_state(values)
                box.setChecked(True)
                self.assertIs(panel.plan().modern_numbers, True)
                box.setChecked(False)
                self.assertIs(panel.plan().modern_numbers, False)
        finally:
            panel.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
