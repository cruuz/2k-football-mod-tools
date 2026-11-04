"""b780 mc1: boot save-list type guard (EMU1 crash_boot: bugcheck 0x1E at 0x30C40 while the title lists saved games).

Static: the two in-place sites (the 0x16A600 prologue redirect and the 15-byte routine in the 0x160771 alignment
padding), idempotent apply, a non-retail padding refused, no allocation. Native (Unicorn, pinned USA retail
executable): the save-type matcher 0x16A600 returns the same index for every one of the 14 real type strings with and
without the guard; a NULL type string faults at 0x30C40 on retail and returns 0 (no match) with the guard. Composes
with MyCareer and Career Home in either order.
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


class StaticTests(unittest.TestCase):
    def test_sites_and_routine(self):
        import capstone
        (_, site, before, after), (_, cave_va, cave_old, cave) = guard.SITES
        self.assertEqual((site, before, cave_va, cave_old), (MATCH, bytes.fromhex("5633f6eb0b"), 0x160771, b"\x90" * 15))
        self.assertEqual(site + 5 + struct.unpack_from('<i', after, 1)[0], cave_va)
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        code = [(i.address, i.mnemonic, i.op_str) for i in md.disasm(cave, cave_va)]
        self.assertEqual(code, [(0x160771, 'test', 'edi, edi'), (0x160773, 'je', '0x16077d'),
                                (0x160775, 'push', 'esi'), (0x160776, 'xor', 'esi, esi'),
                                (0x160778, 'jmp', '0x16a610'), (0x16077d, 'xor', 'eax, eax'), (0x16077f, 'ret', '')])

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


if __name__ == '__main__':
    unittest.main()
