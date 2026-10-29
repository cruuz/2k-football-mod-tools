"""Pass rush stats owner (b779 st1): static shape, coexistence, and every hook run natively in Unicorn.

The patched retail image runs from each real patch site to its retail continuation. Synthetic RAM stands in for
a game: on-field actors (+0x18 transform, +0x34 next, +0x38 team, +0x3C live record, +0x48 inactive), the live
0x54 records in the game's own side arrays (0xB30C4C / 0xB321A0) so the native 0xBBAA0 computes the play-log
codes, and the honors harness's roster object and history pool so the native history readers and writers run.
Substituted leaves are named where used: 0xA7CD0 (the play's role lookup, for the first sack path) and 0x6E390
(the screen push, recorded instead of building a UI screen). Everything else is the game's code.
"""
from __future__ import annotations

import importlib.util
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_pass_rush_stats as prs  # noqa: E402
from mod_editor.core import nfl2k5_pass_rush_stats_code as runtime  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import XbeImage  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
OFFENSE_TEAM, DEFENSE_TEAM = 0x00E5FC20, 0x00E5FC60
SIDE0, SIDE1, REC = 0x00B30C4C, 0x00B321A0, 0x54
YD = 914.4


def retail():
    from tests.mod_editor.test_nfl2k5_sim_cb_tackles import retail as load
    return load()


_PATCHED = {}


def patched():
    if "p" not in _PATCHED:
        data = retail()
        _PATCHED["p"] = prs.apply(data)[0] if data else None
    return _PATCHED["p"]


class StaticTests(unittest.TestCase):
    def test_runtime_fits_and_tables_fit(self):
        self.assertLessEqual(len(runtime.CODE), prs.CODE_SIZE)
        self.assertLessEqual(prs.STATE_SIZE, prs.DATA_SIZE)
        lay = prs.read_only_layout(0x1000000)
        self.assertLessEqual(lay["end"] - 0x1000000, prs.READ_ONLY_SIZE)
        self.assertEqual(prs.FIELDS, {"pressures": 106, "qb_hits": 107, "pressures_allowed": 108,
                                      "qb_hits_allowed": 109, "sacks_allowed": 110})
        self.assertTrue(all(f > 105 for f in prs.FIELDS.values()), "honors owns 96-105")

    def test_site_patches_are_whole_instructions_to_the_runtime(self):
        at = prs.labels(0x1400000)
        for label, va, before, after in prs.sites(0x1400000):
            self.assertEqual(len(before), len(after))
            self.assertIn(after[0], (0xE8, 0xE9))
            target = va + 5 + struct.unpack_from("<i", after, 1)[0]
            self.assertIn(target, at.values(), label)
            self.assertEqual(after[5:], b"\x90" * (len(after) - 5))

    def test_tunables_are_written(self):
        code = prs.code_for(0x1400000, 0x1500000, 0x1600000)
        for label, value in prs.TUNING:
            self.assertAlmostEqual(struct.unpack_from("<f", code, runtime.LABELS[label])[0], value, delta=abs(value) * 1e-6)


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.retail = retail()
        if self.retail is None:
            self.skipTest("pinned USA retail XBE is not available")

    def test_retail_apply_idempotent_and_refuses_a_foreign_site(self):
        self.assertEqual(prs.status(self.retail), "retail")
        out = patched()
        self.assertEqual(prs.status(out), "applied")
        again, receipt = prs.apply(out)
        self.assertEqual((again, receipt["status"]), (out, "already_applied"))
        image = XbeImage(out)
        buf = bytearray(out)
        off = image.offset(0x2DB2CA, 1)
        buf[off] = 0x90
        self.assertEqual(prs.status(bytes(buf)), "foreign")
        with self.assertRaises(prs.PassRushStatsError):
            prs.apply(bytes(buf))

    def test_changed_dependency_is_refused(self):
        image = XbeImage(self.retail)
        buf = bytearray(self.retail)
        buf[image.offset(0x234730, 1)] ^= 0xFF          # inside the shed caller
        self.assertEqual(prs.status(bytes(buf)), "foreign")

    def test_coexists_with_team_column_pass_protection_and_qb_accuracy(self):
        from mod_editor.core import nfl2k5_team_column as tc, nfl2k5_pass_protection as pp, nfl2k5_qb_accuracy as qa
        data = tc.apply(self.retail)[0]
        data = qa.apply(data)[0]                          # late owners in LATE_OWNERS order
        data = pp.apply(data)[0]
        data = prs.apply(data)[0]
        self.assertEqual((tc.status(data), pp.status(data), qa.status(data), prs.status(data)),
                         ("applied", "applied", "applied", "applied"))
        lay = prs.allocations(data)
        ro = prs.read_only_layout(lay["read_only"]["va"])
        image = XbeImage(data)
        ol = struct.unpack_from("<6I", image.read(ro["list_ol"] + 0x9C, 24))
        self.assertEqual(ol, (prs.YR, prs.TEAM_DESCRIPTOR, prs.GAMES, ro["d_pa"], ro["d_ha"], ro["d_sa"]))


class Game:
    """The patched image in the honors Unicorn harness, with two teams, actors and live records."""

    def __init__(self, payload):
        from tests.mod_editor.test_nfl2k5_honors import Machine
        self.m = Machine(payload)
        rows = prs.allocations(payload)
        self.code, self.data, self.ro = rows["code"]["va"], rows["data"]["va"], rows["read_only"]["va"]
        self.at = prs.labels(self.code)
        self.m.put(0x00E60280, OFFENSE_TEAM)
        self.m.put(0x00E60284, DEFENSE_TEAM)
        self.m.put(0x00E53804, 7)
        self.m.uc.mem_write(0x00B30980, bytes([40]))     # side 0 live record count (0x61B90 wraps after it)
        self.actors = self.m.HEAP + 0x50000
        self.n_actors = 0
        # team objects as xemu shows them: +0 = the other team's object, +4 = the first on-field actor, +0x34 next
        self.m.put(DEFENSE_TEAM, OFFENSE_TEAM)
        self.m.put(OFFENSE_TEAM, DEFENSE_TEAM)
        self.m.put(DEFENSE_TEAM + 4, 0)
        self.m.put(OFFENSE_TEAM + 4, 0)
        self.last = {True: None, False: None}

    def live(self, side, slot):
        rec = (SIDE1 if side else SIDE0) + slot * REC
        self.m.put8(rec + 0x34, 2 if side else 1)
        return rec

    @staticmethod
    def pcode(side, slot):
        return 2 + 2 * slot + side

    def actor(self, side, slot, x, z, *, defense):
        a = self.actors + self.n_actors * 0x100
        self.n_actors += 1
        t = a + 0x80
        self.m.uc.mem_write(a, bytes(0x100))
        self.m.put(a + 0x18, t)
        self.m.uc.mem_write(t + 0x30, struct.pack("<f", x))
        self.m.uc.mem_write(t + 0x38, struct.pack("<f", z))
        self.m.put(a + 0x38, DEFENSE_TEAM if defense else OFFENSE_TEAM)
        self.m.put(a + 0x3C, self.live(side, slot))
        team = DEFENSE_TEAM if defense else OFFENSE_TEAM
        if self.last[defense] is None:
            self.m.put(team + 4, a)
        else:
            self.m.put(self.last[defense] + 0x34, a)
        self.last[defense] = a
        return a

    def counts(self, code):
        return list(self.m.uc.mem_read(self.data + prs.STATE_COUNTERS_OFF + 5 * code, 5))

    def diag(self, name):
        return self.m.get(self.data + 4 * prs.STATE_DIAGNOSTICS.index(name))

    def run(self, start, stop, regs, stack=(), budget=500_000):
        sp = self.m.SP - 0x400
        for i, v in enumerate(stack):
            self.m.put(sp + 4 * i, v)
        self.m.reg("ESP", sp)
        for name in ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP"):
            self.m.reg(name, regs.get(name, 0))
        self.m.uc.emu_start(start, stop, count=budget)
        if self.m.reg("EIP") != stop:
            raise AssertionError(f"did not reach {stop:#x}: {self.m.reg('EIP'):#x}")
        return sp


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class PlayedTests(unittest.TestCase):
    def setUp(self):
        data = patched()
        if data is None:
            self.skipTest("pinned USA retail XBE is not available")
        self.g = Game(data)

    def shed(self, blocker, rusher, swap=False):
        a, b = (rusher, blocker) if swap else (blocker, rusher)
        sp = self.g.run(0x23477A, 0x234781, {"EBX": a, "ESI": b})
        # the displaced pushes are on the stack: esi, 3, 0, 0 (push ebx follows at 0x234781)
        self.assertEqual([self.g.m.get(self.g.m.reg("ESP") + 4 * i) for i in range(4)], [b, 3, 0, 0])
        self.assertEqual(self.g.m.reg("ESP"), sp - 16)

    def test_shed_records_the_beaten_blocker_in_either_register_order(self):
        lt = self.g.actor(0, 30, 0, 0, defense=False)
        de = self.g.actor(1, 4, 0, 0, defense=True)
        self.shed(lt, de)
        self.assertEqual(self.g.diag("sheds"), 1)
        beaten = self.g.data + prs.STATE_COUNTERS_OFF + 5 * prs.NCODE
        self.assertEqual(self.g.m.uc.mem_read(beaten + self.g.pcode(1, 4), 1)[0], self.g.pcode(0, 30))
        lg = self.g.actor(0, 31, 0, 0, defense=False)
        dt = self.g.actor(1, 5, 0, 0, defense=True)
        self.shed(lg, dt, swap=True)
        self.assertEqual(self.g.m.uc.mem_read(beaten + self.g.pcode(1, 5), 1)[0], self.g.pcode(0, 31))

    def test_throw_credits_hurry_hit_and_the_beaten_blocker(self):
        qb = self.g.actor(0, 1, 1000.0, 2000.0, defense=False)
        lt = self.g.actor(0, 30, 0, 0, defense=False)
        de_hit = self.g.actor(1, 4, 1000.0 + 0.6 * YD, 2000.0, defense=True)       # 0.6 yd: hit
        de_hurry = self.g.actor(1, 5, 1000.0, 2000.0 + 1.6 * YD, defense=True)     # 1.6 yd: hurry
        self.g.actor(1, 6, 1000.0 + 5 * YD, 2000.0, defense=True)                  # 5 yd: nothing
        inactive = self.g.actor(1, 7, 1000.0, 2000.0, defense=True)
        self.g.m.put(inactive + 0x48, 1)                                           # skipped like the game's own scan
        self.shed(lt, de_hit)
        sp = self.g.run(0x2DB2CA, 0x2DAF10, {"ESI": qb}, stack=(0x12345,))
        self.assertEqual(self.g.m.get(self.g.m.reg("ESP")), 0x2DB2CF)              # the call's own return
        self.assertEqual(self.g.m.get(self.g.m.reg("ESP") + 4), 0x12345)
        self.assertEqual(self.g.m.reg("ESI"), qb)
        self.assertEqual(self.g.counts(self.g.pcode(1, 4)), [1, 1, 0, 0, 0])
        self.assertEqual(self.g.counts(self.g.pcode(1, 5)), [1, 0, 0, 0, 0])
        self.assertEqual(self.g.counts(self.g.pcode(1, 6)), [0, 0, 0, 0, 0])
        self.assertEqual(self.g.counts(self.g.pcode(1, 7)), [0, 0, 0, 0, 0])
        self.assertEqual(self.g.counts(self.g.pcode(0, 30)), [0, 0, 1, 1, 0])
        self.assertEqual(self.g.diag("last_defenders"), 3)
        self.assertAlmostEqual(self.g.diag("last_min_mm"), 0.6 * YD, delta=2)
        del sp

    def test_a_shed_from_an_earlier_play_is_not_charged(self):
        qb = self.g.actor(0, 1, 0, 0, defense=False)
        lt = self.g.actor(0, 30, 0, 0, defense=False)
        de = self.g.actor(1, 4, 0.5 * YD, 0, defense=True)
        self.shed(lt, de)
        self.g.m.put(0x00E53804, 8)                    # the next play
        self.g.run(0x2DB2CA, 0x2DAF10, {"ESI": qb}, stack=(0,))
        self.assertEqual(self.g.counts(self.g.pcode(1, 4)), [1, 1, 0, 0, 0])
        self.assertEqual(self.g.counts(self.g.pcode(0, 30)), [0, 0, 0, 0, 0])

    def test_both_sack_paths_credit_sacker_and_beaten_blocker(self):
        rt = self.g.actor(0, 31, 0, 0, defense=False)
        de = self.g.actor(1, 9, 0, 0, defense=True)
        self.shed(rt, de)
        entry = self.g.m.HEAP + 0x4E000
        self.g.m.put(entry + 0x24, self.g.live(1, 9))
        self.g.m.hook(0xA7CD0, lambda m: entry if m.reg("EDX") == 5 else 0)   # substituted: the play's role lookup
        self.g.run(0xCE32A, 0xCC160, {"ECX": 0x77000, "EAX": 3})
        self.assertEqual(self.g.counts(self.g.pcode(1, 9)), [1, 1, 0, 0, 0])
        self.assertEqual(self.g.counts(self.g.pcode(0, 31)), [1 - 1, 0, 1, 1, 1])
        self.assertEqual((self.g.m.reg("ECX"), self.g.m.reg("EAX")), (0x77000, 3))
        self.g.run(0xCE2A4, 0xCC1F0, {"EDI": entry, "EAX": 4})
        self.assertEqual(self.g.counts(self.g.pcode(1, 9)), [2, 2, 0, 0, 0])
        self.assertEqual(self.g.counts(self.g.pcode(0, 31)), [0, 0, 2, 2, 2])
        self.assertEqual(self.g.diag("sacks"), 2)

    def test_reset_clears_everything_then_runs_the_log_reset(self):
        qb = self.g.actor(0, 1, 0, 0, defense=False)
        self.g.actor(1, 4, 0.2 * YD, 0, defense=True)
        self.g.run(0x2DB2CA, 0x2DAF10, {"ESI": qb}, stack=(0,))
        self.assertEqual(self.g.diag("live"), 1)
        for site in (0xA78EF, 0x10B427):
            self.g.run(site, 0xCCE00, {"EAX": 0x55})
            self.assertEqual(self.g.m.reg("EAX"), 0x55)
            self.assertEqual(bytes(self.g.m.uc.mem_read(self.g.data, prs.STATE_SIZE)), bytes(prs.STATE_SIZE))


class Commit:
    """A club of synthetic players with native history, a team object and live records for one side."""

    def __init__(self, game, positions, *, side=0, played=True, ratings=None):
        from tests.mod_editor.test_nfl2k5_honors import word
        self.g = game
        m = game.m
        self.players = m.roster([(2, [word(0, 1, 5)]) for _ in positions])
        self.club = m.HEAP + 0x48000
        self.team = m.HEAP + 0x49000
        m.uc.mem_write(self.team, bytes(0x200))
        m.put8(self.team + 0x11C, len(positions))
        self.stats = m.HEAP + 0x4A000
        for i, (p, pos) in enumerate(zip(self.players, positions)):
            m.put(self.club + 4 * i, p)
            m.put8(p + 0x35, pos)
            r = (ratings or {}).get(i, {})
            m.put8(p + 0x48, r.get("pass_rush", 70))
            m.put8(p + 0x46, r.get("pass_block", 70))
            m.put(p + 0x28, (r.get("rank", 0) & 7) << 10)
            rec = game.live(side, i)
            holder = self.stats + 0x100 * i
            obj = holder + 0x10
            m.uc.mem_write(holder, bytes(0x100))
            m.put(rec + 0x30, holder)
            m.put(holder, obj)
            m.put(obj, 1 if played else 0)                 # [stats] != 0: played this game (selector 99)
            if "half_sacks" in r:
                blk = holder + 0x80
                m.uc.mem_write(obj + 0x24, struct.pack("<f", 1.0))
                m.put(obj + 0x28, blk)
                m.put8(blk + 4, r["half_sacks"])
            if "sacked" in r:
                blk = holder + 0xA0
                m.uc.mem_write(obj + 0x04, struct.pack("<f", 1.0))
                m.put(obj + 0x08, blk)
                m.put8(blk + 0x23, r["sacked"])
        self.side = side

    def run(self):
        g = self.g
        sp = g.run(0x134E1F, 0x134E26, {"EDI": self.team, "ESI": self.club},
                   stack=(0, 0, 0, 0, 0, self.side), budget=5_000_000)
        assert g.m.reg("EDX") == 0x4C and g.m.get(g.m.reg("ESP")) == 0 and g.m.reg("ESP") == sp - 4
        return [[g.m.call(0x14EE40, ecx=p, edx=f, budget=100_000) & 0xFFFF for f in range(106, 111)]
                for p in self.players]


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class CommitTests(unittest.TestCase):
    def setUp(self):
        data = patched()
        if data is None:
            self.skipTest("pinned USA retail XBE is not available")
        self.g = Game(data)

    def test_played_game_commits_the_live_counters_and_clears_them(self):
        c = Commit(self.g, [16, 13, 3])
        self.g.m.put(self.g.data, 1)                     # live
        base = self.g.data + prs.STATE_COUNTERS_OFF
        self.g.m.uc.mem_write(base + 5 * self.g.pcode(0, 0), bytes([4, 2, 0, 0, 0]))
        self.g.m.uc.mem_write(base + 5 * self.g.pcode(0, 1), bytes([0, 0, 3, 1, 1]))
        self.assertEqual(c.run(), [[4, 2, 0, 0, 0], [0, 0, 3, 1, 1], [0, 0, 0, 0, 0]])
        self.assertEqual(self.g.counts(self.g.pcode(0, 0)), [0, 0, 0, 0, 0])
        self.assertEqual(self.g.m.get(self.g.data), 1, "side 0 keeps the live flag for side 1")
        again = c.run()                                  # a second commit adds nothing (counters were consumed)
        self.assertEqual(again[0], [4, 2, 0, 0, 0])

    def test_side_one_commit_resets_the_game_state(self):
        c = Commit(self.g, [16], side=1)
        self.g.m.put(self.g.data, 1)
        self.g.m.uc.mem_write(self.g.data + prs.STATE_COUNTERS_OFF + 5 * self.g.pcode(1, 0), bytes([1, 0, 0, 0, 0]))
        self.assertEqual(c.run()[0], [1, 0, 0, 0, 0])
        self.assertEqual(bytes(self.g.m.uc.mem_read(self.g.data, prs.STATE_SIZE)), bytes(prs.STATE_SIZE))

    def test_simulated_game_draws_from_ratings_and_the_engine_sacks(self):
        totals = {"elite": [0, 0], "weak": [0, 0], "sacker": [0, 0]}
        ol = [0, 0, 0]
        games = 60
        for week in range(games):
            g = Game(patched())
            g.m.uc.mem_write(0xE576B4, bytes([week]))
            c = Commit(g, [16, 16, 15, 14, 13, 12, 0], ratings={
                0: {"pass_rush": 95}, 1: {"pass_rush": 58}, 2: {"pass_rush": 70, "half_sacks": 4},
                3: {"pass_block": 99}, 4: {"pass_block": 55}, 5: {"pass_block": 75}, 6: {"sacked": 3}})
            rows = c.run()
            for key, i in (("elite", 0), ("weak", 1), ("sacker", 2)):
                totals[key][0] += rows[i][0]
                totals[key][1] += rows[i][1]
            for k in range(3):
                ol[k] += sum(rows[3 + j][2 + k] for j in range(3))
            self.assertEqual(rows[6], [0, 0, 0, 0, 0])
            self.assertGreaterEqual(rows[2][0], 2)          # the engine's two sacks are pressures
            self.assertGreaterEqual(rows[2][1], 2)          # and QB hits
            for r in rows[3:6]:
                self.assertLessEqual(r[4], r[3])            # sacks allowed are QB hits allowed
                self.assertLessEqual(r[3], r[2])            # which are pressures allowed
        elite, weak = totals["elite"][0] / games, totals["weak"][0] / games
        self.assertGreater(elite, 1.8)
        self.assertLess(elite, 3.6)
        self.assertLess(weak, 0.9)
        self.assertGreater(elite, 2.5 * weak)
        self.assertGreater(ol[0] / games, 2.5)             # charged non-sack + sack pressures a game
        self.assertLess(ol[0] / games, 7.5)
        self.assertGreater(ol[2], 0)

    def test_draws_are_deterministic_and_skip_players_who_did_not_play(self):
        rows = []
        for _ in range(2):
            g = Game(patched())
            rows.append(Commit(g, [16, 16], ratings={0: {"pass_rush": 95}, 1: {"pass_rush": 95}}).run())
        self.assertEqual(rows[0], rows[1])
        g = Game(patched())
        self.assertEqual(Commit(g, [16, 13], played=False).run(), [[0] * 5, [0] * 5])


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class CardTests(unittest.TestCase):
    def setUp(self):
        data = patched()
        if data is None:
            self.skipTest("pinned USA retail XBE is not available")
        self.data = data
        self.g = Game(data)
        self.lay = prs.read_only_layout(self.g.ro)

    def card(self, position):
        from tests.mod_editor.test_nfl2k5_honors import word
        m = self.g.m
        p = m.roster([(3, [word(106, 1, 7), word(106, 2, 11), word(110, 2, 2), word(0, 2, 16)])])[0]
        m.put8(p + 0x35, position)
        m.put(0x00C90248, p)
        pushes = []
        m.hook(0x6E390, lambda mm: pushes.append(mm.reg("EDX")), pop=0)   # substituted: the screen push
        self.g.run(0x320B90, m.STOP, {}, stack=(m.STOP, 0x1234))
        return p, pushes

    def test_every_position_gets_its_sheet_and_list(self):
        for pos, field, lst, screen in ((13, 0x535A2C, "list_ol", 0x5365A8), (12, 0x535A2C, "list_ol", 0x5365A8),
                                        (14, 0x535A2C, "list_ol", 0x5365A8), (16, 0x535A2C, "list_def", 0x5365A8),
                                        (4, 0x535A2C, "list_def", 0x5365A8), (3, 0x53592C, "list_wr", 0x536340),
                                        (9, 0x53592C, "list_wr", 0x536340), (7, 0x53582C, "list_rb", 0x5360D8)):
            _p, pushes = self.card(pos)
            self.assertEqual(pushes, [screen], pos)
            self.assertEqual(self.g.m.get(field), self.lay[lst], pos)
        _p, pushes = self.card(0)                          # QB: retail screen, no list change by this owner
        self.assertEqual(pushes, [0x535E70])

    def test_lists_carry_the_new_columns_in_order(self):
        image = XbeImage(self.data)

        def cols(key):
            words = struct.unpack_from("<15I", image.read(self.lay[key] + 0x9C, 60))
            return list(words[:words.index(0)])

        self.assertEqual(cols("list_wr")[:3], [prs.YR, prs.GAMES, self.lay["d_tgt"]])
        rb = cols("list_rb")
        self.assertEqual(rb[rb.index(self.lay["d_tgt"]) + 1], prs.REC)
        d = cols("list_def")
        self.assertEqual(d[d.index(prs.SACK) + 1: d.index(prs.SACK) + 3], [self.lay["d_prs"], self.lay["d_qbh"]])
        self.assertEqual(cols("list_ol"), [prs.YR, prs.GAMES, self.lay["d_pa"], self.lay["d_ha"], self.lay["d_sa"]])
        for key, abbr, long_name, sid in prs.COLUMNS:
            desc = image.read(self.lay["d_" + key], 0xB0)
            self.assertEqual(struct.unpack_from("<I", desc, 0xA0)[0], sid)
            self.assertEqual(image.read(struct.unpack_from("<I", desc, 0x70)[0], 2 * len(abbr)).decode("utf-16-le"), abbr)

    def test_card_value_reads_season_years_ago_and_total(self):
        m = self.g.m
        p, _ = self.card(16)
        trampoline = m.HEAP + 0x47000
        m.uc.mem_write(trampoline, b"\xe8" + struct.pack("<i", self.g.at["prs_card_value"] - (trampoline + 5))
                       + bytes.fromhex("d91d") + struct.pack("<I", m.HEAP + 0x47100) + b"\xc3")

        def value(bank, field):
            m.put(0x00C90254, bank)                    # row 0's bank
            m.call(trampoline, ecx=0, edx=field)
            return m.float_at(m.HEAP + 0x47100)

        # years pro 3: the current season is slot 3, one season ago slot 2, two seasons ago slot 1
        self.assertEqual(value(11, 106), 0.0)
        self.assertEqual(value(12, 106), 11.0)
        self.assertEqual(value(13, 106), 7.0)
        self.assertEqual(value(9, 106), 18.0)          # Total: 7 + 11
        self.assertEqual(value(12, 110), 2.0)
        self.assertEqual(value(9, 110), 2.0)
        self.assertEqual(value(9, 50), 0.0)            # not one of this owner's fields
        del p


if __name__ == "__main__":
    unittest.main()
