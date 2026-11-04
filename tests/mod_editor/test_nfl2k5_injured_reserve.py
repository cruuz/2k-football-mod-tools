"""b780 IR1: modern franchise injured reserve and the Pro Bowl IR guard (Q66).

Static: the owner's sites, the guard bytes (HUNT6's 34-byte rewrite), status / apply / idempotence, the presets, the
memory model (0 bytes of room on Advanced and Experimental, forced off at 64 MB), the save extension's codec.
Unicorn (the game's own code: the retail executable with the owner, the retail roster, the franchise start 0x13EE10):
the CPU's weekly pass (placement of a long injury, the 4-game minimum counted from played grid cells, the return,
the 9th return refused), the IR payroll in 0xC3F00, the user's IR button 0x247070 (place, refuse, activate), the
rollover 0x246F90, the franchise start's roster injuries, the front office writer 0x2D0790 and loader 0x2D0CE0
(round trip, a legacy block migrating, the retail loader on a modern block), and the Pro Bowl clubs (Q66)."""

from __future__ import annotations

import shutil
import struct
import subprocess
import unittest

from mod_editor.core import mod_build
from mod_editor.core import nfl2k5_injured_reserve as ir
from mod_editor.core import nfl2k5_injured_reserve_save as irsave
from mod_editor.core import nfl2k5_memory_budget as budget
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import Machine, retail_bytes

try:
    import unicorn  # noqa: F401
    HAVE_UC = True
except ImportError:
    HAVE_UC = False

STORE_HEAD = 64
CLUB_STRIDE = 164
OFFICE = 0x165B0


class StaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        if cls.retail is None:
            raise unittest.SkipTest("private USA retail XBE is absent")

    def test_every_site_is_retail_in_the_retail_executable(self):
        image = XbeImage(self.retail)
        self.assertEqual(image.read(ir.GUARD_VA, len(ir.GUARD_RETAIL)), ir.GUARD_RETAIL)
        for _label, va, before, patched in ir.sites(0x1000000):
            self.assertEqual(image.read(va, len(before)), before, hex(va))
            self.assertEqual(len(before), len(patched))
        self.assertEqual(ir.status(self.retail), "retail")

    def test_the_guard_is_hunt6s_rewrite_and_changes_only_that_head(self):
        guarded, receipt = ir.apply(self.retail, "guard")
        self.assertEqual(ir.status(guarded), "guard")
        self.assertEqual(ir.GUARD.hex(), "56578bf28bf98bcee8a3dce7ff3c20730c6bc81483b9f021e4000074055f33c05ec3")
        image = XbeImage(guarded)
        self.assertEqual(image.read(ir.GUARD_VA, len(ir.GUARD)), ir.GUARD)
        off = XbeImage(self.retail).offset(ir.GUARD_VA, len(ir.GUARD))
        changed = [i for i, (a, b) in enumerate(zip(self.retail, guarded)) if a != b]
        inside = [i for i in changed if off <= i < off + len(ir.GUARD)]
        self.assertEqual(len(inside), receipt["changed_bytes"] - (len(changed) - len(inside)))
        self.assertTrue(all(i < 0x1000 or off <= i < off + len(ir.GUARD) for i in changed))   # + the section digest
        again, second = ir.apply(guarded, "guard")
        self.assertEqual((again, second["status"]), (guarded, "already_applied"))

    def test_modern_install_status_idempotence_and_upgrade_from_the_guard(self):
        modern, receipt = ir.apply(self.retail, "modern")
        self.assertEqual(ir.status(modern), "applied")
        self.assertEqual(receipt["status"], "applied")
        again, second = ir.apply(modern, "modern")
        self.assertEqual((again, second["status"]), (modern, "already_applied"))
        guarded, _ = ir.apply(self.retail, "guard")
        upgraded, _ = ir.apply(guarded, "modern")
        self.assertEqual(ir.status(upgraded), "applied")
        self.assertEqual(upgraded, modern)
        kept, third = ir.apply(modern, "guard")                            # the guard is part of the modern install
        self.assertEqual((kept, third["status"], ir.status(kept)), (modern, "already_applied", "applied"))
        image = XbeImage(modern)
        head = image.read(ir.GUARD_VA, len(ir.GUARD))
        self.assertEqual((head[0], head[5:]), (0xE9, b"\x90" + ir.GUARD[6:]))   # the guard stays under the hook

    def test_an_allocation_the_build_reserved_first_is_not_an_install(self):
        """rehearsal1: the build's first space pass reserves this owner's allocation (0xCC code) before its step."""
        from mod_editor.core import nfl2k5_xbe_space as space
        reserved, _ = space.apply(self.retail, ir.REQUESTS, scaleout=True)
        self.assertEqual(ir.status(reserved), "retail")
        modern, _ = ir.apply(reserved, "modern")
        self.assertEqual(ir.status(modern), "applied")
        self.assertEqual(ir.allocations(modern)["code"]["va"], ir.allocations(reserved)["code"]["va"])
        guarded, _ = ir.apply(reserved, "guard")
        self.assertEqual(ir.status(guarded), "guard")
        self.assertEqual(ir.status(ir.apply(guarded, "modern")[0]), "applied")

    def test_runtime_template_is_reproducible(self):
        if shutil.which("gcc") is None or shutil.which("ld") is None:
            self.skipTest("gcc/binutils are not installed")
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        out = subprocess.run(["python3", str(root / "tools/nfl2k5_injured_reserve_build.py"), "--check"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


class PresetAndMemoryTests(unittest.TestCase):
    def test_presets(self):
        for name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
            self.assertTrue(mod_build.PRESETS[name]["injured_reserve_guard"], name)
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["modern_injured_reserve"])
        self.assertTrue(mod_build.PRESETS["softdrink_advanced"]["modern_injured_reserve"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["modern_injured_reserve"])

    def test_cost_at_128_and_forced_off_at_64(self):
        self.assertIn("modern_injured_reserve", budget.REQUIRES_128)
        self.assertEqual(budget.OWNER_BYTES["injured_reserve"], (ir.CODE_SIZE, 0, 0, 0, ir.STORE_SIZE))
        for preset in ("softdrink_advanced", "softdrink_experimental"):
            on = budget.predict({"preset": preset, "overrides": {"modern_injured_reserve": True}}, 128)
            off = budget.predict({"preset": preset, "overrides": {"modern_injured_reserve": False}}, 128)
            self.assertEqual(on["room"], off["room"], preset)     # inside the scale-out pages the preset already has
            low = budget.predict({"preset": preset, "overrides": {"modern_injured_reserve": True}}, 64)
            self.assertIn("modern_injured_reserve", low["forced_off"])


class CodecTests(unittest.TestCase):
    def clubs(self):
        clubs = [[] for _ in range(32)]
        clubs[3] = [(100 + i, min(i, 7), i == 19) for i in range(20)]
        clubs[7] = [(900, 4, False), (901, 0, True)]
        clubs[31] = [(2000 + i, 2, False) for i in range(9)]
        return clubs

    def test_round_trip(self):
        returns = [0] * 32
        returns[3], returns[7] = 8, 2
        block = irsave.encode(self.clubs(), returns, extension=True)
        extension, got_returns, got = irsave.decode(block)
        self.assertTrue(extension)
        self.assertEqual(got_returns, returns)
        self.assertEqual(got, self.clubs())
        low = [struct.unpack_from("<H", block, 4 * k)[0] for k in range(160)]
        self.assertEqual(low[15:20], [100, 101, 102, 103, 104])           # an older build's five
        self.assertEqual(low[35:40], [900, 901, 0xFFFF, 0xFFFF, 0xFFFF])

    def test_a_legacy_block_and_a_damaged_extension_read_as_legacy(self):
        clubs = [[] for _ in range(32)]
        clubs[0] = [(5, 0, False), (6, 0, False)]
        legacy = irsave.encode(clubs, [0] * 32, extension=False)
        self.assertEqual(legacy[2:4], b"\0\0")
        extension, _r, got = irsave.decode(legacy)
        self.assertFalse(extension)
        self.assertEqual(got[0], [(5, 0, False), (6, 0, False)])
        block = bytearray(irsave.encode(self.clubs(), [0] * 32, extension=True))
        struct.pack_into("<I", block, 4 * 40, 77)                         # another tool's 5-slot write
        extension, _r, got = irsave.decode(bytes(block))
        self.assertFalse(extension)
        self.assertEqual(got[8][0][0], 77)

    def test_capacity(self):
        clubs = [[(i * 50 + j, 0, False) for j in range(9)] for i in range(32)]   # 4 extended a club = 128 > 102
        with self.assertRaises(irsave.InjuredReserveError):
            irsave.encode(clubs, [0] * 32, extension=True)
        clubs = [[] for _ in range(32)]
        clubs[0] = [(j, 0, False) for j in range(21)]
        with self.assertRaises(irsave.InjuredReserveError):
            irsave.encode(clubs, [0] * 32, extension=True)
        clubs[0] = clubs[0][:6]
        with self.assertRaises(irsave.InjuredReserveError):
            irsave.encode(clubs, [0] * 32, extension=False)

    def test_long_injury_words(self):
        w20, w24 = irsave.long_injury_words(0x12345, 0x0000000F, 12)
        self.assertTrue(irsave.starts_on_ir(w20))
        self.assertEqual(((w20 >> 22) & 0xFF, w20 & 0x3FFFFF, w24), (12, 0x12345, 0x4000000F))
        self.assertFalse(irsave.starts_on_ir(irsave.long_injury_words(0, 0, 4)[0] & ~(0xFF << 22) | (3 << 22)))


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class GameTests(unittest.TestCase):
    """The game's own code on retail + modern IR."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_roster
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.retail = data
        cls.payload, _ = ir.apply(data, "modern")
        cls.store_va = ir.store_va(cls.payload)
        cls.body = retail_roster()

    # ---------------------------------------------------------------- helpers
    def boot(self, payload=None, *, human=None, injure=()):
        m = Machine(payload or self.payload, trace_writes=False)
        m.load_retail_roster(self.body)
        m.seed(4242)
        for address, value in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 15), (0xE60010, 15)):
            m.put(address, value)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.told = []

        def tell():
            m.told.append(bytes(m.uc.mem_read(m.reg("EDX"), 400)).decode("utf-16-le", "replace").split("\0")[0])
            m.ret()
        m.leaf(0x14E520, tell, reason="information dialog: its text is recorded, the player presses A")
        for club, slot, weeks in injure:
            p = m.get(m.team_base + 500 * club + 4 * slot)
            self.hurt(m, p, weeks)
        m.call(0x13EE10, budget=2_000_000_000)
        for t in range(32):
            m.call(0xC4D30, ecx=m.team_base + 500 * t, edx=1 if t == human else 0)
        return m

    @staticmethod
    def hurt(m, p, weeks):
        m.put(p + 0x20, (m.get(p + 0x20) & ~(0xFF << 22) & 0xFFFFFFFF) | 0x80000000 | (weeks << 22))
        m.put(p + 0x24, (m.get(p + 0x24) & ~0x70000000 & 0xFFFFFFFF) | 0x40000000)

    @staticmethod
    def heal(m, p):
        m.put(p + 0x20, m.get(p + 0x20) & ~(0xFF << 22) & 0x7FFFFFFF)
        m.put(p + 0x24, m.get(p + 0x24) & 0x8FFFFFFF)

    @staticmethod
    def club(m, c):
        return m.call(0xC4C50, ecx=c)

    def roster(self, m, c):
        k = self.club(m, c)
        return [m.get(k + 4 * i) for i in range(m.uc.mem_read(k + 0x11C, 1)[0])]

    def store(self, m, c):
        raw = bytes(m.uc.mem_read(self.store_va + STORE_HEAD + CLUB_STRIDE * c, CLUB_STRIDE))
        return raw[0], raw[1], [struct.unpack_from("<IhBB", raw, 4 + 8 * i) for i in range(raw[0])]

    def stats(self, m):
        return struct.unpack("<14I", bytes(m.uc.mem_read(self.store_va + 8, 56)))

    def play(self, m, c, games):
        """Mark ``games`` more grid cells of club c played (kind 3): the minimum counts these."""
        grid = 0xE57C40
        for i in range(374):
            if not games:
                return
            cell = bytes(m.uc.mem_read(grid + 8 * i, 3))
            if cell[0] == 0 and c in (cell[1], cell[2]):
                m.uc.mem_write(grid + 8 * i, b"\x03")
                games -= 1
        self.fail("not enough scheduled games")

    @staticmethod
    def value(m, p):
        """The cut-down's own player value 0x246D80(p, 1) (an x87 float, stored by a three-instruction stub)."""
        stub = 0x3200000
        if not getattr(m, "stub_page", False):
            m.uc.mem_map(stub, 0x1000)
            m.stub_page = True
        m.uc.mem_write(stub, bytes.fromhex("e8") + struct.pack("<i", 0x246D80 - (stub + 5))
                       + bytes.fromhex("d91d00030003") + bytes.fromhex("c3"))
        m.call(stub, ecx=p, edx=1, budget=5_000_000)
        return struct.unpack("<f", bytes(m.uc.mem_read(0x3000300, 4)))[0]

    def week(self, m):
        m.put(0xE576A4, 8)
        m.call(0x2BE020, budget=400_000_000)

    # ---------------------------------------------------------------- the CPU pass
    def test_cpu_places_a_long_injury_keeps_his_salary_and_brings_him_back_after_4_games(self):
        m = self.boot(human=0)
        c = 5
        p = self.roster(m, c)[0]
        self.hurt(m, p, 6)
        payroll = m.get(self.club(m, c) + 0x124)
        self.week(m)
        n, returns, entries = self.store(m, c)
        self.assertEqual((n, returns, entries[0][0]), (1, 0, p))
        self.assertNotIn(p, self.roster(m, c))
        self.assertEqual(m.get(0xE421E0 + 20 * c), p)                      # the retail table mirrors the first five
        self.assertEqual(m.call(0x247110, ecx=p, edx=0x3000100), 1)
        self.assertEqual(m.get(0x3000100), self.club(m, c))
        m.call(0xC3F00, ecx=self.club(m, c))
        self.assertEqual(m.get(self.club(m, c) + 0x124), payroll)         # IR salary still counts
        self.heal(m, p)
        self.play(m, c, 3)
        self.week(m)
        self.assertEqual(self.store(m, c)[0], 1)                           # 3 games: too soon
        self.play(m, c, 1)
        self.week(m)
        n, returns, _ = self.store(m, c)
        self.assertEqual((n, returns), (0, 1))
        self.assertIn(p, self.roster(m, c))
        self.assertLessEqual(len(self.roster(m, c)), 53)

    def test_a_short_injury_and_the_human_club_stay_off_ir(self):
        m = self.boot(human=0)
        short, mine = self.roster(m, 6)[0], self.roster(m, 0)[0]
        self.hurt(m, short, 3)
        self.hurt(m, mine, 8)
        self.week(m)
        self.assertEqual((self.store(m, 6)[0], self.store(m, 0)[0]), (0, 0))
        self.assertIn(short, self.roster(m, 6))
        self.assertIn(mine, self.roster(m, 0))

    def test_cpu_managing_the_users_depth_places_but_never_releases_his_players(self):
        m = self.boot(human=0)
        m.put(0xE60140, 1)                                                 # "CPU manages my depth chart"
        c = 0
        club = self.club(m, c)
        p = self.roster(m, c)[0]
        self.hurt(m, p, 6)
        self.week(m)
        self.assertEqual(self.store(m, c)[0], 1)                           # placed, as retail's pass would
        agents = m.get(m.root + 0x3C)
        m.call(0xC3EE0, ecx=club, edx=m.get(agents))                       # a free agent fills the spot: 53 again
        self.assertEqual(len(self.roster(m, c)), 53)
        before = self.roster(m, c)
        self.heal(m, p)
        self.play(m, c, 4)
        self.week(m)
        self.assertEqual((self.store(m, c)[0], self.roster(m, c)), (1, before))   # no room: nobody released, he waits
        m.call(0x2BD900, ecx=club, edx=before[-1], args=(0, 0))           # the user releases someone himself
        self.week(m)
        self.assertEqual(self.store(m, c)[:2], (0, 1))
        self.assertIn(p, self.roster(m, c))

    def test_the_ninth_return_is_refused_and_he_stays_for_the_season(self):
        m = self.boot(human=0)
        c = 9
        best = sorted(self.roster(m, c), key=lambda p: -self.value(m, p))[:9]      # the club's nine most valuable
        for p in best:
            self.hurt(m, p, 5)
        self.week(m)
        self.assertEqual(self.store(m, c)[0], 9)
        for p in best:
            self.heal(m, p)
        self.play(m, c, 4)
        for _ in range(3):
            self.week(m)
        n, returns, entries = self.store(m, c)
        self.assertEqual(returns, 8)
        self.assertEqual(n, 1)
        self.assertEqual(entries[0][2] & 1, 1)                             # stays on IR for the season
        self.assertNotIn(entries[0][0], self.roster(m, c))
        self.assertLessEqual(len(self.roster(m, c)), 53)

    # ---------------------------------------------------------------- the user's IR button
    def test_the_user_places_and_activates_under_the_same_rules(self):
        m = self.boot(human=4)
        c = 4
        club = self.club(m, c)
        m.put(0xE3C0A0, club)
        picked = {"p": 0}
        m.leaf(0xF3250, lambda: m.ret(picked["p"]), reason="the roster screen's selected player")
        m.leaf(0x14E540, lambda: m.ret(1), reason="yes/no dialog: the player presses Yes")
        m.leaf(0xF31B0, lambda: m.ret(0), reason="screen refresh only")
        m.leaf(0x174C70, lambda: m.ret(), reason="screen refresh only")
        m.put(0xE576A4, 8)
        healthy, hurt = self.roster(m, c)[:2]
        picked["p"] = healthy
        m.call(0x247070, ecx=0x3000200, budget=200_000_000)
        self.assertEqual(m.told[-1], irsave.REASONS["not_injured"])
        self.hurt(m, hurt, 2)
        picked["p"] = hurt
        m.call(0x247070, ecx=0x3000200, budget=200_000_000)
        self.assertEqual(self.store(m, c)[0], 1)
        self.assertNotIn(hurt, self.roster(m, c))
        m.call(0x247070, ecx=0x3000200, budget=200_000_000)
        self.assertEqual(m.told[-1], irsave.REASONS["too_soon"])
        self.play(m, c, 4)
        m.call(0x247070, ecx=0x3000200, budget=200_000_000)
        self.assertEqual(m.told[-1], irsave.REASONS["still_injured"])
        self.heal(m, hurt)
        m.call(0x247070, ecx=0x3000200, budget=200_000_000)
        self.assertEqual(self.store(m, c)[:2], (0, 1))
        self.assertIn(hurt, self.roster(m, c))

    # ---------------------------------------------------------------- rollover, franchise start
    def test_rollover_brings_everyone_back_and_resets_the_returns(self):
        m = self.boot(human=0)
        c = 12
        players = self.roster(m, c)[:7]
        for p in players:
            self.hurt(m, p, 9)
        self.week(m)
        self.assertEqual(self.store(m, c)[0], 7)
        m.call(0x246F90, budget=400_000_000)
        self.assertEqual(self.store(m, c)[:2], (0, 0))
        for p in players:
            self.assertIn(p, self.roster(m, c))
        self.assertEqual([m.get(0xE421E0 + 20 * c + 4 * i) for i in range(5)], [0] * 5)

    def test_the_franchise_start_puts_a_rosters_long_injuries_on_ir(self):
        m = self.boot(human=None, injure=((3, 1, 10), (3, 2, 2)))
        n, _returns, entries = self.store(m, 3)
        self.assertEqual(n, 1)
        self.assertEqual(self.stats(m)[2], 1)                               # placed at the start
        p_long = entries[0][0]
        self.assertNotIn(p_long, self.roster(m, 3))

    # ---------------------------------------------------------------- the save
    def office(self, m):
        buf = 0x2100000
        m.uc.mem_write(buf, bytes(OFFICE))
        m.call(0x2D0790, ecx=buf, budget=400_000_000)
        return buf, bytes(m.uc.mem_read(buf, OFFICE))

    def test_save_and_load_round_trip_and_what_an_older_build_reads(self):
        m = self.boot(human=0)
        c = 14
        players = self.roster(m, c)[:7]
        for p in players:
            self.hurt(m, p, 9)
        self.week(m)
        self.play(m, c, 2)
        before = self.store(m, c)
        self.assertEqual(before[0], 7)
        buf, office = self.office(m)
        block = office[0x4FD0:0x4FD0 + 640]
        extension, returns, clubs = irsave.decode(block)
        self.assertTrue(extension)
        table = m.get(m.root + 4)
        self.assertEqual([row[0] for row in clubs[c]], [(p - table) // 0x54 for p in players])
        self.assertEqual({row[1] for row in clubs[c]}, {2})
        # a cold load: the store and the mirror rebuilt from the block alone
        m.uc.mem_write(self.store_va + STORE_HEAD, bytes(32 * CLUB_STRIDE))
        m.uc.mem_write(0xE421E0, bytes(640))
        m.call(0x2D0CE0, ecx=buf, budget=400_000_000)
        after = self.store(m, c)
        self.assertEqual([e[0] for e in after[2]], players)
        self.assertEqual(self.stats(m)[9], 1)                               # loads_extended
        # an older build (retail code) loading this franchise: the same roster (the save's arena, here the live one)
        # and the same front office. Its loader reads the low halves: the first five are its own season-ending IR.
        r = Machine(self.retail, trace_writes=False)
        r.load_retail_roster(self.body)
        r.leaf(0x177990, lambda: r.ret(pop=4), reason="progress renderer only")
        r.leaf(0x14E520, lambda: r.ret(), reason="information dialog")
        r.call(0x13EE10, budget=2_000_000_000)
        r.uc.mem_write(r.ARENA, bytes(m.uc.mem_read(m.ARENA, 0x200000)))
        r.uc.mem_write(0xE5786C, bytes(m.uc.mem_read(0xE5786C, 4 * 34)))
        rbuf = 0x2100000
        r.uc.mem_write(rbuf, office)
        r.call(0x2D0CE0, ecx=rbuf, budget=400_000_000)
        self.assertEqual([r.get(0xE421E0 + 20 * c + 4 * i) for i in range(5)], players[:5])
        tail = bytes(r.uc.mem_read(0xE42460, 64))
        r.call(0x246F90, budget=400_000_000)                                # its rollover: those five come back
        self.assertEqual(bytes(r.uc.mem_read(0xE42460, 64)), tail)
        k = r.call(0xC4C50, ecx=c)
        back = [r.get(k + 4 * i) for i in range(r.uc.mem_read(k + 0x11C, 1)[0])]
        self.assertTrue(all(p in back for p in players[:5]))
        self.assertFalse(any(p in back for p in players[5:]))                # the 6th and 7th: unattached there

    def test_a_legacy_block_migrates_with_a_fresh_clock(self):
        m = self.boot(human=0)
        c = 20
        players = self.roster(m, c)[:3]
        buf, office = self.office(m)
        table = m.get(m.root + 4)
        clubs = [[] for _ in range(32)]
        clubs[c] = [((p - table) // 0x54, 0, False) for p in players]
        legacy = irsave.encode(clubs, [0] * 32, extension=False)
        m.uc.mem_write(buf + 0x4FD0, legacy)
        m.call(0x2D0CE0, ecx=buf, budget=400_000_000)
        n, returns, entries = self.store(m, c)
        self.assertEqual((n, returns), (3, 0))
        self.assertEqual([e[0] for e in entries], players)
        self.assertEqual(self.stats(m)[10], 1)                              # loads_legacy


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class ProBowlTests(unittest.TestCase):
    """Q66: in the postseason the weekly pass walks league slots 32 and 33 (the Pro Bowl clubs). Retail would write a
    Pro Bowler past the 32-club table; the guard and modern IR write nothing there and remove no one."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_roster
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.retail = data
        cls.guard, _ = ir.apply(data, "guard")
        cls.modern, _ = ir.apply(data, "modern")
        cls.body = retail_roster()

    def run_pass(self, payload):
        m = Machine(payload, trace_writes=False)
        m.load_retail_roster(self.body)
        m.seed(2601)
        for a, v in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 15), (0xE60010, 15)):
            m.put(a, v)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="information dialog")
        m.call(0x13EE10, budget=2_000_000_000)
        menu = m.ARENA + 0x1A0000
        for _ in range(8):
            st, wk, end = (m.get(a) for a in (0xE576A4, 0xE576B4, 0xE576B0))
            if st == 9:
                break
            if st == 8 and wk < end:
                m.put(0xE576B4, end)
                continue
            m.call(0x2480B0, ecx=menu, budget=20_000_000_000)
        self.assertEqual(m.get(0xE576A4), 9)
        self.assertGreaterEqual(m.call(0xC4BE0), 34)
        afc = m.get(0xE5786C + 4 * 32)
        p = m.get(afc)
        n = m.uc.mem_read(afc + 0x11C, 1)[0]
        # retail's own IR condition: injured, more weeks out than 22 minus the week, and +0x28 bits 5..9
        m.put(p + 0x20, (m.get(p + 0x20) & ~(0xFF << 22) & 0xFFFFFFFF) | 0x80000000 | (40 << 22))
        m.put(p + 0x28, m.get(p + 0x28) | 0x3E0)
        m.uc.mem_write(0xE42460, bytes(0x20))   # what retail's slot-4 test reads for "club 32": a zero plan word
        writes = []

        def hook(uc, access, address, size, value, _):
            if 0xE42460 <= address < 0xE42490:
                writes.append(address)
        m.uc.hook_add(m.u.UC_HOOK_MEM_WRITE, hook)
        m.call(0x2BE020, budget=400_000_000)
        return writes, n, m.uc.mem_read(afc + 0x11C, 1)[0]

    def test_retail_writes_past_the_table(self):
        writes, n, after = self.run_pass(self.retail)
        self.assertTrue(writes)
        self.assertEqual(after, n - 1)

    def test_the_guard_and_modern_ir_leave_the_pro_bowl_clubs_alone(self):
        for payload in (self.guard, self.modern):
            writes, n, after = self.run_pass(payload)
            self.assertEqual((writes, after), ([], n))




@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class MyCareerTests(GameTests):
    """In MyCareer the person is a player, not the GM: the career club's IR is the CPU's. MyCareer marks its club in the
    human-coach array 0xE5775C and hooks the user-club test (C4D50, under 13EC30) so management code sees the club as
    CPU; the weekly IR pass asks 13EC30. Control: the same array without a loaded career is a Franchise human club, left
    to its user (MODES2's Q29 state: the real MyCareer owner composed with this one, its state block written)."""

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_roster
        from mod_editor.core import nfl2k5_my_career as career, nfl2k5_xbe_space as space
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.career = career
        base, _ = space.apply(data, career.REQUESTS, scaleout=True)
        composed, _ = ir.apply(career.apply(base)[0], "modern")
        cls.payload = composed
        cls.store_va = ir.store_va(composed)
        cls.career_state = career.allocations(composed)[1]["va"]
        cls.body = retail_roster()

    def career_club(self, m, *, loaded):
        m.uc.mem_write(0xE5775C, bytes(34 * 4))
        m.put(0xE5775C, 1)                                                 # club 0: MyCareer's club / a human coach
        if loaded:
            m.uc.mem_write(self.career_state, self.career.MAGIC)
            m.put(self.career_state + 24, 2)                               # an active career stage
            m.put(self.career_state + 56, 0)                               # the club MyCareer resolved
            m.put(self.career_state + 2588, self.club(m, 0))
        return m.call(0x13EC30, ecx=self.club(m, 0))

    def test_the_career_club_ir_is_cpu_managed_and_a_franchise_human_club_is_not(self):
        for loaded in (True, False):
            m = self.boot(human=None)
            human = self.career_club(m, loaded=loaded)
            self.assertEqual(human, 0 if loaded else 1)
            p = self.roster(m, 0)[0]
            self.hurt(m, p, 6)
            self.week(m)
            if not loaded:
                self.assertEqual(self.store(m, 0)[0], 0)                   # the Franchise user's club: his call
                self.assertIn(p, self.roster(m, 0))
                continue
            self.assertEqual(self.store(m, 0)[0], 1)                       # MyCareer: placed like any CPU club
            agents = m.get(m.root + 0x3C)
            m.call(0xC3EE0, ecx=self.club(m, 0), edx=m.get(agents))        # the spot filled: 53
            self.heal(m, p)
            self.play(m, 0, 4)
            self.week(m)
            self.assertEqual(self.store(m, 0)[:2], (0, 1))                 # back, the cut-down made the room
            self.assertIn(p, self.roster(m, 0))
            self.assertLessEqual(len(self.roster(m, 0)), 53)

    # the inherited GameTests run on the composed image too; keep this class to its own test
    for _name in [n for n in dir(GameTests) if n.startswith("test_")]:
        locals()[_name] = None
    del _name

if __name__ == "__main__":
    unittest.main()
