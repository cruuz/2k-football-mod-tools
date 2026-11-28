"""b81 #46a (release blocker): a computer club is never left without a kicker or a punter (validator I5).

The combined franchise panel (judge RESULTS.txt RR1, 2026-11-27) found three ways the in-season K/P cover failed once game
outcomes made kickers and punters injurable:
- short of room: the cover signs through the fill gate, whose room rule refuses a club with less room than any free agent
  asks (76002 2029 BUF: room 127, so the punter kicked five regular-season and three playoff games; 76002 2028 ATL: room
  217, one game);
- the playoffs: the weekly advance's stage-9 path (0x247E6E) jumps past the weekly CPU pass at 0x248010, so the cover never
  ran in stage 9 (76001 2031 JAX: no kicker in a conference final with 5,005 of room);
- hoarding: the man the cover signed stayed after the starter healed (557 of 1,240 club-seasons with two or three kickers
  at week 18; the control 43).

Unicorn, the retail executable with the economy (tools/franchise_economy/probe.py, the hunt1 tests' method) and, where the
kept panel images are present, those images: club 0, a computer club, in the regular season (stage 8) or the playoffs
(stage 9). Every case here fails on the integration head 6e37263e1 (its cover signs nothing short of room, has no stage-9
entry and releases nobody)."""
from __future__ import annotations

import hashlib
import os
import struct
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes, retail_roster

K, P = 1, 2
STAGE = 0xE576A4
TABLE = 0x248088                      # the weekly advance's jump table (stages 1..9)
STAGE9_PATH = 0x247E6E                # retail stage 9 entry of that table
STAGE9_SIM, SIM, AFTER_SIM = 0x247E77, 0xC7CB0, 0x247E7C   # stage 9's call of the week's games, and its return
KP_WINDOWS = (0x28C2F0, 0x2DCC10, 0x2F7D00, 0x256120, 0x28DC10, 0x357960)
KP_KEEP = (30, 30, 30, 6, 6, 2, 2, 3, 1, 3, 3, 5, 2, 3, 4, 4, 4)   # kp_pick: a man at depth row >= this may go
CUT_MIN = (2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 3, 2, 2, 3, 3, 3, 4)   # the smart cut's minimums (cut_rows row 2)


class Sites(unittest.TestCase):
    def test_stage_nine_sims_the_week_then_covers(self):
        """Review F1: stage 9's sim call (0x247E77) comes to economy_stage9 (call 0xC7CB0; mov ecx, ebp; jmp
        economy_cover_all), so the cover runs after the week's games as in stage 8; the jump table stays retail."""
        retail = retail_bytes()
        before = struct.unpack("<9I", XbeImage(retail).read(TABLE, 36))
        self.assertEqual(before[8], STAGE9_PATH)
        applied = XbeImage(economy.apply(retail)[0])
        after = struct.unpack("<9I", applied.read(TABLE, 36))
        self.assertEqual(after[8], STAGE9_PATH)
        self.assertEqual(after[5], economy.SYMBOLS["economy_stage6"])
        self.assertEqual(after[:5] + after[6:8], before[:5] + before[6:8])
        stub = economy.SYMBOLS["economy_stage9"]
        call = applied.read(STAGE9_SIM, 5)
        self.assertEqual((call[0], STAGE9_SIM + 5 + struct.unpack_from("<i", call, 1)[0]), (0xE8, stub))
        code = applied.read(stub, 12)                 # call 0xC7CB0; mov ecx, ebp; jmp economy_cover_all
        self.assertEqual((code[0], code[5:7], code[7]), (0xE8, bytes.fromhex("89e9"), 0xEB))
        self.assertEqual(stub + 5 + struct.unpack_from("<i", code, 1)[0], SIM)
        self.assertEqual(stub + 9 + struct.unpack("<b", code[8:9])[0], economy.SYMBOLS["economy_cover_all"])
        site = next(s for s in economy.sites() if s.va == economy.STAGE9_SIM)
        self.assertEqual(hashlib.sha256(XbeImage(retail).read(STAGE9_SIM, 5)).hexdigest(), site.digest)
        self.assertIn(economy.STAGE9_SIM, economy.REVISION_10_NEW)
        self.assertFalse(any(s.va == 0x2480A8 for s in economy.sites()))

    def test_the_cover_windows_are_unreferenced_retail_functions(self):
        from tools.franchise_economy import dead_code
        retail = retail_bytes()
        windows = {va: dead_code.WINDOWS[va] for va in KP_WINDOWS}
        image = XbeImage(retail)
        for va, (size, digest) in windows.items():
            self.assertEqual(hashlib.sha256(image.read(va, size)).hexdigest(), digest)
            self.assertEqual(economy.R10_WINDOW_PINS[va], digest)
        self.assertEqual({k: v for k, v in dead_code.references(retail, windows).items() if v}, {})
        self.assertEqual(economy.SYMBOLS["economy_cover"], 0x2DCC10)

    def test_released_and_base_images_still_upgrade_in_place(self):
        for name in ("NFL2K5_V09_RELEASED_XBE", "NFL2K5_V08_XBE"):
            path = Path(os.environ.get(name, "/nonexistent"))
            if not path.is_file():
                self.skipTest(f"{name} is not set (b81/env.sh)")
            payload = path.read_bytes()
            self.assertEqual(economy.status(payload), "legacy", name)
            self.assertEqual(economy.status(economy.apply(payload)[0]), "applied", name)


class CoverMachine:
    """Club 0 of the retail roster on the retail executable with this economy (the hunt1 tests' fixture)."""
    @classmethod
    def setUpClass(cls):
        cls.after, _ = economy.apply(retail_bytes())
        cls.body = retail_roster()

    def league(self, *, kicker="gone", size=52, stage=8, room=40000, second=None, pool_hurt=False):
        """Club 0 grown to `size` with one-year free agents (no K or P); its only kicker hurt ("hurt", 3 weeks), off the
        active list ("gone": modern IR takes him off it) or healthy ("ok"); `second`: with "ok", the pool's two best healthy
        kickers replace the club's own ("best_last" or "best_first" on the list); with "hurt", one healthy pool kicker joins
        him; `room` = cap - payroll."""
        from tools.franchise_economy.probe import start
        m = start(self.body, self.after)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team, lst = m.team_base, m.root + 0x38
        for t in range(34):
            m.put(0xE5775C + 4 * t, 0)                         # every club the computer's
        m.put(STAGE, 5)
        free = [m.call(0x242500, ecx=lst, edx=i) for i in range(m.call(0x2424F0, ecx=lst))]
        for p in free:
            if self.count(m, team) >= size:
                break
            raw = bytearray(m.uc.mem_read(p, 84))
            if raw[0x35] in (K, P) or raw[0x35] >= 17:
                continue
            m.call(0x2425C0, ecx=lst, edx=p)
            raw[0x27] = (raw[0x27] & 0xF0) | 1
            raw[0x24] = (raw[0x24] & 0xF0) | 1
            struct.pack_into("<H", raw, 10, 30)
            m.uc.mem_write(p, bytes(raw))
            self.assertTrue(m.call(0xC3EE0, ecx=team, edx=p))
        while self.count(m, team) > size:
            m.call(0x2BD900, ecx=team, edx=self.members(m, team)[-1], args=(1, 0))
        kickers = self.at(m, team, K)
        self.assertEqual(len(kickers), 1)
        mine = kickers[0]
        if kicker == "hurt":
            m.put(mine + 0x20, (m.get(mine + 0x20) & 0x003FFFFF) | 0x80000000 | (3 << 22))
        elif kicker == "gone":
            m.call(0xC3EB0, ecx=team, edx=mine)                 # off the active list, as modern IR takes him
        if second:
            # the pool's two best healthy kickers, each on a one-year deal (a release divides the value by the length)
            pool = sorted((p for p in self.free(m) if m.uc.mem_read(p + 0x35, 1)[0] == K and not self.hurt(m, p)),
                          key=lambda p: -self.rating(m, p))
            hi, lo = pool[0], pool[1]
            self.assertGreater(self.rating(m, hi), self.rating(m, lo))
            if kicker == "ok":                                  # two healthy kickers of the pool replace the club's own
                m.call(0xC3EB0, ecx=team, edx=mine)
                order = (lo, hi) if second == "best_last" else (hi, lo)
            else:
                order = (lo,)
            for pick in order:
                raw = bytearray(m.uc.mem_read(pick, 84))
                raw[0x27] = (raw[0x27] & 0xF0) | 1
                raw[0x24] = (raw[0x24] & 0xF0) | 1
                struct.pack_into("<H", raw, 10, 30)
                m.uc.mem_write(pick, bytes(raw))
                m.call(0x2425C0, ecx=lst, edx=pick)
                self.assertTrue(m.call(0xC3EE0, ecx=team, edx=pick))
        if pool_hurt:
            for p in self.free(m):
                if m.uc.mem_read(p + 0x35, 1)[0] == K:
                    m.put(p + 0x20, m.get(p + 0x20) | 0x80000000 | (3 << 22))
        m.put(STAGE, stage)
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) + room)
        return m, team

    @staticmethod
    def count(m, team):
        return m.uc.mem_read(team + 0x11C, 1)[0]

    def members(self, m, team):
        return [m.get(team + 4 * i) for i in range(self.count(m, team))]

    def at(self, m, team, pos):
        return [p for p in self.members(m, team) if m.uc.mem_read(p + 0x35, 1)[0] == pos]

    @staticmethod
    def free(m):
        lst = m.root + 0x38
        return [m.call(0x242500, ecx=lst, edx=i) for i in range(m.call(0x2424F0, ecx=lst))]

    @staticmethod
    def hurt(m, p):
        return bool(m.uc.mem_read(p + 0x23, 1)[0] & 0x80)

    @staticmethod
    def rating(m, p):
        """0x246D80(p, 0), the rating best_at compares (a stub: call it, fstp the float to a scratch word)."""
        stub, scratch = m.STOP + 0x10, 0x3000100
        m.uc.mem_write(stub, b"\xe8" + struct.pack("<i", 0x246D80 - (stub + 5)) + b"\xd9\x1d" + struct.pack("<I", scratch) + b"\xc3")
        m.call(stub, ecx=p, edx=0)
        return struct.unpack("<f", bytes(m.uc.mem_read(scratch, 4)))[0]

    def cover(self, m, team):
        before = self.members(m, team)
        m.call(economy.SYMBOLS["economy_cover"], ecx=team, edx=m.ARENA + 0x1A0000, budget=1_000_000_000)
        after = self.members(m, team)
        m.call(0xC3F00, ecx=team)
        pos = lambda ps: [m.uc.mem_read(p + 0x35, 1)[0] for p in ps]
        return dict(released=[p for p in before if p not in after], signed=[p for p in after if p not in before],
                    released_pos=pos([p for p in before if p not in after]), signed_pos=pos([p for p in after if p not in before]),
                    healthy_k=[p for p in self.at(m, team, K) if not self.hurt(m, p)], kickers=self.at(m, team, K),
                    room=m.get(0xE3C278) - m.get(team + 0x124), count=self.count(m, team))



@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class Cover(CoverMachine, unittest.TestCase):
    @staticmethod
    def minimum_value(m, p):
        """floor_of(his years) (the CBA minimum, runtime.c) as the deal's value / 10, rounded up."""
        from tools.franchise_economy import assemble
        minimums = assemble.inputs()[2]
        pro, season = m.uc.mem_read(p + 0x25, 1)[0] & 31, m.get(0xE576B8)
        return ((minimums[min(pro, 7)] + min(season, 4) * 45 + 3) // 4 + 9) // 10

    def minimum_deal(self, m, p):
        """A one-year deal at his league minimum: 1 year left, length 1, balanced, value / 10 = ceil(floor_of / 10)."""
        raw = bytes(m.uc.mem_read(p, 0x54))
        self.assertEqual((struct.unpack_from("<H", raw, 10)[0], raw[0x24] & 15, raw[0x27] & 15, raw[0x26]),
                         (self.minimum_value(m, p), 1, 1, 2))

    def test_short_of_room_the_kicker_signs_past_the_cap_gate_at_his_minimum(self):
        """Review F3/F4 (coordinator 11/27): no cap-driven releases; the K signs past the gate at his league minimum, so
        the club ends over the cap by at most that minimum."""
        m, team = self.league(room=100)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["signed_pos"], got["released"]), (1, [K], []))
        self.minimum_deal(m, got["signed"][0])
        self.assertGreater(got["room"], -600)

    def test_far_over_the_cap_the_kicker_still_signs_and_nobody_goes(self):
        m, team = self.league(room=-4000)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["released"]), (1, []))
        self.minimum_deal(m, got["signed"][0])

    def test_a_hurt_starter_is_never_the_release_that_makes_room(self):
        """Coordinator 11/27: never a hurt depth-row-0 man. The first version took the least price lost among men whose
        charge clears the shortfall, whatever their health: here only the hurt starter's charge clears it, and it released
        him. Now a full club releases exactly one non-starter (kp_pick) and the K signs over the cap."""
        m, team = self.league(size=54, room=100)
        pos = next(q for q in (3, 4, 13, 15, 16) if len(self.at(m, team, q)) > CUT_MIN[q])   # a position with surplus
        star = max(self.at(m, team, pos), key=lambda p: self.rating(m, p))
        m.put(star + 0x20, (m.get(star + 0x20) & 0x003FFFFF) | 0x80000000 | (2 << 22))
        m.uc.mem_write(star + 0x28, struct.pack("<H", struct.unpack("<H", bytes(m.uc.mem_read(star + 0x28, 2)))[0] & ~0x1C00))
        m.uc.mem_write(star + 10, struct.pack("<H", 6000))       # his salary alone clears the club's shortfall
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) - 4000)            # 4,000 over the cap
        got = self.cover(m, team)
        self.assertIn(star, self.members(m, team))
        self.assertEqual((len(got["released"]), got["signed_pos"], got["count"]), (1, [K], 53))
        row = (struct.unpack("<H", bytes(m.uc.mem_read(got["released"][0] + 0x28, 2)))[0] >> 10) & 7
        self.assertGreater(row, 0)

    def test_with_room_it_signs_and_releases_nobody(self):
        m, team = self.league(room=40000)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["signed_pos"], got["released"]), (1, [K], []))

    def expected_pick(self, m, team):
        """kp_pick's rule in Python: the lowest healthy rating (ties: the earlier slot) among men at depth row >= KP_KEEP."""
        best = None
        for p in self.members(m, team):
            raw = bytes(m.uc.mem_read(p, 0x54))
            if raw[0x35] < 17 and (struct.unpack_from("<H", raw, 0x28)[0] >> 10 & 7) >= KP_KEEP[raw[0x35]]:
                r = struct.unpack("<I", struct.pack("<f", self.rating(m, p)))[0]
                if best is None or r <= best[0]:
                    best = (r, p)
        return best and best[1]

    def test_at_53_exactly_one_man_goes_by_kp_pick(self):
        """Review F3-F5: a full club releases exactly one man, the lowest healthy rating among non-starters at a position
        above its keep target; never a QB, K or P (K and P keep 30, QB 30); the count stays 53."""
        m, team = self.league(size=54, room=40000)          # 53 once the kicker is off the list
        self.assertEqual(self.count(m, team), 53)
        want = self.expected_pick(m, team)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["count"], got["released"]), (1, 53, [want]))
        self.assertNotIn(got["released_pos"][0], (0, K, P))

    def test_a_full_club_with_nobody_to_release_signs_nobody(self):
        """Every man at depth row 0 (no non-starter anywhere): kp_pick finds nobody, so no release and no signing (the
        append would refuse a 54th)."""
        m, team = self.league(size=54, room=40000)
        for p in self.members(m, team):
            m.uc.mem_write(p + 0x28, struct.pack("<H", struct.unpack("<H", bytes(m.uc.mem_read(p + 0x28, 2)))[0] & ~0x1C00))
        got = self.cover(m, team)
        self.assertEqual((got["released"], got["signed"], got["count"]), ([], [], 53))

    def test_no_healthy_kicker_in_the_pool_means_no_release(self):
        m, team = self.league(room=100, pool_hurt=True)
        got = self.cover(m, team)
        self.assertEqual((got["released"], got["signed"]), ([], []))

    def test_a_spare_kicker_goes_and_the_better_one_stays(self):
        for second in ("best_last", "best_first"):
            with self.subTest(second=second):
                m, team = self.league(kicker="ok", second=second)
                ks = self.at(m, team, K)
                best = max(ks, key=lambda p: self.rating(m, p))
                got = self.cover(m, team)
                self.assertEqual(got["kickers"], [best])
                self.assertEqual((got["released_pos"], got["signed"]), ([K], []))

    def test_a_hurt_starter_keeps_his_place_beside_his_cover(self):
        m, team = self.league(kicker="hurt", second="one")
        got = self.cover(m, team)
        self.assertEqual((len(got["kickers"]), len(got["healthy_k"]), got["released"], got["signed"]), (2, 1, [], []))

    def test_a_preseason_camp_above_53_signs_into_its_camp_room(self):
        """Stage 7 (Panel B: 76005 2034 CLE opened week 1 with no punter): the preseason upkeep covers too; a camp roster
        above 53 signs without a cut (the gate allows a K or P up to 64)."""
        m, team = self.league(size=61, stage=7, room=40000)
        self.assertEqual(self.count(m, team), 60)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["count"], got["released"]), (1, 61, []))

    def test_after_the_gate_cut_the_stage_7_pass_gives_a_club_of_53_a_kicker(self):
        """Panel B (76005 2034 CLE opened week 1 without a punter): after the stage-7 action's gate cut the economy's
        after-stage pass (economy_clubs, STAGE still 7) runs the upkeep, which now covers from stage 7. On the old code
        (the cover from stage 8 only) the club of 53 stays without a kicker."""
        m, team = self.league(size=54, stage=7, room=40000)
        self.assertEqual(self.count(m, team), 53)
        m.call(economy.SYMBOLS["economy_clubs"], ecx=m.ARENA + 0x1A0000, edx=0, budget=2_000_000_000)
        self.assertEqual(len([p for p in self.at(m, team, K) if not self.hurt(m, p)]), 1)
        self.assertLessEqual(self.count(m, team), 53)

    def test_the_preseason_upkeep_runs_the_cover(self):
        """economy_week in stage 7 (the preseason's weekly pass; the same upkeep runs after the stage's gate cut), fills
        off: the club with no kicker has one after it."""
        m, team = self.league(size=54, stage=7, room=40000)
        zero = struct.unpack("<I", struct.pack("<f", 0.0))[0]
        m.call(economy.SYMBOLS["economy_week"], ecx=m.ARENA + 0x1A0000, edx=0, args=(zero, zero), budget=2_000_000_000)
        self.assertEqual(len([p for p in self.at(m, team, K) if not self.hurt(m, p)]), 1)

    def test_a_kicker_hurt_in_a_simulated_playoff_game_is_covered_before_the_next_game(self):
        """Review F1: stage 9's sim call runs the week's games, then the cover, then returns to the advance (0x247E7C)
        with its registers. The week's games are stubbed: they hurt club 0's only kicker (3 weeks)."""
        m, team = self.league(kicker="ok", stage=9, room=40000)
        mine = self.at(m, team, K)[0]
        menu = m.ARENA + 0x1A0000
        seen = {}

        def games():
            seen.update(ecx=m.reg("ECX"), edx=m.reg("EDX"))
            m.put(mine + 0x20, (m.get(mine + 0x20) & 0x003FFFFF) | 0x80000000 | (3 << 22))
            m.ret()
        m.leaf(SIM, games, reason="the week's games: they hurt the kicker")
        regs = dict(EBX=1, ESI=0x5151, EDI=0x6262, EBP=menu)
        for name, value in dict(ECX=19, EDX=menu, EAX=0, ESP=m.STACK, EFLAGS=0x202, **regs).items():
            m.reg(name, value)
        m.uc.emu_start(STAGE9_SIM, AFTER_SIM, count=2_000_000_000)
        self.assertEqual(m.reg("EIP"), AFTER_SIM)
        self.assertEqual(seen, dict(ecx=19, edx=menu))
        self.assertEqual({k: m.reg(k) for k in regs}, regs)
        self.assertEqual(m.reg("ESP"), m.STACK)
        self.assertTrue(self.hurt(m, mine))
        self.assertEqual(len([p for p in self.at(m, team, K) if not self.hurt(m, p)]), 1)
        for c in range(32):
            t = m.team_base + 500 * c
            for pos in (K, P):
                self.assertGreaterEqual(len([p for p in self.at(m, t, pos) if not self.hurt(m, p)]), 1, (c, pos))

    def test_stage_nine_leaves_the_pro_bowl_rosters_alone(self):
        """In stage 9 n_teams() reads 34: records 32 and 33 (team slots 49 and 50) are the Pro Bowl rosters, the league's
        own player records. The practice squad's slot remove refuses them, so a release from one left the man on his club
        and put him in free agency with no contract (76001 2026: six players, then the 2027 re-signing stage listed one of
        them twice and the payroll walk never ended). The cover walks the 32 clubs."""
        m, team = self.league(stage=9, room=40000)
        m.put(0xE576AC, 34)
        for t, slot in ((32, 49), (33, 50)):                    # the club table's Pro Bowl entries, as the game sets them
            m.put(0xE5786C + 4 * t, m.team_base + 500 * slot)
        pro = m.call(0xC4C50, ecx=32)
        self.assertEqual(pro, m.team_base + 500 * 49)
        stars = [m.get(m.team_base + 500 * c + 4 * i) for c in range(1, 32) for i in (0, 1)]
        stars = [p for p in stars if m.uc.mem_read(p + 0x35, 1)[0] not in (K, P)][:40]
        for i, p in enumerate(stars):
            m.put(pro + 4 * i, p)
        m.uc.mem_write(pro + 0x11C, bytes([len(stars)]))
        m.call(economy.SYMBOLS["economy_cover_all"], ecx=m.ARENA + 0x1A0000, budget=2_000_000_000)
        self.assertEqual(self.members(m, pro), stars)
        rostered = {p for c in range(32) for p in self.members(m, m.team_base + 500 * c)}
        self.assertEqual(rostered & set(self.free(m)), set())

    def test_the_economy_release_refuses_a_record_past_the_32_clubs(self):
        """Belt and braces (coordinator 11/27): economy_release does nothing for a team record past the 32 league clubs
        (the Pro Bowl rosters, slots 49 and 50), and releases from a league club as before."""
        m, team = self.league(stage=9, room=40000)
        pro = m.team_base + 500 * 49
        star = self.members(m, m.team_base + 500 * 7)[0]
        m.put(pro, star)
        m.uc.mem_write(pro + 0x11C, bytes([1]))
        contract, free = bytes(m.uc.mem_read(star, 0x54)), self.free(m)
        m.call(economy.SYMBOLS["economy_release"], ecx=pro, edx=star, budget=50_000_000)
        self.assertEqual((self.members(m, pro), self.free(m), bytes(m.uc.mem_read(star, 0x54))), ([star], free, contract))
        self.assertIn(star, self.members(m, m.team_base + 500 * 7))
        last = m.team_base + 500 * 31
        man = self.members(m, last)[-1]
        m.call(economy.SYMBOLS["economy_release"], ecx=last, edx=man, budget=50_000_000)
        self.assertNotIn(man, self.members(m, last))
        self.assertIn(man, self.free(m))


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class SmartCut(CoverMachine, unittest.TestCase):
    """b81 #46c (the combined judge's B8): modern IR brings a man back at 53 with the cut-down 0x2BF9A0 (the economy's smart
    cut), which ranked by 0x246D80(p, 1). In the composed build flag 1 discounts an injured man (a starting QB out a week:
    0.951 at flag 0, 0.383 at flag 1, kept image 76002 2029 w14), so a hurt starter at a position above its keep target
    (QB 3 > 2) was the one released: Daniels (76008, hurt week 11, cut week 13), Murray (76003). The retail rating here has
    no such discount, so a stub at 0x246D80 gives the hurt man the composed build's flag-1 value and his real one at flag 0.
    On 6e37263e1 the hurt starter is released."""

    KEEP = (2, 1, 1, 6, 6, 2, 2, 3, 1, 3, 0, 5, 2, 3, 4, 4, 4)      # the smart cut's keep targets (cut_rows row 1)

    def club_with(self, pos, n):
        """Club 0 with exactly n men at pos and every other position at or under its keep target (about 50 active), so a
        cut of one man chooses at pos (free agents on one-year deals appended, other men released)."""
        m, team = self.league(kicker="ok", size=53)
        lst = m.root + 0x38
        for q in range(17):
            limit = n if q == pos else self.KEEP[q] if q not in (1, 2) else 1
            while len(self.at(m, team, q)) > limit:
                m.call(0x2BD900, ecx=team, edx=self.at(m, team, q)[-1], args=(1, 0))
        while len(self.at(m, team, pos)) < n:
            fa = [p for p in self.free(m) if m.uc.mem_read(p + 0x35, 1)[0] == pos and not self.hurt(m, p)][0]
            raw = bytearray(m.uc.mem_read(fa, 84))
            raw[0x27] = (raw[0x27] & 0xF0) | 1; raw[0x24] = (raw[0x24] & 0xF0) | 1
            struct.pack_into("<H", raw, 10, 30)
            m.uc.mem_write(fa, bytes(raw))
            m.call(0x2425C0, ecx=lst, edx=fa)
            self.assertTrue(m.call(0xC3EE0, ecx=team, edx=fa))
        m.put(STAGE, 8)
        return m, team

    def hurt_starter(self, m, team, pos, discounted):
        """The best-rated man at pos: hurt 2 weeks, depth row 0; with `discounted` 0x246D80(him, 1) returns 0.05."""
        star = max(self.at(m, team, pos), key=lambda p: self.rating(m, p))
        m.put(star + 0x20, (m.get(star + 0x20) & 0x003FFFFF) | 0x80000000 | (2 << 22))
        m.uc.mem_write(star + 0x28, struct.pack("<H", struct.unpack("<H", bytes(m.uc.mem_read(star + 0x28, 2)))[0] & ~0x1C00))
        if discounted:
            stub, low = m.STOP + 0x100, 0x3000180
            m.uc.mem_write(low, struct.pack("<f", 0.05))
            code = (b"\x81\xf9" + struct.pack("<I", star) + b"\x75\x0b\x85\xd2\x74\x07\xd9\x05" + struct.pack("<I", low) + b"\xc3"
                    + b"\x52\x0f\xb6\x51\x35")
            code += b"\xe8" + struct.pack("<i", 0x246D60 - (stub + len(code) + 5)) + b"\xc3"
            m.uc.mem_write(stub, code)
            m.uc.mem_write(0x246D80, b"\xe9" + struct.pack("<i", stub - 0x246D85))
            m.uc.ctl_flush_tb()
        return star

    def test_the_cut_ranks_by_the_healthy_rating(self):
        for pos, n in ((0, 3), (15, 5)):           # QB above its keep target 2; DT above 4
            with self.subTest(position=pos):
                m, team = self.club_with(pos, n)
                star = self.hurt_starter(m, team, pos, discounted=True)
                count = self.count(m, team)
                m.call(0x2BF9A0, ecx=team, edx=count - 1, budget=400_000_000)
                self.assertIn(star, self.members(m, team))
                self.assertEqual((self.count(m, team), len(self.at(m, team, pos))), (count - 1, n - 1))

    def test_a_hurt_starter_at_row_0_is_never_cut(self):
        """Even when he is the lowest-rated man at his position by the healthy rating."""
        m, team = self.club_with(0, 3)
        worst = min(self.at(m, team, 0), key=lambda p: self.rating(m, p))
        m.put(worst + 0x20, (m.get(worst + 0x20) & 0x003FFFFF) | 0x80000000 | (2 << 22))
        m.uc.mem_write(worst + 0x28, struct.pack("<H", struct.unpack("<H", bytes(m.uc.mem_read(worst + 0x28, 2)))[0] & ~0x1C00))
        for _ in range(3):
            m.call(0x2BF9A0, ecx=team, edx=self.count(m, team) - 1, budget=400_000_000)
        self.assertIn(worst, self.members(m, team))

    def test_a_release_that_removes_nobody_ends_the_cut(self):
        """Review D3: economy_release refuses a record past the 32 clubs, so the smart cut's `while (count > target)`
        on such a record would never end; a release that leaves the count where it was now ends the cut."""
        m, team = self.league(kicker="ok", size=53)
        pro = m.team_base + 500 * 49
        men = [m.get(m.team_base + 500 * c + 4 * i) for c in range(1, 21) for i in (3, 4)]
        for i, p in enumerate(men):
            m.put(pro + 4 * i, p)
        m.uc.mem_write(pro + 0x11C, bytes([len(men)]))
        m.call(0x2BF9A0, ecx=pro, edx=len(men) - 1, budget=50_000_000)
        self.assertEqual(self.members(m, pro), men)


IMAGES = {   # the combined panels' kept failure images (validator I5); economy sources = 6e37263e1's in both executables
    "buf": ("A", "76002/validator/FAIL-2029-st8-w14.b81mem.gz", 3),   # Panel A candidate 8f4bd09c
    "atl": ("A", "76002/validator/FAIL-2028-st8-w14.b81mem.gz", 14),
    "jax": ("A", "76001/validator/FAIL-2031-st9-w20.b81mem.gz", 16),
    "cle": ("B", "76005/validator/FAIL-2034-opening.b81mem.gz", 5),   # Panel B fullBtb 89c80a77: no punter at the opening
}
IMAGE_XBE_SHA256 = {"A": "8f4bd09cf852d2b50f6305328d93566261d57a75a16239063971094daabe251b",
                    "B": "89c80a77026b9c7332afc0c18052645a07631c60b675c643ec651c23ca1ad252"}
ENV = {"A": ("NFL2K5_B81_KP_IMAGES", "NFL2K5_B81_KP_IMAGE_XBE"), "B": ("NFL2K5_B81_KP_IMAGES_B", "NFL2K5_B81_KP_IMAGE_XBE_B")}


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class KeptImages(unittest.TestCase):
    """NFL2K5_B81_KP_IMAGES = the panel's candidate run folder (…/combined76/candidate, or the copy in b81-fixtures), NFL2K5_B81_KP_IMAGE_XBE = its
    executable (8f4bd09c). The images' economy is the integration head's; this build's economy windows and stage-9 entry
    are written over it (economy.sites(), the windows and the entry only) and the cover runs once for every computer club,
    as the upkeep calls it (stage 9's entry into it is Sites and Cover's test). On 6e37263e1 BUF and ATL get no kicker
    (room), JAX keeps its second punter, and CLE (Panel B, at the 2034 opening, stage 8 week 0) has no punter: there the
    pass shows the cover signs one on that roster; that it runs before week 1 is the stage-7 tests' and the panel's."""

    @classmethod
    def setUpClass(cls):
        cls.xbe, cls.paths = {}, {}
        for panel, (root_var, xbe_var) in ENV.items():
            root, xbe = os.environ.get(root_var), os.environ.get(xbe_var)
            if not root or not xbe or not Path(xbe).is_file():
                raise unittest.SkipTest(f"{root_var} / {xbe_var} are not set (kp-cover lane env)")
            cls.xbe[panel] = Path(xbe).read_bytes()
            if hashlib.sha256(cls.xbe[panel]).hexdigest() != IMAGE_XBE_SHA256[panel]:
                raise unittest.SkipTest(f"the kept images' executable differs ({xbe_var})")
            for k, (p, rel, _c) in IMAGES.items():
                if p == panel:
                    cls.paths[k] = Path(root) / rel
        if not all(p.is_file() for p in cls.paths.values()):
            raise unittest.SkipTest("a kept image is absent")

    def machine(self, key, *, new):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        m = Machine(self.xbe[IMAGES[key][0]], trace_writes=False)
        for lo, data in fi.load_memory(self.paths[key]).regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        if new:
            for site in economy.sites():
                if site.va in economy.WINDOWS or site.va == economy.STAGE9_SIM:
                    m.uc.mem_write(site.va, site.patched)
        m.uc.ctl_flush_tb()
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        return m

    @staticmethod
    def specialists(m, club):
        team = m.get(m.get(0xB72918) + 0x1C) + 500 * club
        out = {K: 0, P: 0}
        for i in range(m.uc.mem_read(team + 0x11C, 1)[0]):
            raw = bytes(m.uc.mem_read(m.get(team + 4 * i), 84))
            if raw[0x35] in out and not raw[0x23] & 0x80:
                out[raw[0x35]] += 1
        m.call(0xC3F00, ecx=team)
        return out[K], out[P], m.get(0xE3C278) - m.get(team + 0x124)

    def test_one_pass_gives_every_club_one_kicker_and_one_punter(self):
        for key, (_panel, _rel, club) in IMAGES.items():
            with self.subTest(image=key):
                old = self.machine(key, new=False)
                self.assertEqual(min(self.specialists(old, club)[:2]), 0)    # as the validator found it (I5: no K or P)
                m = self.machine(key, new=True)
                teams = m.get(m.get(0xB72918) + 0x1C)
                for c in range(32):                     # the upkeep's call, once for every computer club
                    team = teams + 500 * c
                    if not m.call(0x13EC30, ecx=team) or m.get(0xE6013C) == 1:
                        m.call(economy.SYMBOLS["economy_cover"], ecx=team, edx=m.ARENA + 0x1A0000, budget=2_000_000_000)
                for c in range(32):
                    k, p, room = self.specialists(m, c)
                    self.assertEqual((k, p), (1, 1), (key, c))
                    if c == club:                      # signed past the cap gate at a minimum: over by less than one
                        self.assertGreater(room, -600)


ROOT_76001_XBE_SHA256 = "7ae6f10af3dab8b73d98845d8776101eead135e376c9e9a9e16cb04cf0177c9f"   # kp-cover build a3dbd0774
ALIASES_76001 = [103, 1254, 1476, 1567, 1586, 2453]     # validator I2 + I6 at the 2026 week-20 check (kp-cover panel)
WAS, DANIELS = 25, 1567


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class Root76001(unittest.TestCase):
    """NFL2K5_B81_KP_76001 = the folder of root 76001's kept state (b81-fixtures/kp-cover-76001: the kp-cover build
    a3dbd0774's executable, the memory before the 2026 stage-9 week-19 advance, the 2026 week-20 validator image and the
    memory before the 2027 re-signing stage, where the run hung). The memory is the league as that build left it; this
    economy's windows and stage-9 entry are written over it for `new`."""

    @classmethod
    def setUpClass(cls):
        root = os.environ.get("NFL2K5_B81_KP_76001")
        if not root:
            raise unittest.SkipTest("NFL2K5_B81_KP_76001 is not set (kp-cover lane env)")
        cls.root = Path(root)
        names = ("default.xbe", "before-2026-st9-w19.b81mem.gz", "FAIL-2026-st9-w20.b81mem.gz", "before-2027-st2.b81mem.gz")
        if not all((cls.root / n).is_file() for n in names):
            raise unittest.SkipTest("a 76001 fixture file is absent")
        cls.xbe = (cls.root / "default.xbe").read_bytes()
        if hashlib.sha256(cls.xbe).hexdigest() != ROOT_76001_XBE_SHA256:
            raise unittest.SkipTest("the 76001 fixture's executable differs")

    def machine(self, *, new):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        m = Machine(self.xbe, trace_writes=False)
        self.regions = [(lo, len(data)) for lo, data in fi.load_memory(self.root / "before-2026-st9-w19.b81mem.gz").regions]
        for lo, data in fi.load_memory(self.root / "before-2026-st9-w19.b81mem.gz").regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        if new:
            for site in economy.sites():
                if site.va in economy.WINDOWS or site.va == economy.STAGE9_SIM:
                    m.uc.mem_write(site.va, site.patched)
        m.uc.ctl_flush_tb()
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        return m

    def report(self, m):
        """The validator (tools/franchise_invariants) over the machine's memory."""
        from tools import franchise_invariants as fi
        mem = fi.Regions((lo, bytes(m.uc.mem_read(lo, n))) for lo, n in self.regions if lo < 0x3000000)
        return fi.check(fi.view_from_memory(mem.read, search=lambda n: mem.find(n, 0x10000, 0x2000000)))

    @staticmethod
    def index(m, p):
        return (p - m.get(m.get(0xB72918) + 4)) // 0x54

    def roster(self, m, t):
        team = m.call(0xC4C50, ecx=t)
        return [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]

    @staticmethod
    def free(m):
        lst = m.get(0xB72918) + 0x38
        return [m.call(0x242500, ecx=lst, edx=i) for i in range(m.call(0x2424F0, ecx=lst))]

    def test_the_validator_names_a_man_both_on_a_roster_and_in_free_agency(self):
        """I2 counts the free-agent list as a holder: the run's own week-20 check and the 2027 re-signing stage's memory
        (Jefferson by then too, Bawden no longer listed) name each such man with his club and the free list."""
        from tools import franchise_invariants as fi
        for name, want in (("FAIL-2026-st9-w20.b81mem.gz", ALIASES_76001), ("before-2027-st2.b81mem.gz", [103, 841, 1254, 1476, 1567, 1586])):
            with self.subTest(image=name):
                mem = fi.load_memory(self.root / name)
                view = fi.view_from_memory(mem.read, search=lambda n: mem.find(n, 0x10000, 0x2000000))
                rows = {v["player_index"]: v["values"]["holders"] for v in fi.check(view).violations if v["invariant"] == "I2"}
                self.assertEqual(sorted(rows), want)
                for i, holders in rows.items():
                    self.assertEqual([h["list"] for h in holders], ["active", "free"], i)
                self.assertEqual(rows[DANIELS], [{"list": "active", "club": WAS}, {"list": "free", "club": None}])

    def test_the_playoff_cover_leaves_the_pro_bowl_rosters_alone(self):
        """Before the week-19 advance n_teams() reads 34. The build's own stage-9 cover (a3dbd0774) released six Pro Bowl
        players from a Pro Bowl roster with no healthy K or P: each stayed on his club's list and on the Pro Bowl list and
        went to free agency with no contract (I2, I6). This one leaves both Pro Bowl rosters as they are."""
        for new in (False, True):
            with self.subTest(new=new):
                m = self.machine(new=new)
                self.assertEqual(m.get(0xE576AC), 34)
                pro = [self.roster(m, t) for t in (32, 33)]
                self.assertEqual([len(r) for r in pro], [40, 40])
                m.call(economy.SYMBOLS["economy_cover_all"], ecx=m.ARENA + 0x1A0000, budget=3_000_000_000)
                rostered = {self.index(m, p) for t in range(32) for p in self.roster(m, t)}
                aliased = sorted(rostered & {self.index(m, p) for p in self.free(m)})
                failing = {v["invariant"] for v in self.report(m).violations if v["severity"] == "failure"}
                if not new:
                    self.assertEqual((aliased, sorted(failing & {"I2", "I6"})), (ALIASES_76001, ["I2", "I6"]))
                    continue
                self.assertEqual([self.roster(m, t) for t in (32, 33)], pro)
                self.assertEqual((aliased, failing & {"I2", "I6"}), ([], set()))

    @staticmethod
    def rating(m, p):
        return CoverMachine.rating(m, p)

    def test_a_kp_free_agents_price_ignores_the_pro_bowl_sides(self):
        """Coordinator 11/27: every economy walk that prices or counts clubs uses the 32 league clubs (0xC6430, 32 in
        franchise mode), never the Pro Bowl records. At this state (stage 9, n_teams() 34) the a3dbd0774 economy priced
        through rank_twice over 34 records, so the two Pro Bowl kickers counted twice for every K rated below them. The
        subject: the best healthy kicker rated below both Pro Bowl kickers, released to free agency; the cap is raised
        eightfold so his in-season ask (a quarter of his price) sits above his floor and shows the price. His price is
        the same with the Pro Bowl lists emptied, and so is every rostered K's and P's (24 of them moved on a3dbd0774)."""
        value = economy.SYMBOLS["economy_value"]
        for new in (False, True):
            got = {}
            for empty in (False, True):
                m = self.machine(new=new)
                pro = {p for t in (32, 33) for p in self.roster(m, t)}
                kickers = [(t, p) for t in range(32) for p in self.roster(m, t)
                           if m.uc.mem_read(p + 0x35, 1)[0] == K and p not in pro and not m.uc.mem_read(p + 0x23, 1)[0] & 0x80]
                line = min(self.rating(m, p) for p in pro if m.uc.mem_read(p + 0x35, 1)[0] == K)
                club, him = max(((t, p) for t, p in kickers if self.rating(m, p) < line), key=lambda tp: self.rating(m, tp[1]))
                specialists = [p for t in range(32) for p in self.roster(m, t) if m.uc.mem_read(p + 0x35, 1)[0] in (K, P) and p != him]
                m.call(0x2BD900, ecx=m.call(0xC4C50, ecx=club), edx=him, args=(1, 1), budget=200_000_000)
                self.assertIn(him, self.free(m))
                m.put(0xE3C278, 8 * m.get(0xE3C278))
                if empty:
                    for t in (32, 33):
                        m.uc.mem_write(m.call(0xC4C50, ecx=t) + 0x11C, bytes([0]))
                price = lambda p: m.call(value, ecx=p, edx=0, args=(0, 1, 0), budget=200_000_000)
                got[empty] = (self.index(m, him), price(him), [price(p) for p in specialists])
            (who, with_pb, rostered_pb), (_, without, rostered) = got[False], got[True]
            if not new:
                self.assertLess(with_pb, without, who)
                self.assertGreater(sum(a != b for a, b in zip(rostered_pb, rostered)), 0)
                continue
            self.assertEqual((with_pb, rostered_pb), (without, rostered), who)

    def test_a_full_club_releases_one_non_starter_and_signs_over_the_cap(self):
        """The first club of 53 at this state, its kicker hurt (still on the list, so the roster is full), its best QB hurt
        at depth row 0, 1,500 over the cap: exactly one release, kp_pick's (the lowest healthy rating among men at depth
        row >= KP_KEEP; never a QB, K or P), the hurt QB stays, a kicker signs past the cap gate on a one-year minimum
        deal, the count stays 53 and the club ends over the cap by that minimum more."""
        m = self.machine(new=True)
        club = next(t for t in range(32) if len(self.roster(m, t)) == 53
                    and [p for p in self.roster(m, t) if m.uc.mem_read(p + 0x35, 1)[0] == K])
        team = m.call(0xC4C50, ecx=club)
        hurt = lambda p: m.put(p + 0x20, (m.get(p + 0x20) & 0x003FFFFF) | 0x80000000 | (2 << 22))
        for k in [p for p in self.roster(m, club) if m.uc.mem_read(p + 0x35, 1)[0] == K]:
            hurt(k)
        qb = max((p for p in self.roster(m, club) if m.uc.mem_read(p + 0x35, 1)[0] == 0), key=lambda p: self.rating(m, p))
        hurt(qb)
        m.uc.mem_write(qb + 0x28, struct.pack("<H", struct.unpack("<H", bytes(m.uc.mem_read(qb + 0x28, 2)))[0] & ~0x1C00))
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) - 1500)
        before, payroll = self.roster(m, club), m.get(team + 0x124)
        eligible = [p for p in before if m.uc.mem_read(p + 0x35, 1)[0] < 17
                    and (struct.unpack("<H", bytes(m.uc.mem_read(p + 0x28, 2)))[0] >> 10 & 7) >= KP_KEEP[m.uc.mem_read(p + 0x35, 1)[0]]]
        bits = {p: struct.unpack("<I", struct.pack("<f", self.rating(m, p)))[0] for p in eligible}
        want = min(eligible, key=lambda p: (bits[p], before.index(p)))
        m.call(economy.SYMBOLS["economy_cover"], ecx=team, edx=m.ARENA + 0x1A0000, budget=2_000_000_000)
        after = self.roster(m, club)
        released, signed = [p for p in before if p not in after], [p for p in after if p not in before]
        self.assertEqual(released, [want])
        self.assertNotIn(m.uc.mem_read(want + 0x35, 1)[0], (0, K, P))
        self.assertEqual(([m.uc.mem_read(p + 0x35, 1)[0] for p in signed], len(after)), ([K], 53))
        self.assertIn(qb, after)
        new = bytes(m.uc.mem_read(signed[0], 0x54))
        self.assertEqual((new[0x24] & 15, new[0x27] & 15, new[0x26]), (1, 1, 2))
        self.assertEqual(struct.unpack_from("<H", new, 10)[0], Cover.minimum_value(m, signed[0]))
        m.call(0xC3F00, ecx=team)
        self.assertLess(m.get(team + 0x124) - payroll, 600)
        self.assertGreater(m.get(team + 0x124), m.get(0xE3C278), "over the cap: the lesser evil beside no kicker")

if __name__ == "__main__":
    unittest.main()
