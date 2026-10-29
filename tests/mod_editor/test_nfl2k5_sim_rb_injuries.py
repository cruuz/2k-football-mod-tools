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
        self.assertEqual(inj.ROTATION_THRESHOLD, 3932)          # 6% of a healthy HB selection goes to the next back

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
        # exactly one league-RNG call and one injured|weeks test in each entry
        self.assertEqual(code[:inj.SUB_OFFSET].count(bytes.fromhex("e86debb6fe")), 1)

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

    def machine(self, draw):
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

    def test_receiver_and_no_backup_keep_retail(self):
        for kind, backup, draw in (("receiver", True, 0), ("receiver", True, 65535), ("injured", False, 0)):
            with self.subTest(kind=kind, backup=backup, draw=draw):
                m, sel = self.machine(kind, backup, draw=draw)
                self.assertEqual(self.call(m), sel)


if __name__ == "__main__":
    unittest.main()
