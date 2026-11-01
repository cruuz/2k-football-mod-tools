"""b778 fa6: the capacity disc's franchise save/list/load path.

The retail writer already sizes itself from [0xB72808]; this suite pins the two places that did
not follow the capacity arena (the save-list admission size and the load path's wrapper-size
answer) and the old-save migration into the 0xB0000 in-memory arena. Native tests execute the
real functions from the pinned USA XBE; private saves/discs are skipped when absent.

b779 ag1: the capacity arena is nfl2k5_roster_arena.CAPACITY_ARENA_SIZE (0xCA000); beta-78's 0xB0000 saves
(847,020 / 847,148) are admitted, report their own wrapper size and load into the bigger arena.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_k128 as k128
from mod_editor.core import nfl2k5_my_career_mode as mc
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_roster_arena_growth as growth
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_xbe_space as space

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
                          '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'
HUB = Path(os.environ.get('NFL2K5_SAVE_FIXTURES', '/home/noah/Desktop/2K5-8 Editors/save_fixtures'))
SAVE = HUB / 'f0/UDATA/53450030/0B8506889D40/SAVEGAME.DAT'
RECORDS = 612
CAPACITY_TOTAL = arena.CAPACITY_SAVE_SIZE
LEGACY_TOTAL = arena.LEGACY_CAPACITY_SAVE_SIZE


def _unicorn():
    return importlib.util.find_spec('unicorn') is not None


@unittest.skipUnless(XBE.is_file() and _unicorn(), 'native capacity save proofs need the pinned USA XBE and Unicorn')
class CapacitySavePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.mod_editor import test_nfl2k5_roster_arena_growth as growth_tests
        if not (XBE.parent / 'vc_53450030/0').is_file():
            raise unittest.SkipTest('capacity save proof requires the preserved ROST pack')
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(XBE.parent)
        cls.retail = XBE.read_bytes()
        cls.xbe, _ = growth.apply(cls.retail, reserves_16=False, capacity=True)
        from mod_editor.core import nfl2k5_team_history as history
        with history._outer_image()(XBE.parent) as archive:
            entry = history._entry(archive)
            retail_rost = archive.read(entry.virtual_offset, entry.size)
        cls.rost, _ = arena.migrate(retail_rost, reserves_16=False, capacity_records=RECORDS)
        cls.body = cls.rost[0x20:]
        cls.site = growth.allocation(cls.xbe)
        cls.labels = {name: cls.site['va'] + offset for name, offset in growth.assembly.CAPACITY_LABELS.items()}
        cls.machine_class = growth_tests.BootPathTests
        cls.file = 0x05000000

    def _machine(self):
        base = self.machine_class('test_retail_pair_loads_through_the_boot_path')
        base.machine(self.xbe)
        base.uc.mem_map(self.file, 0x200000)
        self.assertTrue(base.boot(self.rost)[0])
        root = base.word(0xB72918)
        teams = base.word(root + 0x1C)
        for at, value in ((0xE576A0, 1), (0xE576A4, 7), (0xE576AC, 32)):
            base.put(at, value)
        for i in range(32):
            base.put(0xE5786C + 4 * i, teams + 500 * i)
        base.uc.mem_write(0xE5775C, bytes(32 * 4))
        base.uc.mem_write(0xE421E0, bytes(160 * 4))
        return base

    def _call_esi(self, base, address, esi, *, budget=20000):
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP
        base.uc.mem_write(base.STACK, struct.pack('<I', base.STOP))
        base.uc.reg_write(UC_X86_REG_ESP, base.STACK)
        base.uc.reg_write(UC_X86_REG_ESI, esi)
        base.uc.reg_write(UC_X86_REG_EAX, 0)
        base.uc.emu_start(address, base.STOP, count=budget)
        self.assertEqual(base.uc.reg_read(UC_X86_REG_EIP), base.STOP)
        return base.uc.reg_read(UC_X86_REG_EAX)

    def _damaged(self, base, size):
        base.put(0xbdc1d4, 9)            # metadata slot 0 is Franchise
        base.put(0xbdc1cc, size)
        return base.call(0x16AB70)

    def test_total_size_and_native_writer_follow_the_capacity_arena(self):
        base = self._machine()
        self.assertEqual((base.word(0xB72808), base.word(0xB7280C)),
                         (arena.CAPACITY_ARENA_SIZE, arena.CAPACITY_ARENA_SIZE))
        self.assertEqual(base.call(0xBFE50), arena.CAPACITY_ARENA_SIZE + 0x40)
        self.assertEqual(base.call(0x16A0F0), arena.CAPACITY_ARENA_SIZE + 0x40)
        self.assertEqual(base.call(0x16AA10), CAPACITY_TOTAL)
        base.call(0xC1F90, ecx=base.HEAP + 0x300000, budget=12000000)
        self.assertEqual(base.word(base.HEAP + 0x300000 + 4), arena.CAPACITY_ARENA_SIZE + 0x20)
        self.assertEqual(base.word(base.HEAP + 0x300000 + 4), arena.CAPACITY_ARENA_SIZE + 0x20)
        self.assertEqual(base.word(base.HEAP + 0x300000 + 48), 1)
        self.assertEqual(base.call(0x16AA10), CAPACITY_TOTAL)

    def test_save_list_admits_every_pre_capacity_size(self):
        base = self._machine()
        self.assertEqual((LEGACY_TOTAL, CAPACITY_TOTAL), (847020, 953516))
        for size in (720044, 720172, LEGACY_TOTAL, LEGACY_TOTAL + 128, CAPACITY_TOTAL):
            self.assertEqual(self._damaged(base, size), 0, f'{size} was marked damaged')
        for size in (719000, 720043, 720045, 720171, 720173, 847019, 847021, 847147, 847149,
                     CAPACITY_TOTAL - 1, CAPACITY_TOTAL + 1, CAPACITY_TOTAL + 128, 0):
            self.assertEqual(self._damaged(base, size), 1, f'{size} was admitted')
        # 724140/724268 are the 16-reserve layouts; that experimental option refuses capacity
        # growth, so this capacity build does not claim them.
        self.assertEqual(self._damaged(base, 724140), 1)
        self.assertEqual(self._damaged(base, 724268), 1)

    def test_load_path_reads_an_old_saves_suffix_at_its_own_offset(self):
        base = self._machine()
        shim = self.labels['capacity_load_size']
        for declared, expected in ((0x91020, 0x91040), (0x92020, 0x92040), (0xB0020, 0xB0040)):
            base.uc.mem_write(self.file, bytes(0x1000))
            base.uc.mem_write(self.file + 0x2E4, struct.pack('<I', declared))
            self.assertEqual(self._call_esi(base, shim, self.file), expected)
        base.uc.mem_write(self.file + 0x2E4, struct.pack('<I', arena.CAPACITY_ARENA_SIZE + 0x20))
        self.assertEqual(self._call_esi(base, shim, self.file), arena.CAPACITY_ARENA_SIZE + 0x40)

    def test_old_save_loads_into_the_capacity_arena_and_resaves_at_the_new_size(self):
        if not SAVE.is_file():
            self.skipTest(f'preserved old save absent: {SAVE}')
        source = SAVE.read_bytes()
        self.assertEqual(len(source), 720044)
        from tests.mod_editor import test_nfl2k5_roster_arena_growth as growth_tests
        base = growth_tests.NativeTests('test_native_old_save_load_migrates_auxiliary_tail')
        base.patched, base.body = self.xbe, self.body
        base.setUp()
        base.put(0xB72808, arena.CAPACITY_ARENA_SIZE)
        base.put(0xB7280C, arena.CAPACITY_ARENA_SIZE)
        base.uc.mem_map(self.file, 0x200000)
        base.uc.mem_write(self.file, source)
        import unicorn as uni
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP
        refresh = (0x77AE0, 0x77B20, 0x77A90, 0x77AB0, 0x77B00, 0x77470)
        def service(uc, _address, _size, _data):
            esp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, base.word(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
        hook = base.uc.hook_add(uni.UC_HOOK_CODE, service, begin=min(refresh), end=max(refresh))
        try:
            base.uc.mem_write(base.OUT, source[fs.ARENA_WRAPPER:fs.ARENA_END])
            base.call(0xC2040, ecx=base.OUT, budget=12000000)
        finally:
            base.uc.hook_del(hook)
        root = base.word(0xB72918)
        self.assertEqual(base.word(0xB7280C), arena.CAPACITY_ARENA_SIZE - 366)
        self.assertEqual(base.call(self.labels['integrity']), 1)
        self.assertEqual(bytes(base.uc.mem_read(root + arena.CAPACITY_ARENA_SIZE - 366, 366)),
                         source[fs.ARENA_END - 366:fs.ARENA_END])
        # The load path's season/front-office offsets still address the old buffer.
        self.assertEqual(self._call_esi(base, self.labels['capacity_load_size'], self.file), 0x91040)
        self.assertEqual(self.file + 0x2E0 + 0x91040, self.file + 0x91320)
        # A save from this loaded state is the capacity size and version 1.
        base.call(0xC1F90, ecx=base.OUT, budget=12000000)
        self.assertEqual(base.word(base.OUT + 4), arena.CAPACITY_ARENA_SIZE + 0x20)
        self.assertEqual(base.word(base.OUT + 48), 1)
        self.assertEqual(base.call(0x16AA10), CAPACITY_TOTAL)

    def test_beta78_capacity_save_loads_into_the_larger_arena_with_its_records(self):
        # b779 ag1: a beta-78 save (0xB0000 arena, 847,020 bytes, the descriptor and empty block 0x400 before its
        # end) loads into the current arena: records, history and the auxiliary tail stay where they are, the block
        # and descriptor move to the new end, the load path reads its suffix at 0xB0040, and a resave is the new size.
        if not SAVE.is_file():
            self.skipTest(f'preserved old save absent: {SAVE}')
        retail_save = SAVE.read_bytes()
        source, _ = arena._migrate_capacity(retail_save, RECORDS, class_records=0,
                                            arena_size=arena.LEGACY_CAPACITY_ARENA_SIZE)
        self.assertEqual(len(source), LEGACY_TOTAL)
        old = codec.decode(source)
        # b779 hn1 keeps its champions history in the 448 spare bytes after the reserve block (arena end - 0x400 + 352);
        # a pattern in the part the auxiliary tail does not use must arrive at the same distance from the new end.
        aux = struct.unpack_from('<I', source, fs.ARENA_WRAPPER + 8)[0]
        gap = old.layout.root + arena.LEGACY_CAPACITY_BLOCK_OFFSET + arena.BLOCK_SIZE
        gap_end = old.layout.end - aux
        self.assertGreater(gap_end - gap, 200)
        pattern = bytes((7 * i + 1) & 0xFF or 1 for i in range(gap_end - gap))
        source = source[:gap] + pattern + source[gap_end:]
        old = codec.decode(source)
        self.assertEqual(old.layout.arena_size, arena.LEGACY_CAPACITY_ARENA_SIZE)
        descriptor = arena.capacity_descriptor(source, old.layout)
        from tests.mod_editor import test_nfl2k5_roster_arena_growth as growth_tests
        base = growth_tests.NativeTests('test_native_old_save_load_migrates_auxiliary_tail')
        base.patched, base.body = self.xbe, self.body
        base.setUp()
        base.put(0xB72808, arena.CAPACITY_ARENA_SIZE)
        base.put(0xB7280C, arena.CAPACITY_ARENA_SIZE)
        base.uc.mem_map(self.file, 0x200000)
        base.uc.mem_write(self.file, source)
        import unicorn as uni
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP
        refresh = (0x77AE0, 0x77B20, 0x77A90, 0x77AB0, 0x77B00, 0x77470)
        def service(uc, _address, _size, _data):
            esp = uc.reg_read(UC_X86_REG_ESP)
            uc.reg_write(UC_X86_REG_EIP, base.word(esp))
            uc.reg_write(UC_X86_REG_ESP, esp + 4)
        hook = base.uc.hook_add(uni.UC_HOOK_CODE, service, begin=min(refresh), end=max(refresh))
        growth_bytes = arena.LEGACY_CAPACITY_ARENA_SIZE - arena.RETAIL_SIZE
        try:
            base.uc.mem_write(base.OUT, source[fs.ARENA_WRAPPER:fs.ARENA_END + growth_bytes])
            base.call(0xC2040, ecx=base.OUT, budget=12000000)
        finally:
            base.uc.hook_del(hook)
        root = base.word(0xB72918)
        self.assertNotEqual(root, 0)
        aux = struct.unpack_from('<I', source, fs.ARENA_WRAPPER + 8)[0]
        self.assertEqual(base.word(0xB7280C), arena.CAPACITY_ARENA_SIZE - aux)
        self.assertEqual(base.call(self.labels['integrity']), 1)
        self.assertEqual(base.word(root), old.tables['primary'].count)
        # The load path's season/front-office offsets still address the old buffer.
        self.assertEqual(self._call_esi(base, self.labels['capacity_load_size'], self.file), 0xB0040)
        # A save from this loaded state is the current capacity size and version 1, and decodes with its records.
        base.call(0xC1F90, ecx=base.OUT, budget=12000000)
        self.assertEqual(base.word(base.OUT + 4), arena.CAPACITY_ARENA_SIZE + 0x20)
        self.assertEqual(base.word(base.OUT + 48), 1)
        self.assertEqual(base.call(0x16AA10), CAPACITY_TOTAL)
        resaved = bytes(base.uc.mem_read(base.OUT, 0x20 + 0x20 + arena.CAPACITY_ARENA_SIZE))
        again = codec.decode(bytes(source[:fs.ARENA_WRAPPER]) + resaved)
        self.assertEqual(again.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
        self.assertEqual(again.tables['primary'].count, old.tables['primary'].count)
        self.assertEqual(arena.capacity_descriptor(again.original, again.layout), descriptor)
        old_arena = source[old.layout.root:old.layout.end]
        new_arena = again.original[again.layout.root:again.layout.end]
        old_block, new_block = arena.LEGACY_CAPACITY_BLOCK_OFFSET, arena.CAPACITY_BLOCK_OFFSET
        # every byte before the old tail is the save's own (records, names, history pool, tables) ...
        self.assertEqual(new_arena[:old_block - 16], old_arena[:old_block - 16])
        # ... the descriptor and block sit before the new end, the auxiliary tail at the end, zeros between
        self.assertEqual(new_arena[new_block - 16:new_block + arena.BLOCK_SIZE],
                         old_arena[old_block - 16:old_block + arena.BLOCK_SIZE])
        if aux:
            self.assertEqual(new_arena[-aux:], old_arena[-aux:])
        # the whole 0x400 tail keeps its distance from the end (hn1's 448 spare bytes included) ...
        self.assertEqual(new_arena[-0x410:], old_arena[-0x410:])
        start = new_block + arena.BLOCK_SIZE
        self.assertEqual(new_arena[start:start + len(pattern)], pattern)
        # ... and the old tail and the new gap are cleared
        self.assertFalse(any(new_arena[old_block - 16:new_block - 16]))
        self.assertEqual(again.history_words, old.history_words)



@unittest.skipUnless(XBE.is_file(), 'the capacity build needs the pinned USA XBE')
class CapacityBuildWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()

    def test_build_applies_the_growth_owner_for_a_capacity_request(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        adapter = tt._roster_arena_adapter(False, 0, True)
        self.assertEqual(adapter.kwargs, {'reserves_16': False, 'created_teams_extra': 0, 'capacity': True})
        # The apply-list gate must select the owner for roster_capacity alone.
        source = Path(tt.__file__).read_text()
        self.assertIn('reserves_16 or created_teams_extra or roster_capacity', source)

    def test_capacity_build_with_mycareer_keeps_both_owners_status_valid(self):
        requests = tuple(k128.REQUESTS) + tuple(growth.REQUESTS) + tuple(mc.REQUESTS)
        xbe, _ = space.apply(self.retail, requests, scaleout=True)
        xbe, _ = k128.apply(xbe, roster_heap=True, require=True)
        xbe, _ = mc.apply(xbe)
        xbe, receipt = growth.apply(xbe, reserves_16=False, created_teams_extra=0, capacity=True)
        self.assertEqual(growth.status(xbe), 'applied')
        self.assertEqual(mc.status(xbe), 'applied')
        self.assertFalse(receipt['save_path_shims'])
        self.assertTrue(receipt['my_career_companion'])
        # MyCareer's runtime owns the two save sites; it admits both capacity sizes.
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(xbe)
        self.assertEqual(image.read(0x16ABCF, 6), bytes.fromhex('3986ccc1bd00'))
        self.assertNotEqual(image.read(0x16E7E5, 5), bytes.fromhex('e86616f5ff'))

    def test_non_capacity_build_does_not_install_the_capacity_shims(self):
        requests = tuple(k128.REQUESTS) + tuple(growth.REQUESTS)
        xbe, _ = space.apply(self.retail, requests, scaleout=True)
        xbe, _ = k128.apply(xbe, roster_heap=True, require=True)
        xbe, receipt = growth.apply(xbe, reserves_16=True, created_teams_extra=0, capacity=False)
        self.assertEqual(growth.status(xbe), 'applied')
        self.assertFalse(receipt['save_path_shims'])
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(xbe)
        self.assertEqual(image.read(0x16ABCF, 6), bytes.fromhex('3986ccc1bd00'))
        self.assertEqual(image.read(0x16E7E5, 5), bytes.fromhex('e86616f5ff'))


if __name__ == '__main__':
    unittest.main()
