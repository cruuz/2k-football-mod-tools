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
KP_WINDOWS = (0x28C2F0, 0x2DCC10, 0x2F7D00)


class Sites(unittest.TestCase):
    def test_stage_nine_enters_the_cover_then_its_own_path(self):
        retail = retail_bytes()
        before = struct.unpack("<9I", XbeImage(retail).read(TABLE, 36))
        self.assertEqual(before[8], STAGE9_PATH)
        applied = XbeImage(economy.apply(retail)[0])
        after = struct.unpack("<9I", applied.read(TABLE, 36))
        stub = economy.SYMBOLS["economy_stage9"]
        self.assertEqual(after[8], stub)
        self.assertEqual(after[5], economy.SYMBOLS["economy_stage6"])
        self.assertEqual(after[:5] + after[6:8], before[:5] + before[6:8])
        code = applied.read(stub, 12)                 # mov ecx, ebp; call economy_cover_all; jmp 0x247E6E
        self.assertEqual(code[:2], bytes.fromhex("89e9"))
        self.assertEqual((code[2], code[7]), (0xE8, 0xE9))
        self.assertEqual(stub + 7 + struct.unpack_from("<i", code, 3)[0], economy.SYMBOLS["economy_cover_all"])
        self.assertEqual(stub + 12 + struct.unpack_from("<i", code, 8)[0], STAGE9_PATH)
        site = next(s for s in economy.sites() if s.va == economy.STAGE9_CASE)
        self.assertEqual(hashlib.sha256(struct.pack("<I", STAGE9_PATH)).hexdigest(), site.digest)
        self.assertIn(economy.STAGE9_CASE, economy.REVISION_10_NEW)

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


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class Cover(unittest.TestCase):
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

    def test_short_of_room_the_club_releases_by_value_lost_and_signs_a_kicker(self):
        m, team = self.league(room=100)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["signed_pos"]), (1, [K]))
        self.assertTrue(got["released"], "a release made the room")
        self.assertTrue(all(pos not in (0, K, P) for pos in got["released_pos"]), got["released_pos"])
        self.assertGreaterEqual(got["room"], 0, "the signing stays inside the cap")

    def test_with_room_it_signs_and_releases_nobody(self):
        m, team = self.league(room=40000)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["signed_pos"], got["released"]), (1, [K], []))

    def test_at_53_the_smart_cut_still_makes_the_place(self):
        m, team = self.league(size=54, room=40000)          # 53 once the kicker is off the list
        self.assertEqual(self.count(m, team), 53)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["count"]), (1, 53))

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

    def test_after_the_gate_cut_a_club_of_53_opens_with_a_kicker(self):
        m, team = self.league(size=54, stage=7, room=40000)
        got = self.cover(m, team)
        self.assertEqual((len(got["healthy_k"]), got["count"], len(got["released"])), (1, 53, 1))

    def test_the_preseason_upkeep_runs_the_cover(self):
        """economy_week in stage 7 (the preseason's weekly pass; the same upkeep runs after the stage's gate cut), fills
        off: the club with no kicker has one after it."""
        m, team = self.league(size=54, stage=7, room=40000)
        zero = struct.unpack("<I", struct.pack("<f", 0.0))[0]
        m.call(economy.SYMBOLS["economy_week"], ecx=m.ARENA + 0x1A0000, edx=0, args=(zero, zero), budget=2_000_000_000)
        self.assertEqual(len([p for p in self.at(m, team, K) if not self.hurt(m, p)]), 1)

    def test_stage_nine_runs_the_cover_for_every_computer_club_then_the_playoff_path(self):
        m, team = self.league(stage=9, room=40000)
        menu = m.ARENA + 0x1A0000
        regs = dict(EBX=1, ESI=0x5151, EDI=0x6262, EBP=menu)
        for name, value in dict(ECX=0, EDX=0, EAX=0, ESP=m.STACK, EFLAGS=0x202, **regs).items():
            m.reg(name, value)
        m.uc.mem_write(m.STACK, struct.pack("<I", m.STOP))
        m.uc.emu_start(economy.SYMBOLS["economy_stage9"], STAGE9_PATH, count=2_000_000_000)
        self.assertEqual(m.reg("EIP"), STAGE9_PATH)
        self.assertEqual({k: m.reg(k) for k in regs}, regs)
        self.assertEqual(m.reg("ESP"), m.STACK)
        self.assertEqual(len([p for p in self.at(m, team, K) if not self.hurt(m, p)]), 1)
        for c in range(32):
            t = m.team_base + 500 * c
            for pos in (K, P):
                self.assertEqual(len([p for p in self.at(m, t, pos) if not self.hurt(m, p)]), 1, (c, pos))


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
    """NFL2K5_B81_KP_IMAGES = the panel's candidate run folder (…/combined76/candidate), NFL2K5_B81_KP_IMAGE_XBE = its
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
                if site.va in economy.WINDOWS or site.va == getattr(economy, "STAGE9_CASE", None):
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
                    if c == club:
                        self.assertGreaterEqual(room, 0)


if __name__ == "__main__":
    unittest.main()
