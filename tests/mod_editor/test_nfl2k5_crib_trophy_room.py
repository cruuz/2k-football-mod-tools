"""b778-xs1: the Crib keeps only the Trophy Room side (catalog popup skipped, the two shop rows removed)."""
from pathlib import Path
import importlib.util
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_crib_trophy_room as crib
from mod_editor.core import mod_build
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_my_career_fixture import XBE


def label(image, va):
    return image.read(va, 64).decode("utf-16-le", "replace").split("\0")[0]


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class CribTrophyRoomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.applied, cls.receipt = crib.apply(cls.retail)

    def test_status_edits_and_replay(self):
        self.assertEqual((crib.status(self.retail), crib.status(self.applied)), ("retail", "applied"))
        image = XbeImage(self.applied)
        self.assertEqual(image.read(0x277185, 2), bytes.fromhex("eb0e"))   # entering always goes to the room (state 3)
        self.assertEqual(image.read(0x2771FF, 2), bytes.fromhex("6a03"))   # first visit continues to the room
        self.assertEqual(crib.apply(self.applied)[0], self.applied)
        self.assertEqual(self.receipt["changed_bytes"], sum(a != b for a, b in zip(self.retail, self.applied)))
        from mod_editor.core.nfl2k5_bump_strength import _sections
        digests = [(x.header_offset + 36, x.header_offset + 56) for x in _sections(self.applied)]
        lo = image.offset(crib.OPTIONS, 6 * crib.ROW)
        sites = {image.offset(0x277185), image.offset(0x277185) + 1, image.offset(0x2771FF), image.offset(0x2771FF) + 1}
        sites |= {image.offset(va) + k for va in crib.OWNED_CALLS for k in range(5)}
        sites |= {image.offset(crib.SET_STATE[1]) + k for k in range(6)}
        sites |= {image.offset(crib.GATE_VA) + k for k in range(len(crib.gate_code()))}
        for i, (a, b) in enumerate(zip(self.retail, self.applied)):
            if a != b:
                self.assertTrue(i in sites or lo <= i < lo + 6 * crib.ROW or any(x <= i < y for x, y in digests), hex(i))

    def test_crib_owns_nothing_but_the_unlockables_check_is_kept(self):
        retail, applied = XbeImage(self.retail), XbeImage(self.applied)
        for va in crib.OWNED_CALLS:
            self.assertEqual(retail.read(va, 5), crib.owned_call(va))      # call 0x13FBA0 in retail
            self.assertEqual(applied.read(va, 5), bytes.fromhex("83c40431c0"))  # add esp, 4 ; xor eax, eax
            self.assertTrue(0x26C000 <= va < 0x27E000)                       # all inside the Crib module
        self.assertEqual(applied.read(0x10E912, 5), retail.read(0x10E912, 5))  # teams/stadiums/movies unlock check
        self.assertEqual(len(crib.OWNED_CALLS), 16)

    @unittest.skipUnless(importlib.util.find_spec("unicorn"), "Unicorn absent")
    def test_state_gate_turns_every_item_screen_into_the_room(self):
        import unicorn as uc
        from unicorn import x86_const as x86
        image = XbeImage(self.applied)
        hook = image.read(crib.SET_STATE[1], 6)
        self.assertEqual(crib.SET_STATE[1] + 5 + struct.unpack_from("<i", hook, 1)[0], crib.GATE_VA)
        body = image.read(crib.GATE_VA, len(crib.gate_code()))
        resume = crib.SET_STATE_RESUME
        for state in range(0, 40):
            m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
            m.mem_map(0x274000, 0x1000); m.mem_write(crib.GATE_VA, body)
            m.mem_map(0x276000, 0x1000); m.mem_write(resume, b"\xf4")
            m.mem_map(0x3000000, 0x10000)
            esp = 0x3008000
            m.mem_write(esp, struct.pack("<II", 0x11223344, state))     # return address, the requested state
            m.reg_write(x86.UC_X86_REG_ESP, esp)
            m.reg_write(x86.UC_X86_REG_EAX, 0xCAFE0000 + state)
            m.reg_write(x86.UC_X86_REG_ECX, 0x5150)
            m.reg_write(x86.UC_X86_REG_EBP, 0x77)
            try:
                m.emu_start(crib.GATE_VA, resume, count=40)
            except uc.UcError:
                pass
            self.assertEqual(m.reg_read(x86.UC_X86_REG_EIP), resume, state)
            # after the replayed prologue: [ebp] = saved ebp, [ebp+4] = return address, [ebp+8] = the state
            ebp = m.reg_read(x86.UC_X86_REG_EBP)
            got = struct.unpack("<I", bytes(m.mem_read(ebp + 8, 4)))[0]
            self.assertEqual(got, 3 if state in crib.CUT_STATES else state, state)
            self.assertEqual(struct.unpack("<I", bytes(m.mem_read(ebp, 4)))[0], 0x77)
            self.assertEqual((m.reg_read(x86.UC_X86_REG_EAX), m.reg_read(x86.UC_X86_REG_ECX)), (0xCAFE0000 + state, 0x5150))
        self.assertEqual(set(crib.CUT_STATES) & {6, 7, 10, 11, 17}, set())   # trophies, user card, milestones stay

    def test_rebuild_drops_the_four_game_files_only_with_the_cut(self):
        from mod_editor.core import nfl2k5_crib_reclaim as reclaim
        self.assertEqual(set(reclaim._cuts(False)), {i for i, *_ in reclaim.MOVIES})
        cuts = reclaim._cuts(True)
        self.assertEqual(set(cuts) - {i for i, *_ in reclaim.MOVIES}, {4249, 4250, 4264, 4271})
        self.assertTrue(all(cuts[i] == reclaim.GAME_TOMBSTONE for i in (4249, 4250, 4264, 4271)))
        self.assertEqual(sum(size for _i, _n, size, _d in reclaim.GAMES), 7274432)
        self.assertFalse(reclaim._games_wanted(self.retail))
        self.assertTrue(reclaim._games_wanted(self.applied))

    def test_options_keep_user_card_milestones_and_exit(self):
        retail, applied = XbeImage(self.retail), XbeImage(self.applied)
        rows = lambda img: [(struct.unpack_from("<I", img.read(crib.OPTIONS + i * crib.ROW, 4))[0],
                             struct.unpack_from("<I", img.read(crib.OPTIONS + i * crib.ROW + 4, 4))[0]) for i in range(6)]
        self.assertEqual([label(retail, l) for k, l in rows(retail)[:5]],
                         ["User Card", "Catalogs", "Crib Items", "Milestone Info", "Exit"])
        after = rows(applied)
        self.assertEqual([k for k, _ in after[:4]], [0, 0, 9, 3])
        self.assertEqual([label(applied, l) for _, l in after[:3]], ["User Card", "Milestone Info", "Exit"])
        self.assertFalse(any(applied.read(crib.OPTIONS + 4 * crib.ROW, 2 * crib.ROW)))
        # the kept rows are the retail rows byte for byte (submenus and the Exit action unchanged)
        for new, old in ((0, 0), (1, 3), (2, 4)):
            self.assertEqual(applied.read(crib.OPTIONS + new * crib.ROW, crib.ROW), retail.read(crib.OPTIONS + old * crib.ROW, crib.ROW))

    def test_foreign_and_mixed_refuse(self):
        image = XbeImage(self.applied)
        for va in (0x277185, 0x2771FF, crib.OPTIONS + 4):
            bad = bytearray(self.applied)
            bad[image.offset(va)] ^= 1
            with self.subTest(va=hex(va)):
                self.assertEqual(crib.status(bytes(bad)), "foreign")
                with self.assertRaises(ValueError):
                    crib.apply(bytes(bad))
        mixed = bytearray(self.retail)
        mixed[XbeImage(self.retail).offset(0x277185)] = 0xEB
        self.assertEqual(crib.status(bytes(mixed)), "foreign")

    def test_build_option_presets(self):
        self.assertFalse(mod_build.BuildPlan.__dataclass_fields__["crib_trophy_room"].default)
        for name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
            self.assertTrue(mod_build.PRESETS[name]["crib_trophy_room"], name)


if __name__ == "__main__":
    unittest.main()
