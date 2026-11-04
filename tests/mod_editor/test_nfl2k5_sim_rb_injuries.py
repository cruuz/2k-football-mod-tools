"""Pins and Unicorn units for the b779-sim2 simulated RB injury owner."""

from __future__ import annotations

import struct
import unittest

from tests.nfl2k5_supersim_draft_fixture import Machine, HAVE_UC, retail_bytes

from mod_editor.core import nfl2k5_sim_rb_injuries as inj


class ConstantTests(unittest.TestCase):
    def test_reviewed_probability_table(self):
        # 1.48 short and 0.21 long events a team-season over 17 weekly advances.
        self.assertEqual((inj.LONG_THRESHOLD, inj.SHORT_END), (810, 6516))
        self.assertAlmostEqual(inj.LONG_THRESHOLD / 65536 * 17, 0.2101, places=3)
        self.assertAlmostEqual((inj.SHORT_END - inj.LONG_THRESHOLD) / 65536 * 17, 1.4804, places=3)
        self.assertEqual(inj.INJURY_MASK, 0xBFC00000)
        self.assertEqual(inj.ROTATION_THRESHOLD, 1311)          # 2% of a healthy HB selection goes to the next back (b779-int1)

    def test_owner_and_allocation_request(self):
        self.assertEqual(inj.OWNER, "nfl2k5_sim_rb_injuries")
        self.assertEqual(inj.REQUESTS, ((inj.OWNER, "code", inj.CODE_SIZE, 16),))
        self.assertEqual(inj.CODE_SIZE, 640)
        self.assertEqual(inj.SUB_OFFSET, 256)

    def test_sites_are_the_retail_tail_and_the_carrier_call(self):
        weekly, carrier = inj.sites(0x14DA000)
        self.assertEqual((weekly[0], weekly[1], weekly[2]), ("weekly_injury_tick", 0x133CC9, bytes.fromhex("5f5e5bc390")))
        self.assertEqual((carrier[0], carrier[1], carrier[2]), ("sim_carrier_guard", 0x106CFA, bytes.fromhex("e861c6ffff")))
        self.assertEqual(weekly[3][:1], b"\xe9")
        self.assertEqual((weekly[1] + 5 + struct.unpack_from("<i", weekly[3], 1)[0]) & 0xFFFFFFFF, 0x14DA000)
        self.assertEqual(carrier[3][:1], b"\xe8")
        self.assertEqual((carrier[1] + 5 + struct.unpack_from("<i", carrier[3], 1)[0]) & 0xFFFFFFFF,
                         0x14DA000 + inj.SUB_OFFSET)

    def test_code_layout_and_week_ranges(self):
        code = inj.code_for(0x14DA000)
        self.assertEqual(len(code), inj.CODE_SIZE)
        self.assertEqual(code[:4], bytes.fromhex("5f5e5b60"))          # pop edi; pop esi; pop ebx; pushad
        self.assertEqual(code[inj.SUB_OFFSET:inj.SUB_OFFSET + 6], bytes.fromhex("60e85a92c2fe"))  # pushad; call 0x103360
        self.assertEqual(code[inj.SUB_OFFSET - 1], 0xCC)
        # the roll embeds 4/5 weeks for the long bucket and 2/3 for the short one
        self.assertIn(bytes.fromhex("83c004"), code[:inj.SUB_OFFSET])
        self.assertIn(bytes.fromhex("83c002"), code[:inj.SUB_OFFSET])
        # exactly one league-RNG call and one human-club test in the weekly entry (b780 hunt1)
        targets = [0x14DA000 + i + 5 + struct.unpack_from("<i", code, i + 1)[0]
                   for i in range(inj.SUB_OFFSET - 5) if code[i] == 0xE8]
        self.assertEqual(targets.count(inj.FN_RAND), 1)
        self.assertEqual(targets.count(inj.FN_HUMAN_CLUB), 1)
        self.assertEqual(inj.FN_HUMAN_CLUB, 0x13EC30)

    def test_apply_is_read_back_and_idempotent(self):
        data = retail_bytes()
        if data is None:
            self.skipTest("private USA retail XBE is absent")
        self.assertEqual(inj.status(data), "retail")
        patched, receipt = inj.apply(data)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(inj.status(patched), "applied")
        va = int(receipt["code_va"], 16)
        alloc = [r for r in receipt["allocation"]["allocations"] if r["owner"] == inj.OWNER][0]
        self.assertEqual((alloc["kind"], alloc["size"], alloc["align"]), ("code", inj.CODE_SIZE, 16))
        again, second = inj.apply(patched)
        self.assertEqual(again, patched)
        self.assertEqual(second["status"], "already_applied")
        import hashlib
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(patched)
        self.assertEqual(bytes(image.read(0x133CC9, 5))[0], 0xE9)
        self.assertEqual(bytes(image.read(0x106CFA, 5))[0], 0xE8)
        self.assertEqual(hashlib.sha256(image.read(va, inj.CODE_SIZE)).digest(),
                         hashlib.sha256(inj.code_for(va)).digest())


def patch_code(m, va, blob):
    page = va & ~0xFFF
    m.uc.mem_protect(page, 0x1000, m.u.UC_PROT_READ | m.u.UC_PROT_WRITE | m.u.UC_PROT_EXEC)
    m.uc.mem_write(va, blob)


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class RollTests(unittest.TestCase):
    """The assembled weekly entry, with the six game routines it calls stubbed to fixed answers."""

    @classmethod
    def setUpClass(cls):
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.payload = data

    def machine(self, draw, human=False):
        m = Machine(self.payload, trace_writes=False)
        self.team = m.ARENA + 0x1000
        self.player = m.ARENA + 0x2000
        self.code = 0x300F000
        m.uc.mem_write(self.code, inj.code_for(self.code))
        m.uc.mem_protect(self.code & ~0xFFF, 0x1000, m.u.UC_PROT_READ | m.u.UC_PROT_WRITE | m.u.UC_PROT_EXEC)
        m.uc.mem_write(self.player, bytes(0x54))
        m.uc.mem_write(self.player + 0x35, b"\x07")
        m.put(self.team + 0x11C, 1)
        m.put(self.team, self.player)
        patch_code(m, 0x000C6430, b"\xb8\x01\x00\x00\x00\xc3")              # 1 club
        patch_code(m, 0x000C4C50, b"\xb8" + struct.pack("<I", self.team) + b"\xc3")
        patch_code(m, 0x000C3E70, b"\xb8" + struct.pack("<I", self.player) + b"\xc3")
        patch_code(m, 0x000C3E80, b"\x33\xc0\xc3")                          # no next player
        patch_code(m, 0x00048BC0, b"\xb8" + struct.pack("<I", draw) + b"\xc3")
        patch_code(m, inj.FN_HUMAN_CLUB, b"\xb8" + struct.pack("<I", int(human)) + b"\xc3")
        return m

    def roll(self, m):
        stack = 0x300F800
        m.uc.mem_write(stack, struct.pack("<IIII", 0, 0, 0, m.STOP))
        m.reg("ESP", stack)
        m.uc.emu_start(self.code, m.STOP, count=200000)
        return struct.unpack("<II", bytes(m.uc.mem_read(self.player + 0x20, 8)))

    def test_buckets_write_the_published_fields(self):
        for draw, weeks in ((0, 4), (1, 5), (810, 2), (811, 3), (6515, 3), (6516, 0), (60000, 0)):
            with self.subTest(draw=draw):
                word20, word24 = self.roll(self.machine(draw))
                self.assertEqual((word20 >> 22) & 0xFF, weeks)
                self.assertEqual((word20 >> 31) & 1, bool(weeks))
                self.assertEqual((word24 >> 28) & 7, 4 if weeks else 0)
                if weeks:
                    self.assertEqual(word24 & 0x70000000, 0x40000000)

    def test_an_already_injured_halfback_is_skipped(self):
        m = self.machine(0)
        word20 = 0x80000000 | (2 << 22)
        m.put(self.player + 0x20, word20)
        self.assertEqual(self.roll(m), (word20, m.get(self.player + 0x24)))

    def test_other_positions_are_skipped(self):
        m = self.machine(0)
        m.uc.mem_write(self.player + 0x35, b"\x08")
        before = struct.unpack("<II", bytes(m.uc.mem_read(self.player + 0x20, 8)))
        self.assertEqual(self.roll(m), before)

    def test_a_club_a_person_controls_gets_no_roll(self):
        # b780 hunt1: the draw that injures a computer club's back for 4 weeks leaves a human club's back alone
        m = self.machine(0, human=True)
        before = struct.unpack("<II", bytes(m.uc.mem_read(self.player + 0x20, 8)))
        self.assertEqual(self.roll(m), before)
        word20, _word24 = self.roll(self.machine(0, human=False))
        self.assertEqual((word20 >> 22) & 0xFF, 4)


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class CarrierGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.payload = data

    def machine(self, selected_kind="injured", backup=True, draw=65535):
        m = Machine(self.payload, trace_writes=False)
        root = m.ARENA + 0x1000
        teams = m.ARENA + 0x2000
        roster = m.ARENA + 0x3000
        match = m.ARENA + 0x180000
        self.code = 0x300F000
        m.uc.mem_write(self.code, inj.code_for(self.code))
        m.uc.mem_protect(self.code & ~0xFFF, 0x1000, m.u.UC_PROT_READ | m.u.UC_PROT_WRITE | m.u.UC_PROT_EXEC)
        # one club with two halfbacks: roster[0] injured, roster[1] healthy
        for i in range(2):
            m.uc.mem_write(roster + i * 0x54, bytes(0x54))
            m.put(roster + i * 0x54, 0xA000 + i)                 # identity word
            m.put(roster + i * 0x54 + 0x10, 0x9000 + i)          # name pointer
            m.uc.mem_write(roster + i * 0x54 + 0x35, b"\x07")
        m.put(teams + 0x11C, 0 + 2)
        m.put(teams, roster)
        m.put(teams + 4, roster + 0x54)
        m.put(0xB72918, root)
        m.put(root + 0x1C, teams)
        # selected match copy: a byte-identical identity to roster[0], injured
        sel = match
        m.uc.mem_write(sel, bytes(0x54))
        m.put(sel, 0xA000)
        m.put(sel + 0x10, 0x9000)
        m.uc.mem_write(sel + 0x35, b"\x07")
        m.put(sel + 0x20, 0x80000000 | (2 << 22))
        if selected_kind == "healthy":
            m.put(sel + 0x20, 0)
        elif selected_kind == "receiver":
            m.uc.mem_write(sel + 0x35, b"\x08")
        if backup:
            copy = match + 0x200
            m.uc.mem_write(copy, bytes(0x54))
            m.put(copy, 0xA001)
            m.put(copy + 0x10, 0x9001)
            m.uc.mem_write(copy + 0x35, b"\x07")
            self.backup = copy
        patch_code(m, 0x00103360, b"\xb8" + struct.pack("<I", sel) + b"\xc3")
        patch_code(m, 0x00048BC0, b"\xb8" + struct.pack("<I", draw) + b"\xc3")
        return m, sel

    def call(self, m):
        stack = 0x300F800
        m.uc.mem_write(stack, struct.pack("<I", m.STOP))
        m.reg("ESP", stack)
        m.uc.emu_start(self.code + inj.SUB_OFFSET, m.STOP, count=2000000)
        return m.reg("EAX")

    def test_injured_halfback_returns_the_next_healthy_match_copy(self):
        m, sel = self.machine()
        self.assertEqual(self.call(m), self.backup)
        self.assertNotEqual(self.backup, sel)

    def test_healthy_selection_rotates_on_its_draw(self):
        m, sel = self.machine("healthy", True, draw=0)
        self.assertEqual(self.call(m), self.backup)
        m, sel = self.machine("healthy", True, draw=65535)
        self.assertEqual(self.call(m), sel)

    def wrap_machine(self, code_for):
        """b780 hunt1: the club list is [healthy HB, WR, selected injured HB, WR] and the word after it is no pointer
        (in the club record the count word +0x11C follows the 65 slots). The next healthy back is BEFORE the
        selected one, so the scan must wrap at the club count."""
        m = Machine(self.payload, trace_writes=False)
        root, teams, roster, match = m.ARENA + 0x1000, m.ARENA + 0x2000, m.ARENA + 0x3000, m.ARENA + 0x180000
        self.code = 0x300F000
        m.uc.mem_write(self.code, code_for(self.code))
        m.uc.mem_protect(self.code & ~0xFFF, 0x1000, m.u.UC_PROT_READ | m.u.UC_PROT_WRITE | m.u.UC_PROT_EXEC)
        kinds = (7, 3, 7, 3)                                     # HB, WR, HB (selected, injured), WR
        for i, kind in enumerate(kinds):
            m.uc.mem_write(roster + i * 0x54, bytes(0x54))
            m.put(roster + i * 0x54, 0xA000 + i)
            m.put(roster + i * 0x54 + 0x10, 0x9000 + i)
            m.uc.mem_write(roster + i * 0x54 + 0x35, bytes([kind]))
            m.put(teams + 4 * i, roster + i * 0x54)
        m.put(roster + 2 * 0x54 + 0x20, 0x80000000 | (3 << 22))
        m.put(teams + 4 * len(kinds), 0x24)                     # past the list: a small number, no pointer
        m.put(teams + 0x11C, len(kinds))
        m.put(0xB72918, root)
        m.put(root + 0x1C, teams)
        sel, backup = match, match + 0x200
        for copy, ident in ((sel, 2), (backup, 0)):
            m.uc.mem_write(copy, bytes(0x54))
            m.put(copy, 0xA000 + ident)
            m.put(copy + 0x10, 0x9000 + ident)
            m.uc.mem_write(copy + 0x35, b"\x07")
        m.put(sel + 0x20, 0x80000000 | (3 << 22))
        patch_code(m, 0x00103360, b"\xb8" + struct.pack("<I", sel) + b"\xc3")
        patch_code(m, 0x00048BC0, b"\xb8" + struct.pack("<I", 65535) + b"\xc3")
        return m, sel, backup

    def test_the_scan_wraps_at_the_club_count_and_never_reads_past_the_list(self):
        m, sel, backup = self.wrap_machine(inj.code_for)
        self.assertEqual(self.call(m), backup)

    def test_beta79_read_past_the_list(self):
        from unicorn import UcError
        from mod_editor.core import nfl2k5_sim_rb_injuries_b779 as b779
        m, sel, backup = self.wrap_machine(b779.code_for)
        with self.assertRaises(UcError):                        # +0x35 through the word 0x24: address 0x59
            self.call(m)

    def test_receiver_and_no_backup_keep_retail(self):
        for kind, backup, draw in (("receiver", True, 0), ("receiver", True, 65535), ("injured", False, 0)):
            with self.subTest(kind=kind, backup=backup, draw=draw):
                m, sel = self.machine(kind, backup, draw=draw)
                self.assertEqual(self.call(m), sel)


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class UserClubTests(unittest.TestCase):
    """b780 hunt1, the game's own code: the retail executable with this owner, the retail roster, the franchise start
    0x13EE10 and the franchise week's injury tick 0x133C50. One club is marked human with the game's own setter
    0xC4D30 (the flag the Franchise and MyCareer clubs carry). Each tick starts with both targets healthy."""

    TICKS = 160

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_roster
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.payload, _ = inj.apply(data)
        cls.body = retail_roster()

    def counts(self, payload):
        m = Machine(payload, trace_writes=False)
        m.load_retail_roster(self.body)
        m.seed(4242)
        for address, value in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 15), (0xE60010, 15)):
            m.put(address, value)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog acknowledgement only")
        m.call(0x13EE10, budget=2_000_000_000)
        clubs = [m.team_base + 500 * t for t in (0, 1)]
        for t in range(32):
            m.call(0xC4D30, ecx=m.team_base + 500 * t, edx=1 if t == 0 else 0)
        self.assertEqual([m.call(0x13EC30, ecx=c) for c in clubs], [1, 0])

        def first_healthy_back(club):
            p = m.call(0xC3E70, ecx=club)
            while p:
                if m.uc.mem_read(p + 0x35, 1)[0] == 7 and not m.get(p + 0x20) & inj.INJURY_MASK:
                    return p
                p = m.call(0xC3E80, ecx=club, edx=p)
            self.fail("no healthy halfback")
        backs = [first_healthy_back(c) for c in clubs]
        hits = [0, 0]
        for _ in range(self.TICKS):
            for p in backs:
                m.put(p + 0x20, m.get(p + 0x20) & ~inj.INJURY_MASK & 0xFFFFFFFF)
                m.put(p + 0x24, m.get(p + 0x24) & 0x8FFFFFFF)
            m.call(0x133C50, budget=50_000_000)
            for k, p in enumerate(backs):
                hits[k] += bool(m.get(p + 0x20) & inj.INJURED)
        return hits

    def test_the_human_club_is_left_alone_and_a_computer_club_still_rolls(self):
        human, computer = self.counts(self.payload)
        self.assertEqual(human, 0)
        # 6516 / 65536 a tick (about 16 in 160): a wide band, the draws are the game's own
        self.assertTrue(5 <= computer <= 32, computer)

    def test_the_beta79_roll_hit_the_human_club_too(self):
        from mod_editor.core import nfl2k5_sim_rb_injuries_b779 as b779
        previous, _ = b779.apply(retail_bytes())
        human, computer = self.counts(previous)
        self.assertGreater(human, 0)
        self.assertGreater(computer, 0)


class PreviousTests(unittest.TestCase):
    """b780 hunt1: a beta-79 / SOFTDRINK 2K28 v0.8 install reads "previous" and is upgraded in place."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_sim_rb_injuries_b779 as b779
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.b779 = b779
        cls.previous, _ = b779.apply(data)
        cls.current, _ = inj.apply(data)

    def test_previous_reads_previous_and_upgrades_in_place(self):
        self.assertEqual(inj.status(self.previous), "previous")
        upgraded, receipt = inj.apply(self.previous)
        self.assertEqual((receipt["status"], receipt["upgraded_from"]), ("applied", "previous"))
        self.assertEqual(inj.status(upgraded), "applied")
        self.assertEqual(upgraded, self.current)          # the same image a fresh install from retail makes
        again, second = inj.apply(upgraded)
        self.assertEqual((again, second["status"]), (upgraded, "already_applied"))

    def test_only_the_cave_differs_from_beta79(self):
        va = inj.allocation(self.previous)["va"]
        self.assertEqual(va, inj.allocation(self.current)["va"])
        self.assertEqual(inj.sites(va), self.b779.sites(va))
        self.assertNotEqual(inj.code_for(va), self.b779.code_for(va))
        self.assertEqual(len(inj.code_for(va)), len(self.b779.code_for(va)))


if __name__ == "__main__":
    unittest.main()
