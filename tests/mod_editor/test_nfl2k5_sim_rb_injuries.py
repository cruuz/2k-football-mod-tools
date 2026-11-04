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
        self.assertEqual(inj.SUB_OFFSET, 208)                 # b780 db2: the guard grew with the fullback rule (beta-79: 256)
        self.assertTrue(inj.UPGRADES_PREVIOUS)

    def test_fullback_rule_constants(self):
        # b780 db2: a fullback keeps 1 in 16 of the carries the retail lottery gives him (NFL 2021-2025: 0.3% of
        # carries; the retail lottery gave the modern roster's fullbacks 9.3-9.9%)
        self.assertEqual((inj.FULLBACK_POSITION, inj.FULLBACK_KEEP_THRESHOLD, inj.FULLBACK_REDRAWS), (8, 4096, 3))
        self.assertEqual(inj.FULLBACK_KEEP_THRESHOLD / 65536, 1 / 16)

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
        call = b"\x60\xe8" + struct.pack("<i", 0x103360 - (0x14DA000 + inj.SUB_OFFSET + 6))
        self.assertEqual(code[inj.SUB_OFFSET:inj.SUB_OFFSET + 6], call)  # pushad; call 0x103360
        # b780 db2: the beta-79 guard sat at 256 and had no fullback test
        from mod_editor.core import nfl2k5_sim_rb_injuries_b779 as b779
        previous = b779.code_for(0x14DA000)
        self.assertEqual(previous[256:262], bytes.fromhex("60e85a92c2fe"))
        self.assertNotIn(bytes.fromhex("807e3508"), previous)
        self.assertEqual(code.count(bytes.fromhex("807e3508")), 1)     # cmp byte [esi+0x35], 8
        self.assertEqual(code.count(bytes.fromhex("663d0010")), 1)     # cmp ax, 4096
        self.assertEqual(code[inj.SUB_OFFSET - 1], 0xCC)
        # the roll embeds 4/5 weeks for the long bucket and 2/3 for the short one
        self.assertIn(bytes.fromhex("83c004"), code[:inj.SUB_OFFSET])
        self.assertIn(bytes.fromhex("83c002"), code[:inj.SUB_OFFSET])
        # exactly one league-RNG call in the weekly entry, and the human test reads the native per-club array
        # (b780 hunt1: no call to 0x13EC30, which MyCareer's cpu_management hook answers 0 to cave callers)
        targets = [0x14DA000 + i + 5 + struct.unpack_from("<i", code, i + 1)[0]
                   for i in range(inj.SUB_OFFSET - 5) if code[i] == 0xE8]
        self.assertEqual(targets.count(inj.FN_RAND), 1)
        self.assertEqual(targets.count(inj.FN_HUMAN_CLUB), 0)
        self.assertEqual(inj.HUMAN_FLAGS, 0xE5775C)
        self.assertEqual(code[:inj.SUB_OFFSET].count(bytes.fromhex("833c9d5c77e50000")), 1)  # cmp dword [0xE5775C+ebx*4], 0

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


class PreviousRevisionTests(unittest.TestCase):
    """b780 db2: the released v0.8 executable carries the beta-79 guard; it reads "previous" and upgrades in place."""

    def test_v08_install_reads_previous_and_upgrades_in_place(self):
        import hashlib
        import os
        from pathlib import Path
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        path = Path(os.environ.get("NFL2K5_V08_XBE", "/nonexistent"))
        if not path.is_file():
            self.skipTest("the released v0.8 executable is absent (NFL2K5_V08_XBE)")
        data = path.read_bytes()
        self.assertEqual(inj.status(data), "previous")
        va = inj.allocation(data)["va"]
        from mod_editor.core import nfl2k5_sim_rb_injuries_b779 as b779
        self.assertEqual(XbeImage(data).read(va, inj.CODE_SIZE), b779.code_for(va))
        upgraded, receipt = inj.apply(data)
        self.assertEqual((receipt["status"], receipt["upgraded_from"], len(upgraded)), ("applied", "previous", len(data)))
        self.assertEqual(inj.status(upgraded), "applied")
        image = XbeImage(upgraded)
        self.assertEqual(image.read(va, inj.CODE_SIZE), inj.code_for(va))      # the fresh install's bytes
        for _name, site, _before, after in inj.sites(va):
            self.assertEqual(image.read(site, len(after)), after)
        self.assertEqual([e["label"] for e in receipt["edits"]], ["sim_carrier_guard"])  # the weekly hook is unchanged
        again, second = inj.apply(upgraded)
        self.assertEqual((again, second["status"]), (upgraded, "already_applied"))


class BuildPreflightTests(unittest.TestCase):
    def test_the_build_preflight_accepts_the_beta79_install(self):
        # b780 db2: a v0.8 source carries the beta-79 guard ("previous"); the build step upgrades it in place
        from pathlib import Path
        from unittest import mock
        from mod_editor.core import mod_build
        for state, accepted in (("retail", True), ("applied", True), ("previous", True), ("foreign", False)):
            with self.subTest(state=state):
                fake = mock.Mock(status=mock.Mock(return_value=state))
                with mock.patch.object(mod_build, "_core_module", return_value=fake), \
                        mock.patch.object(mod_build, "_xbe_bytes", return_value=b""):
                    if accepted:
                        mod_build._sim_rb_injuries_preflight(Path("default.xbe"), lambda *_: None)
                    else:
                        with self.assertRaises(ValueError):
                            mod_build._sim_rb_injuries_preflight(Path("default.xbe"), lambda *_: None)


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
        m.put(inj.HUMAN_FLAGS, int(human))                                  # club index 0's native human flag
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
            m.uc.mem_write(sel + 0x35, b"\x03")              # a wide receiver (b780 db2: 8 is the fullback rule)
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


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class MyCareerClubTests(unittest.TestCase):
    """REV1 #1, the game's own code with MyCareer installed: retail + MyCareer mode + this owner, the retail roster,
    the franchise start 0x13EE10 and the week's injury tick 0x133C50. MyCareer hooks the human getter 0xC4D50
    (``cpu_management``): while a career is loaded it answers 0 to every caller outside the game launch and the menu
    team enumerators, so the first revision's test (``call 0x13EC30``) saw the MyCareer club as a computer club and
    rolled for it. The roll reads the native human array, which MyCareer's resolve sets for its club only."""

    TICKS = 160

    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_roster
        from mod_editor.core import nfl2k5_my_career as career, nfl2k5_my_career_mode as mode
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.payload, _ = inj.apply(mode.apply(data)[0])
        cls.state = career.allocations(cls.payload)[1]["va"]
        cls.body = retail_roster()

    def machine(self, loaded=True):
        m = Machine(self.payload, trace_writes=False)
        m.load_retail_roster(self.body)
        m.seed(4242)
        for address, value in ((0xE5FF80, 4), (0xE60120, 0), (0xE6000C, 15), (0xE60010, 15)):
            m.put(address, value)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog acknowledgement only")
        m.call(0x13EE10, budget=2_000_000_000)
        self.clubs = [m.team_base + 500 * t for t in (0, 1)]
        # a loaded career whose club is club 0: the state MyCareer's enabled test reads (magic, version, the game
        # mode 2 at 0xE576A0, a career stage 1..6), its club, and the native human array as its resolve leaves it
        m.put(0xE576A0, 2)
        if loaded:
            for offset, value in ((0, 0x4251434D), (4, 0x31303030), (24, 3), (56, 0), (2588, self.clubs[0])):
                m.put(self.state + offset, value)
        for t in range(34):
            m.put(inj.HUMAN_FLAGS + 4 * t, int(t == 0))
        return m

    def test_the_hook_tells_a_cave_caller_a_computer_owns_the_career_club(self):
        m = self.machine(loaded=True)
        self.assertEqual(m.call(inj.FN_HUMAN_CLUB, ecx=self.clubs[0]), 0)    # this harness's return address
        self.assertEqual(m.get(inj.HUMAN_FLAGS), 1)                          # the native flag says human
        m = self.machine(loaded=False)
        self.assertEqual(m.call(inj.FN_HUMAN_CLUB, ecx=self.clubs[0]), 1)    # no career: the retail getter

    def counts(self, m):
        def first_healthy_back(club):
            p = m.call(0xC3E70, ecx=club)
            while p:
                if m.uc.mem_read(p + 0x35, 1)[0] == 7 and not m.get(p + 0x20) & inj.INJURY_MASK:
                    return p
                p = m.call(0xC3E80, ecx=club, edx=p)
            self.fail("no healthy halfback")
        backs = [first_healthy_back(c) for c in self.clubs]
        hits = [0, 0]
        for _ in range(self.TICKS):
            for p in backs:
                m.put(p + 0x20, m.get(p + 0x20) & ~inj.INJURY_MASK & 0xFFFFFFFF)
                m.put(p + 0x24, m.get(p + 0x24) & 0x8FFFFFFF)
            m.call(0x133C50, budget=50_000_000)
            for k, p in enumerate(backs):
                hits[k] += bool(m.get(p + 0x20) & inj.INJURED)
        return hits

    def test_the_career_club_is_left_alone_with_the_hook_in_place(self):
        career_club, computer = self.counts(self.machine(loaded=True))
        self.assertEqual(career_club, 0)
        self.assertTrue(5 <= computer <= 32, computer)     # 6516 / 65536 a tick, the game's own draws

    def test_without_its_human_flag_the_career_club_would_roll(self):
        # the control: the same machine with the career club's native flag cleared rolls for it like any club
        m = self.machine(loaded=True)
        m.put(inj.HUMAN_FLAGS, 0)
        career_club, computer = self.counts(m)
        self.assertGreater(career_club, 0)
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

    def test_only_the_cave_and_the_carrier_call_differ_from_beta79(self):
        va = inj.allocation(self.previous)["va"]
        self.assertEqual(va, inj.allocation(self.current)["va"])
        (weekly, carrier), (weekly79, carrier79) = inj.sites(va), self.b779.sites(va)
        self.assertEqual(weekly, weekly79)                    # the weekly hook keeps its bytes
        self.assertEqual(carrier[:3], carrier79[:3])
        # b780 db2: the guard moved from offset 256 to 208, so the call at 0x106CFA is re-pointed
        for (_n, site, _b, after), offset in ((carrier, inj.SUB_OFFSET), (carrier79, 256)):
            self.assertEqual((site + 5 + struct.unpack_from("<i", after, 1)[0]) & 0xFFFFFFFF, va + offset)
        self.assertNotEqual(inj.code_for(va), self.b779.code_for(va))
        self.assertEqual(len(inj.code_for(va)), len(self.b779.code_for(va)))

    def test_a_mixed_install_is_foreign(self):
        # b780 db2: this release's cave behind the beta-79 carrier call (or the reverse) is no install of either
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        va = inj.allocation(self.current)["va"]
        for payload, site_bytes in ((self.current, self.b779.sites(va)[1][3]), (self.previous, inj.sites(va)[1][3])):
            buf = bytearray(payload)
            off = XbeImage(payload).offset(0x106CFA, 5)
            buf[off:off + 5] = site_bytes
            self.assertEqual(inj.status(bytes(buf)), "foreign")


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class FullbackRuleTests(unittest.TestCase):
    """b780 db2: the assembled guard on a constructed sim team (QB1, HB1, FB1, HB2 slots) and club. The retail lottery
    0x103360 is replayed by a leaf that also checks it is always asked for the same team (ESI)."""

    @classmethod
    def setUpClass(cls):
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.payload = data

    def machine(self, picks, draw=None, lead="healthy"):
        """picks: the lottery's successive answers (role names), or a callable returning one. draw None: the game's
        own league RNG (seeded); otherwise every 16-bit draw returns ``draw``."""
        m = Machine(self.payload, trace_writes=False)
        root, clubs, roster, match, team = (m.ARENA + 0x1000, m.ARENA + 0x2000, m.ARENA + 0x3000,
                                            m.ARENA + 0x180000, m.ARENA + 0x4000)
        self.code = 0x300F000
        m.uc.mem_write(self.code, inj.code_for(self.code))
        m.uc.mem_protect(self.code & ~0xFFF, 0x1000, m.u.UC_PROT_READ | m.u.UC_PROT_WRITE | m.u.UC_PROT_EXEC)
        # one club: roster[0] HB1, roster[1] HB2, roster[2] FB1, roster[3] QB1; match copies 0x200 apart
        self.copies = {}
        for i, (role, pos) in enumerate((("hb1", 7), ("hb2", 7), ("fb", 8), ("qb", 0))):
            rec, copy = roster + i * 0x54, match + i * 0x200
            for at in (rec, copy):
                m.uc.mem_write(at, bytes(0x54))
                m.put(at, 0xA000 + i)                          # identity word
                m.put(at + 0x10, 0x9000 + i)                   # name pointer
                m.uc.mem_write(at + 0x35, bytes([pos]))
            m.put(clubs + 4 * i, rec)
            self.copies[role] = copy
        self.copies["none"] = 0
        m.uc.mem_write(clubs + 0x11C, b"\x04")
        m.put(0xB72918, root)
        m.put(root + 0x1C, clubs)
        if lead == "injured":
            for at in (roster, self.copies["hb1"]):
                m.put(at + 0x20, 0x80000000 | (2 << 22))
        elif lead == "tight end":
            m.uc.mem_write(self.copies["hb1"] + 0x35, b"\x09")
        # the sim team offense summary: +8 QB1, +0xC HB1, +0x10 FB1, +0x14 HB2 (lineup table 0xA96828)
        for slot, role in enumerate(("qb", "hb1", "fb", "hb2")):
            m.put(team + 8 + 4 * slot, self.copies[role])
        self.team = team
        self.asked = 0
        nxt = picks if callable(picks) else iter(picks).__next__

        def lottery():
            self.assertEqual(m.reg("ESI"), self.team)          # every draw is for the team the guard was called with
            self.asked += 1
            m.ret(self.copies[nxt()])
        m.leaf(0x00103360, lottery, reason="the retail carrier lottery's answers, replayed")
        if draw is None:
            m.seed(2501)
        else:
            patch_code(m, 0x00048BC0, b"\xb8" + struct.pack("<I", draw) + b"\xc3")
        return m

    def call(self, m):
        return m.call(self.code + inj.SUB_OFFSET, esi=self.team, budget=2000000)

    def test_a_fullback_keeps_one_carry_in_sixteen(self):
        for draw, expected, asked in ((0, "fb", 1), (4095, "fb", 1), (4096, "hb1", 2), (65535, "hb1", 2)):
            with self.subTest(draw=draw):
                m = self.machine(["fb", "hb1"], draw)
                self.assertEqual(self.call(m), self.copies[expected])
                self.assertEqual(self.asked, asked)

    def test_the_redraw_follows_the_lottery(self):
        # a re-drawn halfback takes the halfback path: injured, his carry goes on to the next healthy back
        m = self.machine(["fb", "hb1"], 65535, lead="injured")
        self.assertEqual(self.call(m), self.copies["hb2"])
        # a re-drawn quarterback or second back is returned as drawn
        for pick in ("qb", "hb2"):
            with self.subTest(pick=pick):
                m = self.machine(["fb", pick], 65535)
                self.assertEqual(self.call(m), self.copies[pick])
        # fullback on the first draw and on all three re-draws: the HB1 slot takes the carry (the halfback path:
        # healthy, it stays with him; hurt, it goes on to the next healthy back); no halfback there keeps the fullback
        m = self.machine(["fb"] * 4, 65535)
        self.assertEqual((self.call(m), self.asked), (self.copies["hb1"], 1 + inj.FULLBACK_REDRAWS))
        m = self.machine(["fb"] * 4, 65535, lead="injured")
        self.assertEqual(self.call(m), self.copies["hb2"])
        m = self.machine(["fb"] * 4, 65535, lead="tight end")
        self.assertEqual(self.call(m), self.copies["fb"])
        m = self.machine(["fb", "fb", "hb2"], 65535)
        self.assertEqual((self.call(m), self.asked), (self.copies["hb2"], 3))
        m = self.machine(["fb", "none"], 65535)
        self.assertEqual(self.call(m), self.copies["fb"])

    def test_other_picks_are_unchanged(self):
        for pick in ("qb", "hb2"):
            with self.subTest(pick=pick):
                m = self.machine([pick], 65535)
                self.assertEqual((self.call(m), self.asked), (self.copies[pick], 1))

    def test_previous_guard_kept_every_fullback_carry(self):
        from mod_editor.core import nfl2k5_sim_rb_injuries_b779 as b779
        m = self.machine(["fb"], 65535)
        m.uc.mem_write(self.code, b779.code_for(self.code))
        self.assertEqual(m.call(self.code + b779.SUB_OFFSET, esi=self.team, budget=2000000), self.copies["fb"])

    def test_measured_share_with_the_league_rng(self):
        """4,000 carries from a lottery that answers in the measured v0.8 mix for a club with a fullback (HB1 46%,
        HB2 23%, FB 10%, QB 21% with the realism QB picks folded in), through the guard with the game's own league
        RNG: the fullback keeps about 1 in 16 of his picks and the rest are shared by the others in the same mix."""
        import random
        rng = random.Random(2501)
        mix = (("hb1", 0.46), ("hb2", 0.23), ("fb", 0.10), ("qb", 0.21))

        def lottery():
            x = rng.random()
            for role, share in mix:
                if x < share:
                    return role
                x -= share
            return "qb"
        m = self.machine(lottery, None)
        back = {v: k for k, v in self.copies.items() if v}
        out = {"hb1": 0, "hb2": 0, "fb": 0, "qb": 0}
        for _ in range(4000):
            out[back[self.call(m)]] += 1
        self.assertEqual(sum(out.values()), 4000)
        self.assertLessEqual(out["fb"], 4000 * 0.10 / 16 * 1.8)   # 1/16 of 400 = 25 expected
        self.assertGreaterEqual(out["fb"], 4000 * 0.10 / 16 * 0.4)
        for role, share in mix:                                   # the others keep their relative shares
            if role != "fb":
                self.assertAlmostEqual(out[role] / (4000 - out["fb"]), share / 0.90, delta=0.03, msg=role)


@unittest.skipUnless(HAVE_UC, "unicorn is needed")
class CarrierSiteChainTests(unittest.TestCase):
    """b780 db2 (REV2): the scheduled sim's carrier call 0x106CFA through the store of the ball carrier at 0x106D0A,
    run on retail with this owner and then Simulated season realism installed (the build's LATE_OWNERS order). The
    realism QB hook at 0x106CFF takes the guard's EAX and either keeps it or puts the QB in (a mobile QB's draw); the
    retail code stores EAX into 0xA971A4. The retail lottery 0x103360 is replayed; the league draw is fixed."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_sim_realism as realism
        data = retail_bytes()
        if data is None:
            raise unittest.SkipTest("private USA retail XBE is absent")
        cls.realism = realism
        cls.payload, _ = realism.apply(inj.apply(data)[0])
        cls.previous = None
        from mod_editor.core import nfl2k5_sim_rb_injuries_b779 as b779
        cls.previous, _ = realism.apply(b779.apply(data)[0])

    def run_site(self, payload, picks, draw, lead="healthy", mobile_qb=False, qb_roll=None):
        m = Machine(payload, trace_writes=False)
        root, clubs, roster, match, team = (m.ARENA + 0x1000, m.ARENA + 0x2000, m.ARENA + 0x3000,
                                            m.ARENA + 0x180000, m.ARENA + 0x4000)
        copies = {}
        for i, (role, pos) in enumerate((("hb1", 7), ("hb2", 7), ("fb", 8), ("qb", 0), ("wr", 3))):
            rec, copy = roster + i * 0x54, match + i * 0x200
            for at in (rec, copy):
                m.uc.mem_write(at, bytes(0x54))
                m.put(at, 0xA000 + i)
                m.put(at + 0x10, 0x9000 + i)
                m.uc.mem_write(at + 0x35, bytes([pos]))
            m.put(clubs + 4 * i, rec)
            copies[role] = copy
        m.uc.mem_write(clubs + 0x11C, b"\x05")
        m.put(0xB72918, root)
        m.put(root + 0x1C, clubs)
        if lead == "injured":
            for at in (roster, copies["hb1"]):
                m.put(at + 0x20, 0x80000000 | (2 << 22))
        if mobile_qb:                                         # scramble 90 + agility 90: the realism QB family
            m.uc.mem_write(copies["qb"] + 0x4F, b"\x5a")
            m.uc.mem_write(copies["qb"] + 0x37, b"\x5a")
        for slot, role in enumerate(("qb", "hb1", "fb", "hb2")):
            m.put(team + 8 + 4 * slot, copies[role])
        m.put(self.realism.TEAM_OFFENSE, team)              # the realism QB hook reads the offense summary
        seq = iter(picks)

        def lottery():
            self.assertEqual(m.reg("ESI"), team)
            m.ret(copies[next(seq)])
        m.leaf(0x00103360, lottery, reason="the retail carrier lottery's answers, replayed")
        patch_code(m, 0x00048BC0, b"\xb8" + struct.pack("<I", draw) + b"\xc3")
        if qb_roll is not None:                               # the match RNG's float for the realism QB draw
            patch_code(m, self.realism.FN_RAND, b"\x68" + struct.pack("<f", qb_roll) + b"\xd9\x04\x24\x58\xc3")
        m.call(0x00106CFA, esi=team, ebx=0x11111111, stop=0x00106D0F, budget=2000000)
        stored = m.get(0x00A971A4)
        self.assertEqual(stored, m.reg("EAX"))
        # the caller's EBX, EBP and ESI come back as the retail call leaves them (0x103360 saves them too); EDI is the
        # realism hook's replayed `mov edi, [0xA971A0]`
        self.assertEqual((m.reg("EBX"), m.reg("EBP"), m.reg("ESI")), (0x11111111, 0x44444444, team))
        self.assertEqual(m.reg("EDI"), m.get(0x00A971A0))
        return {v: k for k, v in copies.items()}.get(stored, hex(stored))

    def test_every_guard_path_hands_the_realism_hook_a_carrier_of_this_team(self):
        cases = (  # (lottery answers, league draw, lead back, expected carrier)
            (["hb1"], 65535, "healthy", "hb1"),               # HB chosen, kept
            (["hb1"], 65535, "injured", "hb2"),               # injured HB: the next healthy back
            (["hb1"], 0, "healthy", "hb2"),                   # HB chosen, the 2% rotation
            (["fb"], 0, "healthy", "fb"),                     # fullback keeps this one (draw below 4096)
            (["fb", "hb1"], 65535, "healthy", "hb1"),         # fullback rule: drawn again, a halfback
            (["fb", "hb1"], 65535, "injured", "hb2"),         # drawn again, an injured halfback: the next healthy one
            (["fb", "qb"], 65535, "healthy", "qb"),           # drawn again, the quarterback
            (["fb"] * 4, 65535, "healthy", "hb1"),            # the fullback every time: the HB1 slot
            (["fb"] * 4, 65535, "injured", "hb2"),            # ... hurt: the next healthy back
            (["qb"], 65535, "healthy", "qb"),
            (["wr"], 0, "healthy", "wr"),
        )
        for picks, draw, lead, expected in cases:
            with self.subTest(picks=picks, draw=draw, lead=lead):
                self.assertEqual(self.run_site(self.payload, picks, draw, lead), expected)

    def test_the_realism_qb_hook_still_runs_after_the_guard(self):
        # a mobile QB and a match draw of 0.0: the realism hook replaces whatever the guard returned
        for picks, draw, lead in ((["hb1"], 65535, "healthy"), (["fb", "hb1"], 65535, "injured"), (["fb"] * 4, 65535, "healthy")):
            with self.subTest(picks=picks):
                self.assertEqual(self.run_site(self.payload, picks, draw, lead, mobile_qb=True, qb_roll=0.0), "qb")
                self.assertNotEqual(self.run_site(self.payload, picks, draw, lead, mobile_qb=True, qb_roll=0.99), "qb")

    def test_halfback_paths_match_the_beta79_guard(self):
        # every path the fullback rule does not touch gives the same carrier as the shipped beta-79 guard
        for picks, draw, lead in ((["hb1"], 65535, "healthy"), (["hb1"], 65535, "injured"), (["hb1"], 0, "healthy"),
                                  (["qb"], 65535, "healthy"), (["wr"], 0, "healthy"), (["fb"], 0, "healthy")):
            with self.subTest(picks=picks, draw=draw, lead=lead):
                self.assertEqual(self.run_site(self.payload, picks, draw, lead),
                                 self.run_site(self.previous, picks, draw, lead))


if __name__ == "__main__":
    unittest.main()
