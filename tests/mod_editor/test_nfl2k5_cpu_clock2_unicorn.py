"""b780 b-clock: the game's own clock routines replayed (Unicorn) before and after nfl2k5_cpu_clock2.

Bounded instruction replays of the real USA routines with supplied game state; no game boot. Supplied: the kicker's
field-goal range (50 yards, as in test_b778_ai4_cpu_clock), the team, score, clock and down records, the selector
PLAY slots (Take Knee, Spike Ball, field goal and punt PLAYs with their retail header bits). Everything else, the
time-needed estimate, urgency, hurry, onside, snap delay, timeout poll, kneel, late window and the owner's code, runs
natively. What the replays prove is listed per test; game play itself is the job report's emulator gates.
"""
from pathlib import Path
import itertools
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_cpu_clock2 as clock2  # noqa: E402
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe  # noqa: E402

try:
    from tests.nfl2k5_cpu_money_downs_native import Machine, x86
except ImportError:      # pragma: no cover - Unicorn missing
    Machine = None

STUB, SCRATCH = 0x3200100, 0x3100800
TIMEOUT_FLAGGED = 0x188722          # 0x1885F0's request tail: the CPU will call a timeout
SEL, PLAYS = 0x3017000, 0x3018000
NORMAL, KNEEL, SPIKE, FG, PUNT = (PLAYS + i * 0x100 for i in range(5))
HEADERS = {NORMAL: 0x08000400, KNEEL: 0x08408400, SPIKE: 0x08402400, FG: 0x0804850C, PUNT: 0x0802848A}
OBJ = 0x3016000


def _bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


class Replay:
    """Small wrappers around the money-downs fixture (offense = home team object)."""

    def __init__(self, payload):
        self.m = Machine(payload)
        self.m.supply_fg_range(50)

    def st0(self):
        m = self.m
        m.uc.mem_write(STUB, b"\xd9\x1d" + struct.pack("<I", SCRATCH) + b"\xc3")
        m.run(STUB, count=10)
        return m.readf(SCRATCH)

    def estimate(self, team, state):
        m = self.m
        m.configure(**state)
        m.run(0x20A4D0, args=(team,), count=20000)
        return self.st0()

    def prepare(self, state, *, warned=True, mode=7):
        m = self.m
        m.u32(0xE5FF80, mode)
        m.u32(0xE60284, m.DEF)
        offense, defense = self.estimate(m.HOME, state), self.estimate(m.DEF, state)
        m.configure(**state)
        m.f32(0xBF1240, offense)
        m.f32(0xBF1480, defense)
        m.f32(0xE602AC, 40)
        m.u32(0xE602FC, 0x20 if warned else 0)
        m.u32(0xE5FF80, mode)
        for team, sel in ((m.HOME, m.HOME + 0x100), (m.DEF, m.DEF + 0x300)):
            m.u32(team + 0xC, sel)
            m.u32(sel + 0x24, 0)
        m.u32(m.DEF + 0x30, 0)
        m.u32(m.DEF + 8, m.DEF + 0x200)
        m.u32(m.OFFMETA + 0x14, 1)
        m.u32(m.DEF + 0x200 + 0x14, 1)
        m.u32(0xE5FC28, m.OFFMETA)                # the real home / away score records for the overtime window
        m.u32(0xE5FC68, m.DEF + 0x200)
        return offense, defense

    def flag(self, va, **registers):
        self.m.run(va, count=50000, **registers)
        return self.m.uc.reg_read(x86.UC_X86_REG_EAX) & 0xFF

    def urgency(self, team, seconds, estimate):
        self.m.run(0x2079B0, ecx=team, args=(_bits(seconds), _bits(estimate)), count=20000)
        return self.st0()

    def timeout(self, team):
        return self.m.run(0x1885F0, ecx=team, stop_at=TIMEOUT_FLAGGED, count=200000) == TIMEOUT_FLAGGED

    def books(self, current):
        m = self.m
        m.u32(m.HOME + 0xC, SEL)
        for play, header in HEADERS.items():
            m.u32(play + 4, header)
        for offset, play in ((0xC, current), (0x30, KNEEL), (0x2C, SPIKE), (0x3C, FG), (0x40, PUNT)):
            m.u32(SEL + offset, play)
        m.u32(SEL + 0x24, 0)

    def snap_delay(self, *, quarter, seconds, margin, play=NORMAL, urgency=0.0, play_clock=30.0):
        m = self.m
        m.configure(down=1, quarter=quarter, seconds=seconds, score_margin=margin, own_yard=40, distance=10, home=True,
                    quarter_seconds=900)
        self.books(play)
        m.f32(SEL + 0xC4, urgency)
        m.u32(OBJ + 0x38, m.HOME)
        m.u32(OBJ + 0xC, OBJ + 0x80)
        m.u32(OBJ + 0x80, 0xFFFFFFFF)            # CPU controller
        m.f32(m.GAME + 0x600 + 0x10, play_clock)
        m.u32(m.GAME + 0x500 + 0x18, 0)          # game clock running
        m.seed(3)
        m.run(0x2D3360, ecx=OBJ, edx=0, count=50000)
        return self.st0()

    def kneel(self, *, quarter, seconds, own_yard, margin, down, defense_timeouts, play_clock=40.0):
        self.prepare(dict(down=down, quarter=quarter, seconds=seconds, score_margin=margin, own_yard=own_yard,
                          distance=10, home=True, quarter_seconds=900, timeouts=defense_timeouts))
        self.m.f32(self.m.GAME + 0x600 + 0x10, play_clock)
        self.m.u32(self.m.GAME + 0x500 + 0x18, 0)
        return self.flag(0x206F10)

    def runoff(self, *, quarter, seconds, down, defense_timeouts, play=KNEEL, state=18, running=True, warned=True):
        m = self.m
        m.configure(down=down, quarter=quarter, seconds=seconds, score_margin=7, own_yard=40, distance=10, home=True,
                    quarter_seconds=900, timeouts=defense_timeouts)
        self.books(play)
        m.u32(0xE602FC, 0x20 if warned else 0)    # two-minute warning given
        m.u32(0xA83A18, 3)
        m.u32(0xE602B8, state)
        m.f32(0xE602AC, 40)
        m.u32(m.GAME + 0x500 + 0x18, 0 if running else 2)
        m.u32(m.GAME + 0x500, 0)
        m.run(0x189080, stop_at=0x189086, count=5000)
        return m.readf(m.GAME + 0x510), m.get(m.GAME + 0x518) & 6


@unittest.skipUnless(Machine is not None, "Unicorn is required for bounded instruction replay")
class ClockReplays(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = retail_xbe()
        cls.retail = Replay(retail)
        cls.clock = Replay(clock2.apply(retail)[0])
        cls.overtime = Replay(clock2.apply(retail, overtime=True)[0])

    def both(self, fn, *args, **kwargs):
        return fn(self.retail, *args, **kwargs), fn(self.clock, *args, **kwargs)

    def test_two_scores_down_gets_the_estimate_and_urgency_from_ten_minutes(self):
        """Q4, own 25, 7-minute quarters: retail E is 0 until 5:00; a team down 9 or more now gets the native E from
        10:00 (two scores: 75 yards x 1.875 s + 140.625 s), urgency rises before 5:00, one-score games are unchanged."""
        def offense_estimate(r, seconds, margin):
            return r.prepare(dict(down=1, quarter=4, seconds=seconds, score_margin=margin, own_yard=25, distance=10,
                                  home=True, quarter_seconds=420))[0]
        for margin in (-9, -14, -16):
            for seconds in (600, 420, 330):
                self.assertEqual(self.both(offense_estimate, seconds, margin), (0.0, 281.25), (margin, seconds))
            self.assertEqual(self.both(offense_estimate, 660, margin), (0.0, 0.0), margin)
            self.assertEqual(self.both(offense_estimate, 270, margin), (281.25, 281.25), margin)
        for margin in (-8, -3, 0, 7):
            for seconds in (600, 420, 330):
                self.assertEqual(self.both(offense_estimate, seconds, margin), (0.0, 0.0), (margin, seconds))
        u = {}
        for seconds in (420, 390, 330):
            self.clock.prepare(dict(down=1, quarter=4, seconds=seconds, score_margin=-14, own_yard=25, distance=10,
                                    home=True, quarter_seconds=420))
            u[seconds] = self.clock.urgency(self.clock.m.HOME, seconds, 281.25)
        self.assertAlmostEqual(u[390], 1.5 - 390 / 281.25, places=4)
        self.assertAlmostEqual(u[330], 1.5 - 330 / 281.25, places=4)
        self.assertGreater(u[330], u[390])
        self.retail.prepare(dict(down=1, quarter=4, seconds=330, score_margin=-14, own_yard=25, distance=10, home=True,
                                 quarter_seconds=420))
        self.assertEqual(self.retail.urgency(self.retail.m.HOME, 330, 281.25), 0.0)     # retail: not late yet

    def test_hurry_starts_earlier_and_onside_kicks_do_not(self):
        def hurry(r, seconds, margin):
            r.prepare(dict(down=1, quarter=4, seconds=seconds, score_margin=margin, own_yard=25, distance=10,
                           home=True, quarter_seconds=420))
            return r.flag(0x2077C0, ecx=r.m.HOME)

        def onside(r, seconds, margin):
            r.prepare(dict(down=1, quarter=4, seconds=seconds, score_margin=margin, own_yard=35, distance=10,
                           home=True, quarter_seconds=420))
            return r.flag(0x206EB0)
        self.assertEqual(self.both(hurry, 420, -14), (0, 1))
        self.assertEqual(self.both(hurry, 400, -14), (0, 1))
        self.assertEqual(self.both(hurry, 420, -8), (0, 0))
        self.assertEqual(self.both(hurry, 240, -14), (1, 1))
        for seconds, margin in ((360, -14), (330, -14), (500, -17)):
            self.assertEqual(self.both(onside, seconds, margin), (0, 0), (seconds, margin))
        self.assertEqual(self.both(onside, 280, -14), (1, 1))

    def test_trailing_cpu_defense_calls_timeouts_before_the_two_minute_warning(self):
        """Home offense leads, away CPU defense trails, clock running, two-minute warning not yet given."""
        def timeouts(r, seconds, offense_margin, quarter=4):
            r.prepare(dict(down=1, quarter=quarter, seconds=seconds, score_margin=offense_margin, own_yard=40,
                           distance=10, home=True, quarter_seconds=420, timeouts=3), warned=False)
            defense = r.timeout(r.m.DEF)
            r.prepare(dict(down=1, quarter=quarter, seconds=seconds, score_margin=offense_margin, own_yard=40,
                           distance=10, home=True, quarter_seconds=420, timeouts=3), warned=False)
            return defense, r.timeout(r.m.HOME)
        expected = {(150, 7): (True, False), (170, 3): (True, False), (210, 7): (False, False),   # down 1-8: from 2:55
                    (210, 12): (True, False), (270, 12): (True, False), (330, 12): (False, False),  # down 9+: from 5:00
                    (210, -7): (False, False)}                                                    # defense leads
        for (seconds, margin), result in expected.items():
            self.assertEqual(timeouts(self.retail, seconds, margin), (False, False), (seconds, margin))
            self.assertEqual(timeouts(self.clock, seconds, margin), result, (seconds, margin))
        self.assertEqual(self.both(timeouts, 150, 7, 2), ((False, False), (False, False)))      # first half: retail

    def test_four_minute_offense_runs_the_play_clock_down(self):
        """Seconds the CPU waits before the snap (play clock 30): retail runs it down only for a kneel, the field-goal
        run-down or a field goal / punt PLAY in the last 2:00; a leading offense now does it on every PLAY from 5:00."""
        delay = {}
        for key in (("lead_normal_240", 4, 240, 7, NORMAL, -.5), ("lead_punt_240", 4, 240, 7, PUNT, -.5),
                    ("lead_normal_100", 4, 100, 7, NORMAL, -.5), ("lead_punt_100", 4, 100, 7, PUNT, -.5),
                    ("trail_normal_240", 4, 240, -7, NORMAL, .5), ("lead_normal_360", 4, 360, 7, NORMAL, -.2),
                    ("tied_normal_240", 4, 240, 0, NORMAL, 0.), ("q2_lead_normal_100", 2, 100, 7, NORMAL, 0.),
                    ("lead_kneel_200", 4, 200, 3, KNEEL, -1.)):
            name, quarter, seconds, margin, play, u = key
            delay[name] = self.both(Replay.snap_delay, quarter=quarter, seconds=seconds, margin=margin, play=play,
                                    urgency=u)
        run_down = delay["lead_kneel_200"][0]
        self.assertTrue(28.0 < run_down < 29.3, run_down)          # 30 - 0.8 - 1.4 x rand: snap near 0 on the play clock
        for name in ("lead_normal_240", "lead_punt_240", "lead_normal_100"):
            self.assertLess(delay[name][0], 10.0, name)
            self.assertEqual(delay[name][1], run_down, name)
        self.assertEqual(delay["lead_punt_100"], (run_down, run_down))
        for name in ("trail_normal_240", "lead_normal_360", "tied_normal_240", "q2_lead_normal_100", "lead_kneel_200"):
            self.assertEqual(delay[name][0], delay[name][1], name)

    def test_end_of_half_kneel(self):
        """Q2, own side, 60 s or less, the native kneel formula: (4 - defense timeouts - down) x 40 + 40 + 15 > t."""
        cases = {(40, 30, 7, 2, 2): (0, 1), (40, 30, 0, 1, 3): (0, 1), (40, 30, -3, 1, 3): (0, 1),
                 (55, 25, 7, 1, 3): (0, 0), (70, 30, 7, 1, 0): (0, 0), (40, 60, 7, 2, 2): (0, 0),
                 (40, 5, 7, 2, 2): (0, 0), (20, 45, -7, 3, 3): (0, 0), (110, 30, 7, 1, 0): (0, 0)}
        for (seconds, own, margin, down, tos), result in cases.items():
            self.assertEqual(self.both(Replay.kneel, quarter=2, seconds=seconds, own_yard=own, margin=margin, down=down,
                                       defense_timeouts=tos), result, (seconds, own, margin, down, tos))
        self.assertEqual(self.both(Replay.kneel, quarter=4, seconds=100, own_yard=30, margin=7, down=1,
                                   defense_timeouts=0), (1, 1))                       # Q4 stays native

    def test_kneel_runoff(self):
        """After a Take Knee PLAY: the clock goes to 0:00 and stops only when the downs left can kneel it all out."""
        runs_out = ((4, 75, 1, 1), (4, 115, 1, 0), (2, 30, 2, 1), (4, 30, 3, 0))
        keeps = ((4, 75, 1, 2), (4, 125, 1, 0), (4, 30, 4, 0))
        for quarter, seconds, down, tos in runs_out:
            self.assertEqual(self.retail.runoff(quarter=quarter, seconds=seconds, down=down, defense_timeouts=tos),
                             (float(seconds), 0))
            self.assertEqual(self.clock.runoff(quarter=quarter, seconds=seconds, down=down, defense_timeouts=tos),
                             (0.0, 2), (quarter, seconds, down, tos))
        for quarter, seconds, down, tos in keeps:
            self.assertEqual(self.clock.runoff(quarter=quarter, seconds=seconds, down=down, defense_timeouts=tos),
                             (float(seconds), 0), (quarter, seconds, down, tos))
        for kwargs in (dict(play=SPIKE), dict(play=NORMAL), dict(running=False), dict(state=14)):
            result = self.clock.runoff(quarter=4, seconds=30, down=1, defense_timeouts=0, **kwargs)
            self.assertEqual(result[0], 30.0, kwargs)
        self.assertEqual(self.clock.runoff(quarter=3, seconds=30, down=1, defense_timeouts=0), (30.0, 0))
        # a two-minute warning still to come stops the clock once more: no runoff before it
        self.assertEqual(self.clock.runoff(quarter=4, seconds=115, down=1, defense_timeouts=0, warned=False), (115.0, 0))

    def test_native_spike_rule_is_kept(self):
        """The retail spike predicate 0x207310 (used by 0x189D10 to run the book's Spike Ball) is unchanged."""
        def spike(r, seconds, own, margin, down, tos):
            r.prepare(dict(down=down, quarter=4, seconds=seconds, score_margin=margin, own_yard=own, distance=10,
                           home=True, quarter_seconds=900))
            r.m.u32(r.m.OFFMETA + 4, tos)
            return r.flag(0x207310)
        cases = {(35, 50, -4, 1, 0): 1, (35, 70, -4, 1, 0): 0, (12, 70, -4, 2, 0): 1, (12, 70, -4, 3, 0): 1,
                 (25, 60, -4, 2, 0): 0, (35, 50, -4, 1, 1): 0, (12, 80, -1, 2, 0): 1, (50, 40, -7, 1, 0): 1,
                 (12, 70, -4, 4, 0): 0}
        for state, result in cases.items():
            self.assertEqual(self.both(spike, *state), (result, result), state)

    def test_overtime_window(self):
        """0x205FE0 itself: overtime counts as late only with the overtime choice, in franchise regular season
        (mode 7, period 5) or while the scores differ outside the playoffs; Q1-Q4 are unchanged."""
        def window(r, quarter, seconds, mode, margin):
            r.prepare(dict(down=1, quarter=quarter, seconds=seconds, score_margin=margin, own_yard=40, distance=10,
                           home=True, quarter_seconds=600), mode=mode)
            return r.flag(0x205FE0)
        cases = {(4, 200, 7, 0): (1, 1), (4, 400, 7, 0): (0, 0), (5, 200, 7, 0): (0, 1), (5, 400, 7, 0): (0, 0),
                 (5, 200, 6, 0): (0, 0), (5, 200, 5, -3): (0, 0), (5, 200, 4, 0): (0, 0), (5, 200, 4, -3): (0, 1),
                 (6, 200, 4, 3): (0, 1), (6, 200, 7, 0): (0, 0), (2, 100, 7, 0): (0, 0), (3, 100, 7, 0): (0, 0)}
        for state, (retail, overtime) in cases.items():
            self.assertEqual(window(self.retail, *state), retail, state)
            self.assertEqual(window(self.clock, *state), retail, state)          # main owner: overtime untouched
            self.assertEqual(window(self.overtime, *state), overtime, state)

    def test_overtime_census_of_the_late_window_callers(self):
        """The decision routines that ask 0x205FE0, replayed on overtime states. Without the overtime choice nothing
        changes; with it, playoffs and tied non-franchise games stay native, and franchise regular season gets the
        end-of-game rules (examples pinned below)."""
        def row(r, state, mode):
            out = {}
            offense, defense = r.prepare(state, mode=mode)
            out["estimate"] = (round(offense, 2), round(defense, 2))
            for name, va in (("hail", 0x206DD0), ("kneel", 0x206F10), ("spike", 0x207310), ("punt", 0x209CA0),
                             ("fg", 0x20AF80)):
                r.prepare(state, mode=mode)
                out[name] = r.flag(va)
            r.prepare(state, mode=mode)
            out["hurry"] = r.flag(0x2077C0, ecx=r.m.HOME)
            r.prepare(state, mode=mode)
            out["offense_timeout"] = r.timeout(r.m.HOME)
            r.prepare(state, mode=mode)
            out["defense_timeout"] = r.timeout(r.m.DEF)
            return out
        changed = []
        for mode, seconds, margin, own, down in itertools.product((7, 6, 4), (250, 100, 30, 10), (0, -3, 3, -7),
                                                                   (30, 65), (1, 4)):
            state = dict(down=down, quarter=5, seconds=seconds, score_margin=margin, own_yard=own, distance=4,
                         home=True, quarter_seconds=600, timeouts=2)
            retail, clock, overtime = (row(r, state, mode) for r in (self.retail, self.clock, self.overtime))
            self.assertEqual(clock, retail, (mode, state))
            if mode == 6 or (mode == 4 and margin == 0):
                self.assertEqual(overtime, retail, (mode, state))
            if overtime != retail:
                changed.append((mode, seconds, margin, own, down, retail, overtime))
        self.assertTrue(changed)
        self.assertEqual({c[0] for c in changed}, {4, 7})
        by_state = {c[:5]: (c[5], c[6]) for c in changed}
        # trailing by 3 on fourth down at 1:40 of franchise overtime: retail punts, the overtime rules go for it
        retail, overtime = by_state[(7, 100, -3, 30, 4)]
        self.assertEqual((retail["punt"], overtime["punt"]), (1, 0))
        # trailing by 7 on fourth down in field-goal range: retail kicks, the overtime rules do not
        retail, overtime = by_state[(7, 100, -7, 65, 4)]
        self.assertEqual((retail["fg"], overtime["fg"]), (1, 0))
        # tied with 1:40 left: the offense hurries and the defense wants its timeouts, as in Q4
        retail, overtime = by_state[(7, 100, 0, 30, 1)]
        self.assertEqual((retail["hurry"], overtime["hurry"]), (0, 1))
        self.assertEqual((retail["defense_timeout"], overtime["defense_timeout"]), (False, True))


if __name__ == "__main__":
    unittest.main()
