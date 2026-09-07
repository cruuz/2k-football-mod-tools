"""Native prerequisites for the in-game mode, not a simulated finished mode.

These probes execute the retail creator, allocator, menu stack and complete
season serializer. No test stub returns a fabricated MyCareer save or hub.
The original mode owner is composed only to reuse its bounded RW harness.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career as career
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, Machine, draft_save


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "Unicorn and pinned USA retail default.xbe required")
class ModeRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if XBE.stat().st_size > 16 * 1024**2:
            raise unittest.SkipTest("retail XBE evidence exceeds the 16 MiB bound")
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("USA retail XBE evidence pin differs")
        cls.payload = career.apply(retail)[0]

    def machine(self, save=None):
        return Machine(self.payload, draft_save() if save is None else save)

    def menu(self, m):
        manager, sheet = m.BODIES, m.BODIES + 0x1000
        m.put(manager + 0x100, 2)
        m.put(manager + 16, 0x56E9C4)
        m.put(manager + 0x10C, sheet)
        m.put(sheet + 0x65C + 0xBC, 0)
        # Only descriptor rendering/resource delivery is external here.
        m.stub(0x6E4E0, lambda: m.ret(pop=4))
        return manager

    def preserved(self, m):
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222),
                            ("EDI", 0x33333333), ("EBP", 0x44444444)):
            self.assertEqual(m.reg(name), value, name)

    def test_creator_allocates_primary_slot_and_enters_editor_without_a_disc_seed(self):
        m = self.machine()
        manager = self.menu(m)
        m.uc.mem_write(m.player + 8, b"\x01")  # unused native Create Player slot
        other_records = bytes(m.uc.mem_read(m.player - 7 * 84, 7 * 84))
        m.stub(0x48BC0, lambda: m.ret(0))  # RNG source, not a roster decision
        m.call(0x3461F0, ecx=manager, budget=20000)
        self.assertEqual(m.get(0xCB8B14), m.player)
        self.assertEqual(m.get(0xCB8B98), 1)
        self.assertEqual(m.get(manager + 0x100), 3)
        self.assertEqual(m.get(manager + 24), 0x56F050)
        self.assertEqual(m.get(m.player), m.get(m.root + 0x24))
        self.assertEqual(m.uc.mem_read(m.player - 7 * 84, 7 * 84), other_records)
        self.assertEqual(m.uc.mem_read(m.state, career.STATE_SIZE), bytes(career.STATE_SIZE))
        self.preserved(m)

    def test_creator_full_pool_refuses_without_pushing_or_mutating_records(self):
        m = self.machine()
        manager = self.menu(m)
        before = bytes(m.uc.mem_read(m.player - 7 * 84, 8 * 84))
        m.call(0x3461F0, ecx=manager, budget=20000)
        self.assertEqual(m.get(0xCB8B14), 0)
        self.assertEqual(m.get(manager + 0x100), 2)
        self.assertEqual(m.uc.mem_read(m.player - 7 * 84, 8 * 84), before)
        self.preserved(m)

    def test_creator_existing_player_selection_is_distinct_from_new_allocation(self):
        m = self.machine()
        manager = self.menu(m)
        m.uc.mem_write(m.player + 8, b"\x05")
        before = bytes(m.uc.mem_read(m.player, 84))
        m.call(0x3461F0, ecx=manager, budget=20000)
        self.assertEqual(m.get(0xCB8B14), m.player)
        self.assertEqual(m.get(0xCB8B98), 0)
        self.assertEqual(m.uc.mem_read(m.player, 84), before)
        self.assertEqual(m.get(manager + 24), 0x56F050)

    def test_complete_season_serializer_preserves_128_byte_tail(self):
        # Preservation is proved. Vacancy/ownership is deliberately NOT inferred
        # from this probe; no production writer allocates this opaque tail.
        for pattern in (bytes(128), bytes(range(128)), b"\xff" * 128):
            with self.subTest(pattern=pattern[:4].hex()):
                save = bytearray(draft_save())
                start = fs.SEASON_BLOCK + fs.S_TAIL
                save[start:start + 128] = pattern
                m = self.machine(bytes(save))
                original = bytes(m.uc.mem_read(m.SAVE, len(save)))
                m.call(0xC5800, ecx=m.SAVE + fs.SEASON_BLOCK, budget=200000)
                self.assertEqual(m.uc.mem_read(0xE5FB80, 128), pattern)
                destination = m.BODIES + 16
                m.uc.mem_write(destination - 16, b"\xa5" * (fs.SEASON_BLOCK_SIZE + 32))
                m.call(0xC5310, ecx=destination, budget=200000)
                self.assertEqual(m.uc.mem_read(destination + fs.S_TAIL, 128), pattern)
                self.assertEqual(m.uc.mem_read(destination - 16, 16), b"\xa5" * 16)
                self.assertEqual(m.uc.mem_read(destination + fs.SEASON_BLOCK_SIZE, 16), b"\xa5" * 16)
                self.assertEqual(m.uc.mem_read(m.SAVE, len(save)), original)
                self.preserved(m)

    def test_empty_season_serializer_clears_tail_so_it_is_not_unconditional_storage(self):
        m = self.machine()
        m.put(0xE576A8, 3)
        m.uc.mem_write(m.BODIES, b"\xa5" * fs.SEASON_BLOCK_SIZE)
        m.call(0xC5310, ecx=m.BODIES, budget=30000)
        result = bytearray(fs.SEASON_BLOCK_SIZE)
        result[2] = 3
        self.assertEqual(m.uc.mem_read(m.BODIES, len(result)), result)

    def test_native_franchise_options_advance_calls_initializers_before_league_screen(self):
        for allowed in (0, 1):
            with self.subTest(allowed=allowed):
                m = self.machine()
                manager = self.menu(m)
                calls = []
                # This proves the native call order and destination, not the
                # internal roster/default/schedule work of these services.
                m.stub(0x148AB0, lambda: m.ret(allowed))
                for address in (0x10EA10, 0x13EE10):
                    m.stub(address, lambda a=address: (calls.append(a), m.ret()))
                m.call(0x148CC0, ecx=manager, budget=500)
                self.assertEqual(calls, [0x10EA10, 0x13EE10] if allowed else [])
                self.assertEqual(m.get(manager + 0x100), 3 if allowed else 2)
                if allowed:
                    self.assertEqual(m.get(manager + 24), 0x52ABE0)
                self.preserved(m)

    def test_coach_mode_predicate_does_not_supply_a_skip_primitive(self):
        m = self.machine()
        for mode in range(8):
            for fpp in (0, 1):
                m.put(0xE5FF80, mode)
                m.put(0xE5FFE4, fpp)
                m.put(0xE6002C, 1)
                self.assertEqual(m.call(0x63810), int(mode not in (0, 3) and not fpp))


if __name__ == "__main__":
    unittest.main()
