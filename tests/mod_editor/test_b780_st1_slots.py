"""b780 st1: the specialist bytes in the line-up builder, the weekly exchange sort and the Pro Bowl skip.

All three live in the returner fix (on in every preset), in its two 128-byte in-place sites:

* Q91, the line-up builder 0xE7C50 (game setup 0x6476A -> 0xE80D0, availability flag 0): retail checks the KR1/KR2/PR
  bytes only for -1; a byte at or past the player count read a vacated (NULL) slot and faulted in 0xE7900 (the game froze
  setting up the game). The KR1 load at 0xE7CC5 now calls a slot check that turns such a byte into -1.
* Q34, the weekly exchange store 0xC3D70: the weekly sort swaps two players with two stores and retail cleared every
  specialist byte pointing at either slot, so the long snapper, the holder and the kicker bytes were lost whenever their
  slot moved. Each byte now follows its player; a real replacement keeps the retail clear.
* Q32 (HUNT6's finding), the Pro Bowl teams in league slots 32/33 during the postseason: the weekly auto-depth sorted
  them and moved their members on their own clubs. The loop head's call 0x2BDD1B now goes to an all-star skip in the
  exchange site, so Basic and Advanced (no depth locks) skip them as depth locks revision 5 does; with depth locks the
  returner fix's call is kept and depth locks' own skip stays for builds without the returner fix.

The game's own code under Unicorn on the retail executable, the released v0.8 one and the v0.9 RC (when configured).
"""
from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "mod_editor"))
from mod_editor.core import nfl2k5_depth_locks as locks  # noqa: E402
from mod_editor.core import nfl2k5_returner_fix as returner  # noqa: E402
import test_nfl2k5_returner_slot_guard as guard  # noqa: E402

RETAIL = guard.RETAIL
RELEASED = guard.RELEASED
CTX = guard.OBJ                 # the 0x334-byte line-up context
H, KR1, KR2, K, LS, PR = range(6)


def _released():
    for name, path in RELEASED.items():
        data = guard._read(path)
        if data is not None:
            yield name, data


@unittest.skipUnless(guard.HAVE_UC, "Unicorn is absent; native x86 proofs require it")
@unittest.skipUnless(RETAIL.is_file(), "the retail default.xbe is not configured (NFL2K5_RETAIL_XBE)")
class LineupSlotCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        # (the executable before, the same executable with the returner fix installed or upgraded in place)
        cls.images = {"retail + fix": (cls.retail, returner.apply(cls.retail)[0])}
        for name, data in _released():
            cls.images[name + " upgraded"] = (data, returner.apply(data)[0])

    @staticmethod
    def lineup(image, specials, vacate=12):
        m = guard._Machine(image, guard.PS_TAIL, bytes(specials))
        m.uc.mem_write(m.team + vacate * 4, b"\0" * 4)         # a vacated slot reads NULL
        result = m.call(0xE80D0, {guard.UC_X86_REG_ECX: m.team, guard.UC_X86_REG_EDX: CTX}, (0, 0))
        return result, bytes(m.uc.mem_read(CTX, 0x334))

    def test_a_returner_byte_past_the_roster_no_longer_faults(self):
        for role in (KR1, KR2, PR):
            specials = bytearray([0, 2, 3, 9, 1, 3])
            specials[role] = 12                                  # past the count (10), its slot vacated
            empty = bytearray(specials)
            empty[role] = 0xFF
            for name, (before, image) in self.images.items():
                with self.subTest(image=name, role=role):
                    self.assertEqual(self.lineup(before, specials)[0], ("fault", 0x24))   # the freeze
                    result, ctx = self.lineup(image, specials)
                    self.assertEqual(result[0], "returned")
                    self.assertEqual(ctx, self.lineup(image, empty)[1])          # exactly an empty byte,
                    self.assertEqual(ctx, self.lineup(before, empty)[1])         # which the game already handles

    def test_valid_bytes_build_the_same_line_up_as_retail(self):
        configs = ([0, 2, 3, 9, 1, 3], [0, 4, 4, 9, 1, 2], [1, 8, 2, 9, 0, 8], [0, 0xFF, 0xFF, 9, 1, 0xFF], [0, 7, 5, 9, 1, 6])
        for specials in configs:
            for name, (before, image) in self.images.items():
                with self.subTest(image=name, specials=specials):
                    want = self.lineup(before, specials)
                    self.assertEqual(want[0][0], "returned")
                    self.assertEqual(self.lineup(image, specials), want)


@unittest.skipUnless(guard.HAVE_UC, "Unicorn is absent; native x86 proofs require it")
@unittest.skipUnless(RETAIL.is_file(), "the retail default.xbe is not configured (NFL2K5_RETAIL_XBE)")
class ExchangeStoreTests(unittest.TestCase):
    """0xC3D70 called the way the weekly sort calls it: store(j, P_i) then store(i, P_j)."""

    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        cls.images = {"retail + fix": returner.apply(cls.retail)[0]}
        for name, data in _released():
            cls.images[name + " upgraded"] = returner.apply(data)[0]

    @staticmethod
    def store(m, slot, player):
        return m.call(returner.EXCHANGE_VA, {guard.UC_X86_REG_ECX: m.team, guard.UC_X86_REG_EDX: player}, (slot,))

    def swap(self, image, specials, i, j):
        m = guard._Machine(image, guard.PS_TAIL, bytes(specials))
        p_i, p_j = m.players[(1, i)], m.players[(1, j)]
        self.assertEqual(self.store(m, j, p_i)[0], "returned")
        self.assertEqual(self.store(m, i, p_j)[0], "returned")
        slots = [struct.unpack("<I", m.uc.mem_read(m.team + 4 * s, 4))[0] for s in range(10)]
        return m.specials(), slots, m

    def test_a_swap_keeps_every_specialist_byte_on_its_player(self):
        i, j = 2, 5
        cases = ([i, j, 7, i, j, 0xFF], [j, i, i, j, 0, j], [0, 1, 3, 9, 4, 8], [i, i, i, j, j, j])
        follow = {i: j, j: i}
        for specials in cases:
            old, slots_old, _ = self.swap(self.retail, specials, i, j)
            self.assertEqual(old, [0xFF if b in (i, j) else b for b in specials])     # retail: cleared
            for name, image in self.images.items():
                with self.subTest(image=name, specials=specials):
                    new, slots, m = self.swap(image, specials, i, j)
                    self.assertEqual(slots, slots_old)                                # the same swap
                    self.assertEqual(new, [follow.get(b, b) for b in specials])
                    for role, byte in enumerate(specials):                            # each byte, same player
                        if byte < 10:
                            self.assertEqual(slots[new[role]], m.players[(1, byte)], role)

    def test_a_real_replacement_clears_like_retail(self):
        specials = [0, 2, 4, 9, 4, 2]
        for name, image in self.images.items():
            with self.subTest(image=name):
                old = guard._Machine(self.retail, guard.PS_TAIL, bytes(specials))
                self.store(old, 4, old.players[(0, 5)])                              # another club's player
                want = old.specials()
                new = guard._Machine(image, guard.PS_TAIL, bytes(specials))
                self.store(new, 4, new.players[(0, 5)])
                self.assertEqual(new.specials(), want)
                self.assertEqual(want, [0, 2, 0xFF, 9, 0xFF, 2])

    def test_storing_the_same_player_again_changes_nothing(self):
        specials = [0, 2, 4, 9, 4, 2]
        for name, image in self.images.items():
            with self.subTest(image=name):
                m = guard._Machine(image, guard.PS_TAIL, bytes(specials))
                self.store(m, 4, m.players[(1, 4)])
                self.assertEqual(m.specials(), specials)


def _cpu_harness():
    from test_nfl2k5_depth_locks import CPU, record, fields, TEAM, PLAYERS
    return CPU, record, fields, TEAM, PLAYERS


@unittest.skipUnless(guard.HAVE_UC, "Unicorn is absent; native x86 proofs require it")
@unittest.skipUnless(RETAIL.is_file(), "the retail default.xbe is not configured (NFL2K5_RETAIL_XBE)")
class WeeklyPassTests(unittest.TestCase):
    """The real weekly auto-depth 0x2BDCF0 (the depth-locks harness: team count, team lookup and user test stubbed) on
    the four owner combinations and on the released executables upgraded in place."""

    @classmethod
    def setUpClass(cls):
        CPU, record, fields, cls.TEAM, cls.PLAYERS = _cpu_harness()
        cls.CPU, cls.record, cls.fields = CPU, staticmethod(record), staticmethod(fields)
        retail = RETAIL.read_bytes()
        cls.neither = retail
        # (the harness maps the executable's first 16 MB, so the released images with their high allocator sections
        # are proved by bytes in UpgradeTests: their sites equal these)
        cls.fixed = {"returner fix": returner.apply(retail)[0], "depth locks": locks.apply(retail)[0],
                     "both": locks.apply(returner.apply(retail)[0])[0],
                     "both, depth locks first": returner.apply(locks.apply(retail)[0])[0]}

    def _league(self, data, kind=1):
        """HUNT6's league: a club (QB A .80 rank 0, QB B .60 rank 1) and a second team of ``kind`` holding QB X (.95)
        and the same QB A, the shape of a Pro Bowl team."""
        r, T, P = self.record, self.TEAM, self.PLAYERS
        cpu = self.CPU(data)
        players = [r(position=0, rank=0, side=1, bits=3, score=.80), r(position=0, rank=1, side=0, bits=3, score=.60),
                   r(position=0, rank=0, side=2, bits=3, score=.95)]
        cpu.seed(players, order=[0, 1])
        second = bytearray(500)
        for i, index in enumerate((2, 0)):
            struct.pack_into("<I", second, 4 * i, P + 84 * index)
        second[0x11C] = 2
        second[0x194:0x19A] = b"\xff" * 6
        struct.pack_into("<I", second, 0x128, kind)
        cpu.uc.mem_write(T + 500, bytes(second))
        cpu.teams = [T, T + 500]
        return cpu

    def test_the_pro_bowl_team_is_skipped_by_every_fixed_combination(self):
        cpu = self._league(self.neither)
        cpu.run(0x2BDCF0)
        self.assertEqual((self.fields(cpu.player(0))[0], self.fields(cpu.player(1))[0]), (1, 1))   # retail: the bug
        for name, image in self.fixed.items():
            with self.subTest(image=name):
                cpu = self._league(image)
                before = bytes(cpu.uc.mem_read(self.TEAM + 500, 500))
                cpu.run(0x2BDCF0)
                self.assertEqual([self.fields(cpu.player(i))[:2] for i in range(2)], [(0, 1), (1, 0)])
                self.assertEqual(bytes(cpu.uc.mem_read(self.TEAM + 500, 500)), before)

    def test_clubs_and_created_teams_are_still_sorted(self):
        for name, image in self.fixed.items():
            for kind in (0, 2):
                with self.subTest(image=name, kind=kind):
                    cpu = self._league(image, kind=kind)
                    cpu.run(0x2BDCF0)
                    self.assertEqual(self.fields(cpu.player(0))[0], 1)

    def test_the_weekly_sort_keeps_the_snapper_holder_and_kicker(self):  # noqa: C901
        """Slots 0..5: C .5, C .9, QB .5, QB .9, K .5, K .9; the lesser of each pair holds the role. The sort swaps
        each pair (better first)."""
        r = self.record
        players = [r(position=12, rank=1, score=.5), r(position=12, rank=0, score=.9), r(position=0, rank=1, score=.5),
                   r(position=0, rank=0, score=.9), r(position=1, rank=1, score=.5), r(position=1, rank=0, score=.9)]

        def run(image):
            cpu = self.CPU(image)
            cpu.seed(players)
            cpu.uc.mem_write(self.TEAM + 0x194, bytes([2]))       # holder: the lesser QB
            cpu.uc.mem_write(self.TEAM + 0x197, bytes([4, 0]))    # kicker: the lesser K; long snapper: the lesser C
            cpu.run(0x2BDCF0)
            slots = [struct.unpack("<I", cpu.uc.mem_read(self.TEAM + 4 * s, 4))[0] for s in range(6)]
            team = bytes(cpu.uc.mem_read(self.TEAM + 0x194, 6))
            return slots, team[H], team[K], team[LS]

        slots, holder, kicker, snapper = run(self.neither)
        self.assertEqual(slots, [self.PLAYERS + 84 * i for i in (1, 0, 3, 2, 5, 4)])   # each pair swapped
        self.assertEqual((holder, kicker, snapper), (0xFF, 0xFF, 0xFF))                  # retail: all three lost
        for name, image in self.fixed.items():
            with self.subTest(image=name):
                slots, holder, kicker, snapper = run(image)
                self.assertEqual(slots, [self.PLAYERS + 84 * i for i in (1, 0, 3, 2, 5, 4)])
                if name == "depth locks":                        # no returner fix: the retail store
                    self.assertEqual((holder, kicker, snapper), (0xFF, 0xFF, 0xFF))
                    continue
                self.assertEqual((slots[holder], slots[kicker], slots[snapper]),
                                 (self.PLAYERS + 84 * 2, self.PLAYERS + 84 * 4, self.PLAYERS + 84 * 0))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(RETAIL.is_file(), "the retail default.xbe is not configured (NFL2K5_RETAIL_XBE)")
class UpgradeTests(unittest.TestCase):
    """The released v0.8 and v0.9 RC executables upgrade in place to exactly the sites a fresh install writes, with
    depth locks before or after, and keep every other byte."""

    def test_released_executables_carry_the_fresh_sites_after_the_upgrade(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        fresh = XbeImage(locks.apply(returner.apply(RETAIL.read_bytes())[0])[0])
        sites = ((returner.GETTER_VA, returner.GETTER_SIZE), (returner.LINEUP_HOOK_VA, 7),
                 (returner.EXCHANGE_VA, returner.EXCHANGE_SIZE), (returner.ALL_STAR_CALL_VA, 5),
                 (returner.SITE_VA, returner.SITE_SIZE), (locks.ALL_STAR_SKIP_VA, len(locks.ALL_STAR_SKIP)))
        seen = 0
        for name, data in _released():
            seen += 1
            self.assertEqual((returner.status(data), locks.status(data)), ("legacy", "legacy"), name)
            for order in ("returner fix first", "depth locks first"):
                with self.subTest(release=name, order=order):
                    up = (locks.apply(returner.apply(data)[0])[0] if order == "returner fix first"
                          else returner.apply(locks.apply(data)[0])[0])
                    self.assertEqual((returner.status(up), locks.status(up)), ("applied", "applied"))
                    image = XbeImage(up)
                    for va, size in sites:       # either order: the returner fix owns the loop head's call
                        self.assertEqual(image.read(va, size), fresh.read(va, size), hex(va))
        if not seen:
            self.skipTest("no released executable configured (NFL2K5_V08_XBE, NFL2K5_B780_RC_XBE)")
