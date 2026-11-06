"""b780 mc1: boot save-list guard (EMU1 crash_boot: a save whose name does not match its folder id faults the title
list builder 0x16AC40, at the type compare 0x30C40 or the name length 0x30A60).

Static: the four in-place sites (the 0x16A600 prologue redirect + its 15-byte routine at 0x160771, and the 0x16AD0D
name-length call redirect + its 12-byte routine at 0x160354), idempotent apply, a non-retail padding refused, no
allocation. Native (Unicorn, pinned USA retail executable): the type matcher 0x16A600 returns the same index for every
one of the 14 real type strings with and without the guard, and a NULL type string faults at 0x30C40 on retail and
returns 0 with the guard; the name-length guard at 0x160354 returns the real length for a real name and 0 for a NULL
name (where retail's 0x30A60 faults). Composes with MyCareer and Career Home in either order.
"""
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_save_list_type_guard as guard  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, XBE  # noqa: E402

TYPE_TABLE = 0xAA3398
MATCH, MATCH_BODY, COMPARE = 0x16A600, 0x16A610, 0x30C40
NAME_CALL, NAME_FN = 0x16AD0D, 0x30A60


class StaticTests(unittest.TestCase):
    def test_sites_and_routines(self):
        import capstone
        (_, site, before, after), (_, cave_va, cave_old, cave), \
            (_, name_site, name_before, name_after), (_, cave2_va, cave2_old, cave2) = guard.SITES
        self.assertEqual((site, before, cave_va, cave_old), (MATCH, bytes.fromhex("5633f6eb0b"), 0x160771, b"\x90" * 15))
        self.assertEqual(site + 5 + struct.unpack_from('<i', after, 1)[0], cave_va)
        self.assertEqual((name_site, cave2_va, cave2_old), (NAME_CALL, 0x160354, b"\x90" * 12))
        self.assertEqual(name_before, bytes.fromhex("e84e5decff"))
        self.assertEqual(name_site + 5 + struct.unpack_from('<i', name_before, 1)[0], NAME_FN)
        self.assertEqual(name_site + 5 + struct.unpack_from('<i', name_after, 1)[0], cave2_va)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        code = [(i.address, i.mnemonic, i.op_str) for i in md.disasm(cave, cave_va)]
        self.assertEqual(code, [(0x160771, 'test', 'edi, edi'), (0x160773, 'je', '0x16077d'),
                                (0x160775, 'push', 'esi'), (0x160776, 'xor', 'esi, esi'),
                                (0x160778, 'jmp', '0x16a610'), (0x16077d, 'xor', 'eax, eax'), (0x16077f, 'ret', '')])
        code2 = [(i.address, i.mnemonic, i.op_str) for i in md.disasm(cave2, cave2_va)]
        self.assertEqual(code2, [(0x160354, 'test', 'ecx, ecx'), (0x160356, 'je', '0x16035d'),
                                 (0x160358, 'jmp', '0x30a60'), (0x16035d, 'xor', 'eax, eax'), (0x16035f, 'ret', '')])

    def test_in_place_on_in_every_preset_and_at_64_mb(self):
        from mod_editor.core import mod_build, nfl2k5_memory_budget as mb, nfl2k5_xbe_space as space
        self.assertNotIn(guard.OWNER, space.LATE_OWNERS)
        self.assertFalse(hasattr(guard, "REQUESTS"))
        for name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
            self.assertIs(mod_build.PRESETS[name]["save_list_type_guard"], True, name)
        self.assertIn("save_list_type_guard", mb.PROFILE_64_ON)
        self.assertIs(mb.profile_64_plan(None).get("save_list_type_guard"), True)

    @unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required')
    def test_apply_status_and_replay(self):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        retail = retail_bytes()
        self.assertEqual(guard.status(retail), 'retail')
        patched, _ = guard.apply(retail)
        self.assertEqual(guard.status(patched), 'applied')
        self.assertEqual(len(patched), len(retail))
        self.assertEqual(guard.apply(patched)[0], patched)
        moved = bytearray(retail)
        moved[rdata.offset_of(retail, guard.CAVE_VA + 2)] ^= 0xFF
        self.assertEqual(guard.status(bytes(moved)), 'foreign')
        with self.assertRaises(ValueError):
            guard.apply(bytes(moved))

    @unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required')
    def test_composes_with_mycareer_either_order(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_my_career_home as home
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        retail = retail_bytes()
        after = guard.apply(home.apply(mode.apply(retail)[0])[0])[0]
        before = home.apply(mode.apply(guard.apply(retail)[0])[0])[0]
        self.assertEqual(after, before)
        self.assertEqual((guard.status(after), mode.status(after), home.status(after)), ('applied',) * 3)


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE and Unicorn required')
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        cls.retail = retail_bytes()
        cls.guarded = guard.apply(cls.retail)[0]

    def _matcher(self, payload, edi):
        import unicorn as u
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDI, UC_X86_REG_EIP
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        img = XbeImage(payload)
        uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        lo = min(s.start for s in img.sections)
        top = max(s.start + s.size for s in img.sections)
        uc.mem_map(lo & ~0xFFF, (top - lo + 0x1FFF) & ~0xFFF)
        for s in img.sections:
            uc.mem_write(s.start, img.read(s.start, min(s.size, s.raw_size)))
        uc.mem_map(0x1FF0000, 0x20000)
        uc.mem_map(0x5000000, 0x1000)
        uc.mem_write(0x5000000, b"\xc3")
        uc.reg_write(UC_X86_REG_ESP, 0x2000000 - 0x400)
        uc.mem_write(0x2000000 - 0x400, struct.pack('<I', 0x5000000))
        uc.reg_write(UC_X86_REG_EDI, edi)
        uc.reg_write(UC_X86_REG_EAX, 0)
        try:
            uc.emu_start(MATCH, 0x5000000, count=200000)
            return uc.reg_read(UC_X86_REG_EAX)
        except u.UcError:
            return ('fault', hex(uc.reg_read(UC_X86_REG_EIP)))

    def _typeptr(self, payload, i):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        return struct.unpack('<I', XbeImage(payload).read(TYPE_TABLE + 4 * i, 4))[0]

    def test_every_real_type_string_matches_identically(self):
        for i in range(14):
            self.assertEqual(self._matcher(self.retail, self._typeptr(self.retail, i)), i)
            self.assertEqual(self._matcher(self.guarded, self._typeptr(self.guarded, i)), i)

    def test_a_null_type_string_faults_on_retail_and_is_guarded(self):
        self.assertEqual(self._matcher(self.retail, 0), ('fault', hex(COMPARE)))
        self.assertEqual(self._matcher(self.guarded, 0), 0)

    def _name_guard(self, ecx):
        """The name-length routine the builder now calls at 0x16AD0D (0x160354 on the guarded exe)."""
        import unicorn as u
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        img = XbeImage(self.guarded)
        uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        lo = min(s.start for s in img.sections)
        top = max(s.start + s.size for s in img.sections)
        uc.mem_map(lo & ~0xFFF, (top - lo + 0x1FFF) & ~0xFFF)
        for s in img.sections:
            uc.mem_write(s.start, img.read(s.start, min(s.size, s.raw_size)))
        uc.mem_map(0x1FF0000, 0x20000)
        uc.mem_map(0x5000000, 0x1000)
        uc.mem_write(0x5000000, b"\xc3")
        uc.mem_write(0x1FF8000, "Mycareer\x00".encode('utf-16-le'))
        uc.reg_write(UC_X86_REG_ESP, 0x2000000 - 0x400)
        uc.mem_write(0x2000000 - 0x400, struct.pack('<I', 0x5000000))
        uc.reg_write(UC_X86_REG_ECX, ecx)
        uc.reg_write(UC_X86_REG_EAX, 0)
        try:
            uc.emu_start(guard.CAVE2_VA, 0x5000000, count=200000)
            return uc.reg_read(UC_X86_REG_EAX)
        except u.UcError:
            return ('fault', hex(uc.reg_read(UC_X86_REG_EIP)))

    def test_name_length_guard_returns_length_or_zero(self):
        # retail's 0x30A60 faults on a NULL name; the guarded builder calls 0x160354 instead
        import unicorn as u
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EIP
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        img = XbeImage(self.retail)
        uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        lo = min(s.start for s in img.sections)
        uc.mem_map(lo & ~0xFFF, (max(s.start + s.size for s in img.sections) - lo + 0x1FFF) & ~0xFFF)
        for s in img.sections:
            uc.mem_write(s.start, img.read(s.start, min(s.size, s.raw_size)))
        uc.mem_map(0x1FF0000, 0x20000)
        uc.mem_map(0x5000000, 0x1000)
        uc.mem_write(0x5000000, b"\xc3")
        uc.reg_write(UC_X86_REG_ESP, 0x2000000 - 0x400)
        uc.mem_write(0x2000000 - 0x400, struct.pack('<I', 0x5000000))
        uc.reg_write(UC_X86_REG_ECX, 0)
        try:
            uc.emu_start(NAME_FN, 0x5000000, count=200000)
            retail_null = 'no fault'
        except u.UcError:
            retail_null = ('fault', hex(uc.reg_read(UC_X86_REG_EIP)))
        self.assertEqual(retail_null, ('fault', hex(NAME_FN)))
        self.assertEqual(self._name_guard(0x1FF8000), 8)   # len("Mycareer")
        self.assertEqual(self._name_guard(0), 0)           # NULL name: no fault, empty


@unittest.skipUnless(HAVE_UC and XBE.is_file(), 'pinned USA XBE, retail ROST and Unicorn required')
class RealFlowTests(unittest.TestCase):
    """b780 mc1: a cut free-agent MyPlayer save (no human-controlled club) that the game itself writes has a matching
    name/folder, so it does NOT trigger the save-list crash; it cold-loads into Career Home. The crash needs a
    name/folder mismatch, which only hand-copied or tool-made saves have; the guard covers those. This test confirms
    the ordinary game-written save still loads with the guard present."""

    def test_cut_free_agent_save_loads_into_career_home(self):
        from mod_editor.core import nfl2k5_my_career_mode as mode, nfl2k5_my_career_home as home
        from mod_editor.core import nfl2k5_injured_reserve as ir
        from tests.nfl2k5_supersim_draft_fixture import retail_bytes
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        from tests.mod_editor.test_nfl2k5_my_career_mc1 import release
        from tests.nfl2k5_my_career_home_fixture import Machine as Home
        from tests.nfl2k5_my_career_played_fixture import Machine as Played
        payload = guard.apply(ir.apply(home.apply(mode.apply(retail_bytes())[0])[0])[0])[0]
        self.assertEqual((mode.status(payload), home.status(payload), ir.status(payload), guard.status(payload)),
                         ('applied',) * 4)
        roster = retail_roster()
        m = Home(payload)
        p = m.create(roster, club=15, position=0, preseason=False)
        m.child_services()
        release(m, p, 15)
        self.assertEqual(m.get(m.state + 24), 4)
        self.assertEqual([i for i in range(34) if m.get(0xE5775C + 4 * i)], [], 'a free agent has no human club')
        saved = m.native_save(budget=1000000000)
        m.close()
        c = Played(payload)
        c.cold(roster, saved)
        self.assertEqual(c.top(), c.labels['apartment'], 'the cut free-agent save opens Career Home')
        self.assertEqual(c.get(c.state + 24), 4)
        c.close()


if __name__ == '__main__':
    unittest.main()
