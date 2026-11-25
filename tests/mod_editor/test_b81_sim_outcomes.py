"""Beta 81 game outcomes: execute the simulated-outcomes page (home field and form, two-point chart, tie roll) on
synthetic simulator state, and install it on a real standard executable.

Native classes run the shipped page and assert the new behaviour; each also runs the retail bytes on the same state and
asserts they behave differently, so the tests fail on the old code.  The executable checks use
``NFL2K5_B81_SIM_OUTCOMES_XBE`` (a built beta 81 standard default.xbe; the combined calibration's frozen candidate) or,
failing that, ``B81_HISTORY_POOL_FULL_XBE`` (the same file in the b81 environment), and ``NFL2K5_RETAIL_XBE``.
"""
from __future__ import annotations

import os
import struct
import unittest
from pathlib import Path

from mod_editor.core import nfl2k5_sim_outcomes as so
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

PAGE = 0x1000
PAGE_VA = 0x1534000
STACK = 0x00200000
RETURN = 0x00300000          # a fake caller of 0x106480 / 0x103260
COMMIT_RESUME = so.COMMIT_RESUME
TIES_ROLL, TIES_SKIP = so.TIES_SITE + 5, so.TIES_SKIP
# 0x100F00 (retail): cvttss2si eax, [esp+4] ; ret 4
FLOAT_TO_INT = bytes.fromhex("f30f2c442404c20400")
# The retail two-point chooser 0x103260..0x1032EF (144 bytes, its jump tables and padding included), for the failing-first comparison.
RETAIL_TRY = bytes.fromhex(
    "51a19c71a900e895efffffd95c2400a1a071a900e887efffffd86c240051d91c24e87adcffff83c00983f80e771e0fb680dc32"
    "1000ff2485d03210008b0df071a90033c083f9030f94c059c3b9a0fce500e8da58f4ffd81d40fe4e00dfe0f6c4057a07b80100"
    "000059c333c059c38bff9c321000ca321000ac3210000002020200010200010200020200009090909090")


def f32(value):
    return struct.unpack("<f", struct.pack("<f", value))[0]


def mix32(h):
    h &= 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h


def model_factors(season, week, home, away, w0, w1, edge=so.HOME_EDGE, sigma=so.FORM_SIGMA):
    """The page's fixture rule in Python (DESIGN.txt, simulated outcomes): (home factor, away factor)."""
    key = mix32((season * so.GOLDEN) & 0xFFFFFFFF ^ week)
    key = mix32(key ^ home)
    key = mix32(key ^ away)
    seed = mix32(mix32(key ^ w0) ^ w1)
    out = []
    for tag, scale in ((so.HOME_TAG, 1 + edge), (so.AWAY_TAG, 1 - edge)):
        h = mix32(seed ^ tag)
        z = (sum((h >> s) & 0xFF for s in (0, 8, 16, 24)) - so.IRWIN_HALL_MEAN) * f32(sigma / so.IRWIN_HALL_SD)
        m = f32(f32(1.0 + z) * f32(scale))
        out.append(min(max(m, f32(so.M_LOW)), f32(so.M_HIGH)))
    return out


class _Machine:
    def __init__(self, page):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn import x86_const as x
        self.x = x
        self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        self.mapped = set()
        self.put(PAGE_VA, page)
        self.map(STACK - 0x4000, 0x8000)
        self.map(RETURN, 16)
        self.map(0x00A96000, 0x2000)
        self.map(0x00E57000, 0x1000)
        self.map(0x00E5F000, 0x1000)
        self.put(0x00100F00, FLOAT_TO_INT)
        # 0x102200 stand-in: eax = side summary -> st0 = that side's score (floats at 0xA97300 / 0xA97304)
        stub = (bytes.fromhex("3d") + struct.pack("<I", so.HOME_SIDE) + bytes.fromhex("7507")
                + bytes.fromhex("d905") + struct.pack("<I", 0xA97300) + b"\xc3"
                + bytes.fromhex("d905") + struct.pack("<I", 0xA97304) + b"\xc3")
        self.put(0x00102200, stub)
        for at in (COMMIT_RESUME, TIES_ROLL, TIES_SKIP):
            self.map(at, 1)
        self.reg("ESP", STACK)

    def map(self, at, size):
        for page in range(at & ~(PAGE - 1), at + size, PAGE):
            if page not in self.mapped:
                self.uc.mem_map(page, PAGE)
                self.mapped.add(page)

    def put(self, at, raw):
        self.map(at, len(raw))
        self.uc.mem_write(at, bytes(raw))

    def u32(self, at, value):
        self.put(at, struct.pack("<I", value & 0xFFFFFFFF))

    def f(self, at, value):
        self.put(at, struct.pack("<f", value))

    def get_f(self, at):
        return struct.unpack("<f", bytes(self.uc.mem_read(at, 4)))[0]

    def get_u32(self, at):
        return struct.unpack("<I", bytes(self.uc.mem_read(at, 4)))[0]

    def reg(self, name, value=None):
        register = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value & 0xFFFFFFFF)

    def run(self, start, stops):
        from unicorn import UC_HOOK_CODE
        landed = []

        def stop(uc, address, size, user):
            landed.append(address)
            uc.emu_stop()
        hooks = [self.uc.hook_add(UC_HOOK_CODE, stop, begin=at, end=at) for at in stops]
        self.uc.emu_start(start, 0xFFFFFFFF, count=5000)
        for hook in hooks:
            self.uc.hook_del(hook)
        assert landed, "the routine did not reach any stop address"
        return landed[0]


def _fixture(m, season=2, week=5, home=0x00B10000, away=0x00B10200, w0=0x12345678, w1=0x9ABCDEF0):
    m.u32(so.SEASON, season)
    m.u32(so.WEEK, week)
    m.u32(so.HOME_SIDE, home)
    m.u32(so.AWAY_SIDE, away)
    m.u32(so.MATCH_WORDS[0], w0)
    m.u32(so.MATCH_WORDS[1], w1)
    m.u32(so.SIM_RECORD, 0x00E53800)
    return model_factors(season, week, home, away, w0, w1)


@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the page")
class CommitHook(unittest.TestCase):
    """0x106480's entry: the offense's positive gain short of the goal line times its game factor."""

    def commit(self, m, gain, *, side=0, kind=0, line=50.0):
        m.u32(so.SIM_KIND, kind)
        m.u32(so.SIM_OFFENSE, so.HOME_SIDE if side == 0 else so.AWAY_SIDE)
        m.f(so.SIM_LINE_TO_GOAL, line)
        m.reg("ESP", STACK - 8)
        m.u32(STACK - 8, RETURN)
        m.f(STACK - 4, gain)
        landed = m.run(PAGE_VA + so.labels()["commit"], [COMMIT_RESUME, RETURN])
        self.assertEqual(landed, COMMIT_RESUME)
        self.assertEqual(m.reg("ECX"), 0x00E53800, "the replayed first instruction")
        self.assertEqual(m.reg("ESP"), STACK - 8, "the stack is as the caller left it")
        return m.get_f(STACK - 4)

    def test_home_and_away_factors_follow_the_rule(self):
        m = _Machine(so.code_for(PAGE_VA))
        home, away = _fixture(m)
        self.assertAlmostEqual(self.commit(m, 10.0, side=0), f32(10.0 * home), places=4)
        self.assertAlmostEqual(self.commit(m, 10.0, side=1), f32(10.0 * away), places=4)
        self.assertEqual(m.get_u32(PAGE_VA + so.STATE_OFF + so.S_FIXTURES), 1, "one fixture seen")

    def test_home_edge_without_form_is_exactly_one_plus_minus_edge(self):
        m = _Machine(so.code_for(PAGE_VA, home_edge=0.05, form_sigma=0.0))
        _fixture(m)
        self.assertAlmostEqual(self.commit(m, 8.0, side=0), 8.0 * 1.05, places=4)
        self.assertAlmostEqual(self.commit(m, 8.0, side=1), 8.0 * 0.95, places=4)

    def test_touchdowns_losses_and_tries_are_unchanged(self):
        m = _Machine(so.code_for(PAGE_VA, home_edge=0.1, form_sigma=0.0))
        _fixture(m)
        self.assertEqual(self.commit(m, 50.0, line=50.0), 50.0)       # reaches the goal line: a touchdown stays
        self.assertEqual(self.commit(m, 61.0, line=50.0), 61.0)       # a promoted breakaway (distance + 1)
        self.assertEqual(self.commit(m, -3.0), -3.0)
        self.assertEqual(self.commit(m, 0.0), 0.0)
        self.assertEqual(self.commit(m, 1.5, kind=4, line=2.0), 1.5)  # a two-point try
        self.assertEqual(self.commit(m, 9.0, kind=1), 9.0)            # a kickoff
        self.assertEqual(m.get_u32(PAGE_VA + so.STATE_OFF + so.S_SCALED), 0)

    def test_factor_is_kept_for_the_fixture_and_redrawn_for_the_next(self):
        m = _Machine(so.code_for(PAGE_VA))
        home, _ = _fixture(m)
        first = self.commit(m, 10.0)
        m.u32(so.MATCH_WORDS[0], 0x0BADF00D)       # the generator moves during a game: the factor must not
        self.assertEqual(self.commit(m, 10.0), first)
        home2, _ = _fixture(m, week=6, w0=0x0BADF00D)
        self.assertAlmostEqual(self.commit(m, 10.0), f32(10.0 * home2), places=4)
        self.assertEqual(m.get_u32(PAGE_VA + so.STATE_OFF + so.S_FIXTURES), 2)

    def test_the_match_generator_is_only_read(self):
        m = _Machine(so.code_for(PAGE_VA))
        _fixture(m)
        before = bytes(m.uc.mem_read(0x00E5FCA0, 0x200))
        self.commit(m, 10.0)
        self.assertEqual(bytes(m.uc.mem_read(0x00E5FCA0, 0x200)), before)

    def test_form_spread_and_clamp(self):
        """Over 4,000 synthetic fixtures the factors have the declared spread around 1 +/- edge, inside the clamp."""
        homes, aways = [], []
        for i in range(4000):
            h, a = model_factors(i % 20, i // 20, 0x00B10000 + 500 * (i % 32), 0x00B10000 + 500 * ((i * 7 + 3) % 32),
                                 mix32(i), mix32(i + 99))
            homes.append(h)
            aways.append(a)
        mean = sum(homes) / len(homes)
        sd = (sum((x - mean) ** 2 for x in homes) / len(homes)) ** 0.5
        self.assertAlmostEqual(mean, 1 + so.HOME_EDGE, delta=0.01)
        self.assertAlmostEqual(sum(aways) / len(aways), 1 - so.HOME_EDGE, delta=0.01)
        self.assertAlmostEqual(sd, so.FORM_SIGMA * (1 + so.HOME_EDGE), delta=0.01)
        self.assertTrue(all(f32(so.M_LOW) <= x <= f32(so.M_HIGH) for x in homes + aways))   # the clamp's float32 bounds

    def test_retail_entry_leaves_the_gain_alone(self):
        """Failing first: the retail first instruction of 0x106480 does not touch the gain (no home edge)."""
        m = _Machine(so.code_for(PAGE_VA))
        _fixture(m)
        m.put(so.COMMIT_SITE, so.COMMIT_RETAIL)
        m.reg("ESP", STACK - 8)
        m.u32(STACK - 8, RETURN)
        m.f(STACK - 4, 10.0)
        m.u32(so.SIM_KIND, 0)
        m.u32(so.SIM_OFFENSE, so.HOME_SIDE)
        m.run(so.COMMIT_SITE, [COMMIT_RESUME])
        self.assertEqual(m.get_f(STACK - 4), 10.0)
        self.assertNotEqual(self.commit(m, 10.0), 10.0)


def chart_reference(margin, period, fraction):
    """Modern 2 (nfl2k5_cpu_money_downs.two_point_decision) on the simulator's clock: True = go for two. Game time left
    in units of 10 s is (3 - period + fraction) x 90, as the page computes it (exact for these values in both)."""
    if period >= 4:
        return margin in (-2, -1)
    if not -16 <= margin <= 16:
        return False
    thr = so.two_point_thresholds()[margin + 16]
    return thr == 255 or (thr > 0 and (3 - period + f32(fraction)) * 90.0 <= thr)


@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the page")
@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the page")
class GoalLine(unittest.TestCase):
    """Touchdown mix part 1: a run or scramble snapped inside the 5 whose gain reaches the goal line scores with the keep
    chance for its distance; otherwise the ball stops at the 1. Passes, gains short of the line, longer runs and kicks
    are untouched; a two-point run is filtered too."""
    RUN, SCRAMBLE = so.GOAL_LINE_RUN_RETURNS
    PASS = 0x0010921F                     # another 0x106480 call (a completion): never filtered

    def commit(self, m, gain, *, line, ret=None, kind=0, side=0):
        m.u32(so.SIM_KIND, kind)
        m.u32(so.SIM_OFFENSE, so.HOME_SIDE if side == 0 else so.AWAY_SIDE)
        m.f(so.SIM_LINE_TO_GOAL, line)
        m.reg("ESP", STACK - 8)
        m.u32(STACK - 8, self.RUN if ret is None else ret)
        m.f(STACK - 4, gain)
        m.reg("EBX", 0x1234)
        landed = m.run(PAGE_VA + so.labels()["commit"], [COMMIT_RESUME, RETURN])
        self.assertEqual(landed, COMMIT_RESUME)
        self.assertEqual((m.reg("ESP"), m.reg("EBX")), (STACK - 8, 0x1234))
        self.assertEqual(m.reg("FPSW") >> 11 & 7, 0, "the x87 stack is left as found")
        return m.get_f(STACK - 4)

    def counters(self, m):
        state = PAGE_VA + so.STATE_OFF
        return m.get_u32(state + so.S_GOAL_SEEN), m.get_u32(state + so.S_GOAL_STOPPED)

    def test_always_and_never(self):
        m = _Machine(so.code_for(PAGE_VA, home_edge=0.0, form_sigma=0.0, goal_line=(0, 0, 0, 0)))
        _fixture(m)
        for line, stopped in ((1.0, 0.0), (2.0, 1.0), (3.0, 2.0), (4.0, 3.0), (5.0, 4.0), (0.5, 0.0), (1.4, 0.4)):
            with self.subTest(line=line):
                self.assertAlmostEqual(self.commit(m, line, line=line), stopped, places=5)
                self.assertAlmostEqual(self.commit(m, line + 7.0, line=line, ret=self.SCRAMBLE), stopped, places=5)
        self.assertEqual(self.counters(m), (14, 14))
        m = _Machine(so.code_for(PAGE_VA, home_edge=0.0, form_sigma=0.0, goal_line=(1, 1, 1, 1)))
        _fixture(m)
        for line in (1.0, 2.0, 3.0, 5.0):
            self.assertEqual(self.commit(m, line, line=line), line)
        self.assertEqual(self.counters(m), (4, 0))

    def test_only_goal_line_runs_and_tries(self):
        m = _Machine(so.code_for(PAGE_VA, home_edge=0.0, form_sigma=0.0, goal_line=(0, 0, 0, 0)))
        _fixture(m)
        self.assertEqual(self.commit(m, 3.0, line=3.0, ret=self.PASS), 3.0)        # a pass touchdown stands
        self.assertEqual(self.commit(m, 3.0, line=3.0, ret=RETURN), 3.0)
        self.assertEqual(self.commit(m, 2.0, line=3.0), 2.0)                       # short of the line
        self.assertEqual(self.commit(m, 6.0, line=6.0), 6.0)                       # snapped at the 6
        self.assertEqual(self.commit(m, 9.0, line=5.0, kind=1), 9.0)               # a kickoff
        self.assertEqual(self.counters(m), (0, 0))
        self.assertEqual(self.commit(m, 2.0, line=2.0, kind=4), 1.0)               # a two-point run from the 2
        self.assertEqual(self.counters(m), (1, 1))

    def test_draws_follow_the_model_and_the_keep_chances(self):
        keep = (0.69, 0.59, 0.54, 0.55)
        m = _Machine(so.code_for(PAGE_VA, home_edge=0.0, form_sigma=0.0, goal_line=keep))
        stops = [0, 0, 0, 0]
        for fixture in range(40):
            _fixture(m, season=fixture % 7, week=fixture, w0=mix32(fixture), w1=mix32(fixture + 1000))
            self.commit(m, 1.0, line=50.0)                 # an ordinary play: the new fixture's seed is current
            seed = m.get_u32(PAGE_VA + so.STATE_OFF + so.S_SEED)
            for line, bucket in ((1.0, 0), (2.0, 1), (3.0, 2), (5.0, 3)) * 25:
                seen = self.counters(m)[0]
                got = self.commit(m, line, line=line)
                draw = mix32(((seed ^ so.GOAL_TAG) + seen * so.GOLDEN) & 0xFFFFFFFF) & 0xFFFF
                self.assertEqual(got == line, draw < round(keep[bucket] * 65536), (fixture, line, seen))
                stops[bucket] += got != line
        for bucket, q in enumerate(keep):
            self.assertAlmostEqual(stops[bucket] / 1000, 1 - q, delta=0.05, msg=bucket)

    def test_keep_chances_read_back(self):
        page = so.code_for(PAGE_VA, home_edge=0.05, form_sigma=0.1, goal_line=(0.6, 0.5, 0.45, 0.4))
        self.assertEqual(so._installed_levers(page)["goal_line"], (0.6, 0.5, 0.45, 0.4))
        self.assertEqual(so._installed_levers(so.code_for(PAGE_VA))["goal_line"], tuple(so.GOAL_LINE_KEEP))
        for bad in ((0.5, 0.5, 0.5), (1.2, 0.5, 0.5, 0.5), (-0.1, 0.5, 0.5, 0.5)):
            with self.assertRaises(so.SimOutcomesError):
                so.code_for(PAGE_VA, goal_line=bad)


class RevisionPins(unittest.TestCase):
    """An installed page and its sites are recognised by rebuilding their bytes. These pins make any change to the page's
    code or constants (here or in a module it reads) a deliberate new revision: freeze this one first so discs built with
    it read "previous" and are upgraded in place, then re-pin (coordinator, 2026-11-25, after the fb-targets review S1)."""
    # Re-pinned for the goal-line filter, the move to 0x1534000 (0x1531000 is the awards page) and the regulation hook's
    # move to 0x106400 (0x106427 stays retail), before any release or integration build carried the page.
    PAGE = {(0.045, 0.08): "5f0bbe69df3567d8da088e08d4b81617827fc036ac6ef05e67b5ea6150cc8046",
            (0.07, 0.12): "27a47c5a9be23aaac7ac3751aba5ec9043defd08da8039b6925bb96ca734f069"}
    SITES = "3d2f1051f096612c2deb0563164eb9f4a2d863e23d5e2cc264bb67cd339859ed"

    def test_page_bytes_up_to_the_state_block(self):
        import hashlib
        for (home_edge, form_sigma), digest in self.PAGE.items():
            page = so.code_for(PAGE_VA, home_edge=home_edge, form_sigma=form_sigma)
            self.assertEqual(hashlib.sha256(page[:so.STATE_OFF]).hexdigest(), digest, (home_edge, form_sigma))

    def test_site_bytes(self):
        import hashlib
        rows = so.sites(PAGE_VA)
        self.assertEqual([row[0] for row in rows],
                         ["commit_entry", "two_point_chooser", "tie_roll_gate", "regulation_end", "state_step"])
        joined = b"".join(name.encode() + va.to_bytes(4, "little") + retail + after for name, va, retail, after in rows)
        self.assertEqual(hashlib.sha256(joined).hexdigest(), self.SITES)

    def test_frozen_two_point_chart_is_still_the_played_games(self):
        """Failing means the played game's Modern 2 chart changed: the simulator's copy is frozen with this revision, so
        decide whether the simulator follows (a new page revision that keeps this one readable) or not."""
        from mod_editor.core import nfl2k5_cpu_money_downs as downs
        self.assertEqual(so.TWO_POINT_THRESHOLDS, bytes(downs.m2_tables()[2]))
        self.assertIs(so.two_point_thresholds(), so.TWO_POINT_THRESHOLDS)


class TwoPointChart(unittest.TestCase):
    def decide(self, code_va, code, margin, period, fraction, offense_home=True):
        m = _Machine(so.code_for(PAGE_VA))
        if code_va != PAGE_VA:
            m.put(code_va, code)
        m.f(0xA97300, 20.0 + margin if offense_home else 20.0)
        m.f(0xA97304, 20.0 if offense_home else 20.0 + margin)
        m.u32(so.SIM_OFFENSE, so.HOME_SIDE if offense_home else so.AWAY_SIDE)
        m.u32(so.SIM_DEFENSE, so.AWAY_SIDE if offense_home else so.HOME_SIDE)
        m.u32(so.SIM_PERIOD_INDEX, period)
        m.f(so.SIM_CLOCK_FRACTION, fraction)
        m.reg("ESP", STACK - 4)
        m.u32(STACK - 4, RETURN)
        start = PAGE_VA + so.labels()["try"] if code_va == PAGE_VA else code_va
        self.assertEqual(m.run(start, [RETURN]), RETURN)
        self.assertEqual(m.reg("ESP"), STACK, "the chooser returns with its own stack popped")
        return m.reg("EAX")

    def test_page_equals_the_played_games_chart(self):
        for margin in range(-20, 21):
            for period in range(5):
                for fraction in (1.0, 0.8, 0.5, 0.25, 0.05, 0.0):
                    for home in (True, False):
                        want = chart_reference(margin, period, fraction)
                        self.assertEqual(bool(self.decide(PAGE_VA, None, margin, period, fraction, home)), want,
                                         (margin, period, fraction, home))

    def test_reference_matches_cpu_money_downs(self):
        """The simulator clock reading agrees with the played game's own function in regulation."""
        from mod_editor.core import nfl2k5_cpu_money_downs as downs
        for margin in range(-16, 17):
            for quarter in range(1, 5):
                for left in (899.0, 605.0, 455.0, 305.0, 125.0, 25.0, 19.0, 5.0):   # off the 10 s grid of the chart
                    played = downs.two_point_decision(margin=margin, quarter=quarter, seconds=left,
                                                      quarter_seconds=900.0)   # the quarter clock, as 205F80 reads it
                    self.assertEqual(chart_reference(margin, quarter - 1, left / 900.0), played,
                                     (margin, quarter, left))

    def test_retail_chooser_differs(self):
        """Failing first: retail goes for two only in the fourth quarter (and never at -1); the chart goes earlier."""
        retail_va = so.TRY_SITE
        self.assertFalse(self.decide(retail_va, RETAIL_TRY, -2, 2, 0.5))    # retail: -2 in the 3rd quarter, kick
        self.assertTrue(self.decide(PAGE_VA, None, -2, 2, 0.5))             # Modern 2: always at -2
        self.assertFalse(self.decide(retail_va, RETAIL_TRY, -1, 3, 0.01))   # retail never goes at -1
        self.assertTrue(self.decide(PAGE_VA, None, -1, 3, 0.01))            # Modern 2: -1 inside the last 20 s


@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the page")
class TieRoll(unittest.TestCase):
    FRAME = STACK - 0x100

    def gate(self, code_va, code, *, allowed, mode, stage):
        m = _Machine(so.code_for(PAGE_VA))
        m.put(code_va, code)
        m.reg("EBP", self.FRAME)
        m.reg("EBX", 0)
        m.u32(self.FRAME + 0x10, allowed)
        m.u32(so.MODE, mode)
        m.u32(so.STAGE, stage)
        m.reg("ESP", STACK - 0x200)
        landed = m.run(code_va, [TIES_ROLL, TIES_SKIP])
        self.assertEqual(m.reg("ESP"), STACK - 0x200, "the gate leaves the stack as it found it")
        return landed

    def site(self):
        return next(after for label, _va, _retail, after in so.sites(PAGE_VA) if label == "tie_roll_gate")

    def test_regular_season_rolls_whatever_the_stale_flag(self):
        self.assertEqual(self.gate(so.TIES_SITE, self.site(), allowed=0, mode=2, stage=8), TIES_ROLL)
        self.assertEqual(self.gate(so.TIES_SITE, self.site(), allowed=1, mode=2, stage=9), TIES_ROLL)

    def test_postseason_preseason_and_other_modes_keep_retail(self):
        for mode, stage in ((2, 9), (2, 7), (1, 8), (3, 8)):
            self.assertEqual(self.gate(so.TIES_SITE, self.site(), allowed=0, mode=mode, stage=stage), TIES_SKIP)

    def test_retail_skips_the_roll_after_season_one(self):
        """Failing first: retail rolls only on the caller's flag, which is 0 from a franchise's second season."""
        self.assertEqual(self.gate(so.TIES_SITE, so.TIES_RETAIL, allowed=0, mode=2, stage=8), TIES_SKIP)


# Retail 0x106400..0x106459, the period-advance routine 0x1061F0 after the period index is stored (eax): end of
# regulation (cmp eax,4 ; jle 0x106423), an expired overtime (0x106405: cmp edi,ebx ; jne 0x106427 ; the tie roll at
# 0x106409 ; jne 0x106427 ; another overtime period), the end of regulation (0x106423: cmp edi,ebx ; je 0x106450 ;
# 0x106427 game over ; tail returns 5) and the overtime kickoff 0x106450. Read from the retail executable
# (test_the_tail_is_retail checks it where the private retail image is present).
PERIOD_TAIL = 0x00106400
PERIOD_TAIL_RETAIL = bytes.fromhex(
    "83f8047e1e3bfb751ea1d471a90085c07515c705f071a900040000005f5e33c05b59c33bfb7429c705b871a900120000008b06a90000c00375"
    "0c25ffff7ffe0d0000400289065f5eb8050000005b59c3c705b871a90001000000")


@unittest.skipUnless(HAVE_UC, "Unicorn is required to execute the page")
class RegulationEnd(unittest.TestCase):
    """R8: a regulation end reached from a play's commit is decided on the scores after the play. The routine runs inside
    the real retail tail of 0x1061F0 with the site installed; 0x106427 (game over) stays retail because the expired
    overtime branches jump there."""
    PENDING = PAGE_VA + so.STATE_OFF + so.S_PENDING
    RETURN_OF_ROUTINE = 0x00106A40       # a stand-in for 0x1061F0's own return (the ret instructions land here)
    TAIL_END = (0x0010641C + 6, 0x0010644F, 0x00106450 + 10)   # ret 0 (period goes on), ret 5 (over), the kickoff

    def machine(self, site=None):
        m = _Machine(so.code_for(PAGE_VA))
        tail = bytearray(PERIOD_TAIL_RETAIL)
        site = site if site is not None else dict((l, a) for l, _va, _r, a in [(r[0], r[1], r[2], r[3])
                                                                                for r in so.sites(PAGE_VA)])["regulation_end"]
        tail[0:len(site)] = site
        m.put(PERIOD_TAIL, bytes(tail))
        m.map(self.RETURN_OF_ROUTINE, 1)
        m.map(so.FN_DISPATCH, 1)
        return m

    def advance(self, m, *, period, caller, home, away, tie_allowed=0):
        """0x1061F0 after it stored the new period index: edi/ebx the two scores, its four pushes and return on the stack."""
        m.u32(so.SIM_STATE, 2)
        m.u32(so.SIM_PERIOD_INDEX, period)
        m.u32(0x00A971D4, tie_allowed)
        m.reg("EAX", period)
        m.reg("EDI", home)
        m.reg("EBX", away)
        m.reg("ESI", 0x00A96000)              # the tail's [esi] flags word (mapped scratch)
        frame = STACK - 0x40
        for i, value in enumerate((0x11, 0x22, 0x33, 0x44)):   # pushed edi, esi, ebx, ecx
            m.u32(frame + 4 * i, value)
        m.u32(frame + 0x10, caller)           # 0x1061F0's return address
        m.reg("ESP", frame)
        stops = [0x00106422, 0x0010644F, so.REG_OVERTIME, so.REG_GAME_OVER + 10]
        return m.run(PERIOD_TAIL, stops)

    def step(self, m, home, away):
        m.f(0xA97300, home)
        m.f(0xA97304, away)
        m.reg("ESP", STACK - 8)
        m.u32(STACK - 8, 0x0010B256)
        return m.run(PAGE_VA + so.labels()["step"], [so.FN_DISPATCH])

    def test_mid_play_end_is_tentative_and_keeps_the_fourth_quarter(self):
        m = self.machine()
        landed = self.advance(m, period=4, caller=so.COMMIT_CLOCK_RETURN, home=20, away=23)
        self.assertEqual(landed, so.REG_GAME_OVER + 10)              # retail's game over ran, then its tail
        self.assertEqual(m.get_u32(so.SIM_STATE), 0x12)
        self.assertEqual(m.get_u32(so.SIM_PERIOD_INDEX), 3)
        self.assertEqual(bytes(m.uc.mem_read(self.PENDING, 1)), b"\x01")

    def test_pre_play_end_keeps_retail(self):
        m = self.machine()
        self.assertEqual(self.advance(m, period=4, caller=0x0010798B, home=20, away=23), so.REG_GAME_OVER + 10)
        self.assertEqual((m.get_u32(so.SIM_STATE), m.get_u32(so.SIM_PERIOD_INDEX)), (0x12, 4))
        self.assertEqual(bytes(m.uc.mem_read(self.PENDING, 1)), b"\x00")
        m = self.machine()
        self.assertEqual(self.advance(m, period=4, caller=0x0010798B, home=17, away=17), so.REG_OVERTIME)

    def test_an_expired_overtime_reaches_retails_game_over(self):
        """The round-1 emulation error: an overtime that expires level with ties allowed (or not level) jumps to
        0x106427 from 0x106410 (0x106407). With the site at 0x106400 that is still retail's mov [state], 0x12."""
        for home, away, allowed in ((17, 17, 1), (24, 17, 0)):
            with self.subTest(home=home, away=away, tie_allowed=allowed):
                m = self.machine()
                landed = self.advance(m, period=5, caller=so.COMMIT_CLOCK_RETURN, home=home, away=away,
                                      tie_allowed=allowed)
                self.assertEqual(landed, so.REG_GAME_OVER + 10)
                self.assertEqual((m.get_u32(so.SIM_STATE), m.get_u32(so.SIM_PERIOD_INDEX)), (0x12, 5))
                self.assertEqual(bytes(m.uc.mem_read(self.PENDING, 1)), b"\x00")
        m = self.machine()        # level, no tie: another overtime period (period back to 4), the routine returns 0
        self.assertEqual(self.advance(m, period=5, caller=0x0010798B, home=17, away=17), 0x00106422)
        self.assertEqual(m.get_u32(so.SIM_PERIOD_INDEX), 4)

    def test_the_first_sites_layout_broke_the_expired_overtime(self):
        """Failing first: the first version replaced 0x106423..0x106430 (a call and nine nops); the expired-overtime jump
        to 0x106427 then lands inside the call's displacement."""
        from unicorn import UcError
        first = bytearray(PERIOD_TAIL_RETAIL[:5])                    # cmp eax,4 ; jle kept
        m = self.machine(site=bytes(first))
        old = b"\xe8" + struct.pack("<i", PAGE_VA + so.labels()["regulation"] - (0x106423 + 5)) + b"\x90" * 9
        m.put(0x106423, old)
        try:
            landed = self.advance(m, period=5, caller=0x0010798B, home=17, away=17, tie_allowed=1)
        except UcError:
            landed = None
        self.assertNotEqual(landed, so.REG_GAME_OVER + 10)
        self.assertNotEqual(m.get_u32(so.SIM_STATE), 0x12)

    def test_the_site_replaces_only_the_period_test(self):
        label, va, retail, after = next(r for r in so.sites(PAGE_VA) if r[0] == "regulation_end")
        self.assertEqual((va, retail, len(after)), (0x106400, PERIOD_TAIL_RETAIL[:5], 5))
        self.assertFalse(va <= so.REG_GAME_OVER < va + len(after))

    def test_the_tail_is_retail(self):
        path = Path(os.environ.get("NFL2K5_RETAIL_XBE") or "/nonexistent")
        if not path.is_file():
            self.skipTest("the private retail default.xbe is absent")
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        self.assertEqual(XbeImage(path.read_bytes()).read(PERIOD_TAIL, len(PERIOD_TAIL_RETAIL)), PERIOD_TAIL_RETAIL)

    def test_next_handler_decides_on_the_scores_after_the_play(self):
        m = self.machine()
        self.advance(m, period=4, caller=so.COMMIT_CLOCK_RETURN, home=20, away=23)
        m.u32(so.SIM_STATE, 0xB)                              # the handler went on (an interception return)
        self.assertEqual(self.step(m, 20.0, 23.0), so.FN_DISPATCH)
        self.assertEqual(m.get_u32(so.SIM_STATE), 0x12, "the game is over")
        self.assertEqual(m.get_u32(so.SIM_PERIOD_INDEX), 3, "a regulation result")
        m = self.machine()
        self.advance(m, period=4, caller=so.COMMIT_CLOCK_RETURN, home=20, away=23)
        m.u32(so.SIM_STATE, 7)                                # the play's last kick tied the game
        self.step(m, 23.0, 23.0)
        self.assertEqual((m.get_u32(so.SIM_STATE), m.get_u32(so.SIM_PERIOD_INDEX)), (1, 4), "overtime kickoff")
        self.assertEqual(bytes(m.uc.mem_read(self.PENDING, 1)), b"\x00")

    def test_step_without_a_pending_end_changes_nothing(self):
        m = self.machine()
        m.u32(so.SIM_STATE, 5)
        m.u32(so.SIM_PERIOD_INDEX, 2)
        self.step(m, 3.0, 10.0)
        self.assertEqual((m.get_u32(so.SIM_STATE), m.get_u32(so.SIM_PERIOD_INDEX)), (5, 2))

    def test_new_game_clears_the_flag(self):
        m = self.machine()
        self.advance(m, period=4, caller=so.COMMIT_CLOCK_RETURN, home=20, away=23)
        frame = STACK - 0x100
        m.reg("EBP", frame)
        m.u32(frame + 0x10, 0)
        m.u32(so.MODE, 2)
        m.u32(so.STAGE, 9)
        m.reg("ESP", STACK - 0x200)
        m.run(PAGE_VA + so.labels()["ties"], [TIES_ROLL, TIES_SKIP])
        self.assertEqual(bytes(m.uc.mem_read(self.PENDING, 1)), b"\x00")

    def test_retail_game_over_is_overwritten(self):
        """Failing first: retail ends regulation on the pre-play scores and a later handler write survives."""
        m = self.machine(site=PERIOD_TAIL_RETAIL[:5])
        self.assertEqual(self.advance(m, period=4, caller=so.COMMIT_CLOCK_RETURN, home=20, away=23), so.REG_GAME_OVER + 10)
        self.assertEqual(m.get_u32(so.SIM_STATE), 0x12)
        m.u32(so.SIM_STATE, 0xB)                              # 0x108AC0's interception write
        self.assertEqual(m.get_u32(so.SIM_STATE), 0xB, "retail: the game goes on into a phantom overtime")


def _built_xbe():
    for name in ("NFL2K5_B81_SIM_OUTCOMES_XBE", "B81_HISTORY_POOL_FULL_XBE"):
        value = os.environ.get(name)
        if value and Path(value).is_file():
            return Path(value)
    return None


BUILT = _built_xbe()
RETAIL = Path(os.environ.get("NFL2K5_RETAIL_XBE", "")) if os.environ.get("NFL2K5_RETAIL_XBE") else None


class PageShape(unittest.TestCase):
    def test_page_and_sites(self):
        page = so.code_for(PAGE_VA)
        self.assertEqual(len(page), so.CODE_SIZE)
        self.assertEqual(page[so.DATA_OFF:so.DATA_OFF + 8], so.MARK)
        self.assertEqual(page[so.DATA_OFF + so.D_THRESHOLDS:so.DATA_OFF + so.D_THRESHOLDS + 33],
                         so.two_point_thresholds())
        for label, va, retail, after in so.sites(PAGE_VA):
            self.assertEqual(len(retail), len(after), label)

    def test_allocator_places_the_fixed_page(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        self.assertEqual(space.SIM_OUTCOMES_VA, so.PLACEHOLDER_VA)
        rows = space._scale_allocations(list(space._requests([space.SIM_OUTCOMES_REQUEST])))
        self.assertEqual([r["va"] for r in rows if r["owner"] == so.OWNER], [space.SIM_OUTCOMES_VA])
        # any other pool owner steps over the page
        self.assertEqual(space._sim_outcomes_at("other", space.SIM_OUTCOMES_VA - space.POOL_VA - 16, 64, 16),
                         space.SIM_OUTCOMES_VA - space.POOL_VA + space.SIM_OUTCOMES_SIZE)

    @unittest.skipUnless(RETAIL and RETAIL.is_file(), "the retail default.xbe is not available")
    def test_sites_are_retail_bytes(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(RETAIL.read_bytes())
        for label, va, retail, _after in so.sites(PAGE_VA):
            self.assertEqual(image.read(va, len(retail)), retail, label)
        self.assertEqual(image.read(so.TRY_SITE, len(RETAIL_TRY)), RETAIL_TRY)
        self.assertEqual(so.status(RETAIL.read_bytes()), "retail")


@unittest.skipUnless(BUILT, "no built beta 81 standard default.xbe in the environment")
class BuiltExecutable(unittest.TestCase):
    def setUp(self):
        self.base = BUILT.read_bytes()

    def test_install_moves_nothing_and_keeps_the_other_simulator_owners(self):
        from mod_editor.core import nfl2k5_overtime as overtime
        from mod_editor.core import nfl2k5_sim_qb_injuries as qb
        from mod_editor.core import nfl2k5_sim_realism as realism
        from mod_editor.core import nfl2k5_sim_scoring as scoring
        from mod_editor.core import nfl2k5_xbe_space as space
        self.assertEqual(so.status(self.base), "retail")
        new, receipt = so.apply(self.base)
        self.assertEqual(so.status(new), "applied")
        self.assertEqual(receipt["page_va"], hex(space.SIM_OUTCOMES_VA))
        before = space.layout(self.base)["allocations"]
        self.assertTrue(all(row in space.layout(new)["allocations"] for row in before), "an allocation moved")
        for module in (overtime, realism, scoring):
            self.assertEqual(module.status(new), module.status(self.base), module.__name__)
        self.assertEqual(qb.read_settings(new), qb.read_settings(self.base))
        self.assertEqual(so.apply(new)[1]["already_applied"], True)
        settings = so.read_settings(new)
        self.assertEqual((settings["home_edge"], settings["form_sigma"]), (so.HOME_EDGE, so.FORM_SIGMA))

    def test_levers_reset_in_place_and_retail_restores_the_sites(self):
        new, _ = so.apply(self.base)
        other, receipt = so.apply(new, home_edge=0.03, form_sigma=0.1)
        self.assertEqual(so.read_settings(other)["home_edge"], 0.03)
        self.assertEqual(len(other), len(new))
        back, _ = so.remove(other)
        self.assertEqual(so.status(back), "retail")
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(back)
        for label, va, retail, _after in so.sites(so.PLACEHOLDER_VA):
            self.assertEqual(image.read(va, len(retail)), retail, label)
        again, _ = so.apply(back)
        self.assertEqual(again, new, "re-applying after Retail gives the same executable")

    def test_foreign_page_is_refused(self):
        new, _ = so.apply(self.base)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        buf = bytearray(new)
        off = XbeImage(new).offset(so.PLACEHOLDER_VA + 0x10, 1)
        buf[off] ^= 0xFF
        self.assertEqual(so.status(bytes(buf)), "foreign")


if __name__ == "__main__":
    unittest.main()
