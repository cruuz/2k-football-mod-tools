"""b779 ag1: more player records. The capacity arena grows from beta-78's 0xB0000 (3,231 records) to 0xCA000
(4,096 records) and every size the Studio, the save tools and the native owners name comes from one layout helper
(nfl2k5_roster_arena). beta-78 saves (847,020 bytes, 847,148 with the MyCareer footer) are admitted and migrate.

Native checks run the real generated code under Unicorn; private fixtures (the retail ROST pack, preserved saves)
are skipped when absent.
"""
from __future__ import annotations

import importlib.util
import os
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_save_rost as codec

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
                          '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'
HUB = Path(os.environ.get('NFL2K5_SAVE_FIXTURES', '/home/noah/Desktop/2K5-8 Editors/save_fixtures'))
SAVE = HUB / 'f0/UDATA/53450030/0B8506889D40/SAVEGAME.DAT'
HAVE_UC = importlib.util.find_spec('unicorn') is not None


def _retail_rost():
    if not (XBE.parent / 'vc_53450030/0').is_file():
        raise unittest.SkipTest('the retail ROST pack is absent')
    from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
    require_nfl_retail_packs(XBE.parent)
    from mod_editor.core import nfl2k5_team_history as history
    with history._outer_image()(XBE.parent) as archive:
        entry = history._entry(archive)
        return archive.read(entry.virtual_offset, entry.size)


class LayoutHelperTests(unittest.TestCase):
    """One layout helper; every consumer follows it."""

    def test_the_capacity_geometry(self):
        self.assertEqual(arena.CAPACITY_ARENA_SIZE, 0xCA000)
        self.assertEqual(arena.LEGACY_CAPACITY_ARENA_SIZE, 0xB0000)          # beta-78 / v0.7, shipped
        self.assertEqual(arena.CAPACITY_SAVE_SIZE, 953516)
        self.assertEqual(arena.LEGACY_CAPACITY_SAVE_SIZE, 847020)
        self.assertEqual(arena.save_size(arena.RETAIL_SIZE), 720044)
        self.assertEqual(arena.save_size(arena.ARENA_SIZE), 724140)
        self.assertEqual(arena.disc_resource_size(), 0xCA060)
        self.assertEqual(arena.CAPACITY_BLOCK_OFFSET, 0xCA000 - 0x400)
        self.assertEqual(arena.block_offset(arena.LEGACY_CAPACITY_ARENA_SIZE), 0xAFC00)
        self.assertEqual(arena.block_offset(arena.ARENA_SIZE), 0x91C00)
        with self.assertRaises(arena.ArenaError):
            arena.block_offset(0xC0000)
        # 4,096 records fit from the retail 2,619-record disc roster and from a retail save
        self.assertGreaterEqual(arena.capacity_fit(0x90F40), arena.CAPACITY_PRIMARY_LIMIT - 2619)
        self.assertGreaterEqual(arena.capacity_fit(0x91000), arena.CAPACITY_PRIMARY_LIMIT - 2619)

    def test_every_size_site_follows_the_helper(self):
        from mod_editor.core import nfl2k5_save_writer as writer, nfl2k5_player_progression as progression
        from mod_editor.core import nfl2k5_my_career_save as career
        self.assertEqual(writer.CAPACITY_SAVE_SIZE, arena.CAPACITY_SAVE_SIZE)
        self.assertEqual(writer.CAPACITY_SAVE_SIZES, (847020, 953516))
        self.assertEqual(progression.NATIVE_SAVE_SIZES, (720044, 724140, 847020, 953516))
        self.assertEqual(career.BASE_SIZES, (720044, 724140, 847020, 953516))
        self.assertEqual(arena.BARE_BODY_SIZES[18], (0x92040, 0xB0040, 0xCA040))
        sys.path.insert(0, str(ROOT / 'tools'))
        import nfl2k5_roster_reclassify as reclassify
        self.assertEqual(reclassify.GROWN_ARENA_SIZES, arena.ARENA_SIZES)
        sys.path.insert(0, str(ROOT / 'tools/roster_arena'))
        spec = importlib.util.spec_from_file_location('ag1_build_runtime', ROOT / 'tools/roster_arena/build_runtime.py')
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        self.assertIn(f'ARENA_SIZE={arena.CAPACITY_ARENA_SIZE:#x}U', build.CAPACITY_DEFINES)
        self.assertIn(('LEGACY_CAPACITY_SAVE', 847020), build.ASM_SYMBOLS)

    def test_generated_capacity_runtime_names_the_new_arena(self):
        from mod_editor.core import nfl2k5_roster_arena_code as code
        self.assertIn(struct.pack('<I', 0xCA000), code.CAPACITY_CODE)
        self.assertIn(struct.pack('<I', 0xB0020), code.CAPACITY_CODE)           # beta-78 wrapper (load size)
        self.assertNotIn(struct.pack('<I', 0xAFC00), code.CAPACITY_CODE)        # no fixed beta-78 block offset
        from mod_editor.core import nfl2k5_roster_arena_growth as growth
        self.assertLessEqual(growth.CAPACITY_OPTION_OFFSET + 4, growth.CODE_SIZE)


class GrowthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail_rost()
        cls.grown, cls.receipt = arena.migrate(cls.retail, reserves_16=False, capacity_records=612)

    def test_vacancies_then_free_class_records(self):
        r = self.receipt
        doc = codec.decode(self.grown)
        self.assertEqual(doc.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
        self.assertEqual(len(self.grown), arena.disc_resource_size())
        self.assertEqual(r['vacancy_records'], 612)
        self.assertGreater(r['class_records'], 800)
        self.assertLessEqual(doc.tables['primary'].count, arena.CAPACITY_PRIMARY_LIMIT)
        primary = doc.tables['primary']
        flags = [self.grown[primary.offset + i * 84 + 8] for i in range(primary.count)]
        first = primary.count - r['capacity_records']
        self.assertTrue(all(f & 5 == 1 for f in flags[first:first + 612]))          # Create Player vacancies
        self.assertTrue(all(f == 0 for f in flags[first + 612:]))                   # free for the draft class
        self.assertEqual(arena.capacity_class_count(self.grown, doc.layout), r['class_records'])
        self.assertEqual(arena.capacity_descriptor(self.grown, doc.layout)[0], r['capacity_records'])
        self.assertEqual(doc.pool_capacity, 50000)
        # the retail-geometry inspectors still get the source back byte for byte
        self.assertEqual(arena.legacy_disc_resource(self.grown), self.retail)

    def test_a_beta78_roster_grows_to_the_same_bytes(self):
        legacy, _ = arena._migrate_capacity(self.retail, 612, class_records=0,
                                            arena_size=arena.LEGACY_CAPACITY_ARENA_SIZE)
        self.assertEqual(len(legacy), arena.disc_resource_size(arena.LEGACY_CAPACITY_ARENA_SIZE))
        extended, receipt = arena.migrate(legacy, reserves_16=False, capacity_records=612)
        self.assertEqual(receipt['source'], 'capacity')
        self.assertEqual(receipt['vacancy_records'], 0)
        self.assertEqual(extended, self.grown)
        self.assertEqual(arena.legacy_disc_resource(extended), self.retail)

    def test_hn1_champions_bytes_keep_their_place_before_the_end(self):
        # b779 hn1: the champions history is one checked block (270 bytes now, after the aux-tail fix) right after the 352-byte reserve block,
        # which starts 0x400 before the arena end (nfl2k5_champions_history.FROM_END / RESERVE_BLOCK / SPARE). A growth
        # keeps the reserve block at the new end - 0x400 and moves those 448 bytes with it.
        legacy, _ = arena._migrate_capacity(self.retail, 612, class_records=0,
                                            arena_size=arena.LEGACY_CAPACITY_ARENA_SIZE)
        doc = codec.decode(legacy)
        reserve = doc.layout.end - 0x400
        self.assertEqual(legacy[reserve:reserve + 8], arena.MAGIC)
        spare = reserve + arena.BLOCK_SIZE
        self.assertFalse(any(legacy[spare:spare + 448]))
        block = b'2K5CHMP\0' + bytes(range(1, 256)) + bytes(range(1, 186))     # 448 bytes
        self.assertEqual(len(block), 448)
        legacy = legacy[:spare] + block + legacy[spare + 448:]
        grown, receipt = arena.migrate(legacy, reserves_16=False, capacity_records=612)
        self.assertEqual(receipt['source'], 'capacity')
        new = codec.decode(grown)
        reserve = new.layout.end - 0x400
        self.assertEqual(reserve - new.layout.root, arena.CAPACITY_BLOCK_OFFSET)
        self.assertEqual(grown[reserve:reserve + 8], arena.MAGIC)
        self.assertIsNotNone(new.overflow)
        self.assertEqual(grown[reserve + arena.BLOCK_SIZE:reserve + arena.BLOCK_SIZE + 448], block)
        # the whole 0x400 tail moved unchanged (the descriptor before it now counts the appended class records)
        self.assertEqual(grown[new.layout.end - 0x400:new.layout.end], legacy[doc.layout.end - 0x400:doc.layout.end])

    def test_replay_is_a_no_op_and_the_limit_holds(self):
        again, receipt = arena.migrate(self.grown, reserves_16=False, capacity_records=612)
        self.assertTrue(receipt['already_applied'])
        self.assertEqual(again, self.grown)
        with self.assertRaises(arena.ArenaError):
            arena.migrate(self.retail, reserves_16=False, capacity_records=612, class_records=5000)

    def test_a_retail_save_grows_and_keeps_its_suffix(self):
        if not SAVE.is_file():
            self.skipTest(f'preserved save absent: {SAVE}')
        from mod_editor.core import nfl2k5_franchise_save as fs
        original = SAVE.read_bytes()
        grown, receipt = arena.migrate(original, reserves_16=False, capacity_records=612)
        self.assertEqual(len(grown), arena.CAPACITY_SAVE_SIZE)
        self.assertGreater(receipt['class_records'], 0)
        save = fs.FranchiseSave(grown)
        self.assertEqual(save.header, fs.FranchiseSave(original).header)
        growth = arena.CAPACITY_SAVE_GROWTH
        self.assertEqual(grown[0x91320 + growth:], original[0x91320:])


@unittest.skipUnless(HAVE_UC, 'Unicorn is not installed')
class MyCareerSaveSizeTests(unittest.TestCase):
    """The generic MyCareer runtime's save-list admission and load staging follow [0xB72808]."""
    CODE, DATA = 0x01000000, 0x01100000

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_my_career_mode as mc
        cls.mc = mc
        cls.blob, cls.labels = mc.code_for(cls.CODE, cls.DATA)

    def machine(self):
        import unicorn as uc
        m = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        for base, size in ((self.CODE, 0x10000), (self.DATA, 0x10000), (self.mc.EXTRA_VA & ~0xFFF, 0x3000),
                           (0xB72000, 0x1000), (0x02000000, 0x100000), (0x03000000, 0x10000)):
            m.mem_map(base, size)
        m.mem_write(self.CODE, self.blob)
        return m

    def call(self, m, label, ecx=0, edx=0):
        from unicorn import x86_const as x86
        sp = 0x03008000
        m.mem_write(sp, struct.pack('<I', 0x03000000))
        m.mem_write(0x03000000, b'\xf4')
        m.reg_write(x86.UC_X86_REG_ESP, sp)
        m.reg_write(x86.UC_X86_REG_ECX, ecx)
        m.reg_write(x86.UC_X86_REG_EDX, edx)
        m.emu_start(self.labels[label], 0x03000000, count=200000)
        return m.reg_read(x86.UC_X86_REG_EAX)

    def test_admission_follows_the_arena_and_admits_beta78_saves(self):
        m = self.machine()
        for arena_size, accepted, refused in (
                (0xCA000, (720044, 720172, 847020, 847148, 953516, 953644),
                 (724140, 847021, 953515, 953645, 0)),
                (0xB0000, (720044, 720172, 847020, 847148), (953516, 953644, 724140)),
                (0x92000, (720044, 720172, 724140, 724268), (847020, 953516)),
                (0x91000, (720044, 720172), (724140, 847020))):
            m.mem_write(0xB72808, struct.pack('<I', arena_size))
            for size in accepted:
                self.assertEqual(self.call(m, 'inline_admit', ecx=size), 1, (hex(arena_size), size))
            for size in refused:
                self.assertEqual(self.call(m, 'inline_admit', ecx=size), 0, (hex(arena_size), size))

    def _file(self, m, declared):
        growth = declared - 0x91020
        file = 0x02000000
        m.mem_write(file, bytes(0x100000))
        m.mem_write(file + 0x2E4, struct.pack('<I', declared))
        m.mem_write(file + 0x30C, b'ROST' + struct.pack('<II', int(growth != 0), 13))
        m.mem_write(file + 0x91320 + growth, b'\x02')
        return file, 720044 + growth

    def test_staging_reads_each_geometry_up_to_this_arena(self):
        m = self.machine()
        m.mem_write(0xB72808, struct.pack('<I', 0xCA000))
        state = self.DATA                                  # code_for(code_va, data_va): the state block
        for declared in (0x91020, 0xB0020, 0xCA020):
            file, size = self._file(m, declared)
            m.mem_write(state + 2580, bytes(4))
            self.assertEqual(self.call(m, 'inline_stage', ecx=file, edx=size), 1, hex(declared))
            self.assertEqual(struct.unpack('<I', m.mem_read(state + 2664, 4))[0], declared + 0x20)
        for declared in (0xA0020, 0xCB020):
            file, size = self._file(m, declared)
            self.assertEqual(self.call(m, 'inline_stage', ecx=file, edx=size), 0, hex(declared))
        # a beta-78 build never stages the larger save
        m.mem_write(0xB72808, struct.pack('<I', 0xB0000))
        file, size = self._file(m, 0xCA020)
        self.assertEqual(self.call(m, 'inline_stage', ecx=file, edx=size), 0)


@unittest.skipUnless(XBE.is_file(), 'the pinned USA XBE is required')
class CompositionTests(unittest.TestCase):
    def test_a_beta78_capacity_runtime_is_recognized_but_never_installed(self):
        # An already built beta-78 executable (0xB0000 runtime) reads as the installed capacity owner, so the owners
        # that validate against the growth owner's retail projection (economy, practice squad) still work on it; the
        # Studio refuses to install over it.
        from mod_editor.core import nfl2k5_roster_arena_growth as growth, nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        xbe, _ = growth.apply(XBE.read_bytes(), reserves_16=False, created_teams_extra=0, capacity=True)
        self.assertFalse(growth.read_settings(xbe)['legacy_capacity'])
        site = growth.allocation(xbe)
        flags = growth.options(False, 0, True)
        old = bytearray(xbe)
        blob = growth.code_for(site['va'], flags, legacy=True)
        at = rdata.offset_of(xbe, site['va'])
        old[at:at + len(blob)] = blob
        for _name, address, _before, after in growth.sites(site['va'], True, False, legacy=True):
            at = rdata.offset_of(xbe, address)
            old[at:at + len(after)] = after
        space._seal_scaleout(old, space._validate(xbe)[2])
        for section in _sections(old):
            old[section.header_offset + 36:section.header_offset + 56] = section_digest(old, section)
        old = bytes(old)
        self.assertEqual(growth.status(old), 'applied')
        settings = growth.read_settings(old)
        self.assertTrue(settings['legacy_capacity'])
        self.assertEqual(settings['arena_size'], arena.LEGACY_CAPACITY_ARENA_SIZE)
        self.assertIn(struct.pack('<I', 0xB0000), growth.code_for(site['va'], flags, legacy=True))
        # the retail projection restores every hook site
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        projected = XbeImage(growth.project(old))
        for name, address, before, _after in growth.sites(site['va'], True, False, legacy=True):
            self.assertEqual(projected.read(address, len(before)), before, name)
        with self.assertRaises(growth.ArenaGrowthError):
            growth.apply(old, reserves_16=False, created_teams_extra=0, capacity=True)

    def test_mycareer_validates_next_to_economy_revision_four(self):
        # MyCareer's native-context hash covers the cut-down 0x2BF9A0 that revision 4 jumps to its smart cut.
        from mod_editor.core import nfl2k5_k128 as k128, nfl2k5_roster_arena_growth as growth
        from mod_editor.core import nfl2k5_my_career_mode as mc, nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_practice_squad as ps, nfl2k5_franchise_economy as economy
        xbe, _ = space.apply(XBE.read_bytes(), tuple(k128.REQUESTS) + tuple(growth.REQUESTS) + tuple(mc.REQUESTS),
                             scaleout=True)
        xbe, _ = k128.apply(xbe, roster_heap=True, require=True)
        xbe, _ = ps.apply(xbe)
        xbe, _ = mc.apply(xbe)
        xbe, receipt = growth.apply(xbe, reserves_16=False, created_teams_extra=0, capacity=True)
        self.assertEqual(receipt['arena_size'], arena.CAPACITY_ARENA_SIZE)
        xbe, _ = economy.apply(xbe)
        self.assertEqual(economy.status(xbe), 'applied')
        self.assertEqual(mc.status(xbe), 'applied')
        self.assertEqual(growth.status(xbe), 'applied')


if __name__ == '__main__':
    unittest.main()
