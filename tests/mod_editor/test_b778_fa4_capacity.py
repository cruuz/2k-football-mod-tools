"""b778 fa4: capacity-grown ROST arena (0xB0000) and the 561-candidate free-agent plan.

Private fixtures are skipped when absent; every structural claim runs on the real writer/codec.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_roster_arena_growth as growth
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_save_writer as save_writer
from mod_editor.core import nfl2k5_spare_capacity as spare

BASE = Path(os.environ.get('NFL2K5_FA4_BASE',
                           '/home/noah/2k-worktrees/.b77-scratch/b778/fa3/work/oct13_main_body.bin'))
PLAN = Path(os.environ.get('NFL2K5_FA4_PLAN',
                           '/home/noah/2k-worktrees/.b77-scratch/b778/rt1/out/roster-edits-b778-rt1.json'))
HUB = Path(os.environ.get('NFL2K5_SAVE_FIXTURES', '/home/noah/Desktop/2K5-8 Editors/save_fixtures'))
XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION',
                          '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'
RECORDS = 612
CANDIDATES = 533


def _fa3():
    spec = importlib.util.spec_from_file_location('b778_fa3', ROOT / 'tools/b77/b778_fa3_free_agent_depth.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fa4():
    spec = importlib.util.spec_from_file_location('b778_fa4', ROOT / 'tools/b77/b778_fa4_capacity.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CapacityMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BASE.is_file():
            raise unittest.SkipTest(f'fa4 base ROST body absent: {BASE}')
        cls.base = BASE.read_bytes()
        cls.grown, cls.receipt = arena.migrate(cls.base, reserves_16=False, capacity_records=RECORDS)

    def test_layout_capacity_and_inverse(self):
        doc = codec.decode(self.grown)
        self.assertEqual(doc.layout.version, 18)
        self.assertEqual(doc.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
        self.assertEqual(doc.tables['primary'].count, 2619 + RECORDS)
        self.assertEqual(doc.tables['primary'].count, self.receipt['primary_after'])
        self.assertEqual(doc.overflow.reserves_enabled, False)
        self.assertEqual(arena.capacity_descriptor(self.grown, doc.layout),
                         (RECORDS, self.receipt['names_start'] - RECORDS * 84))
        self.assertEqual(len(self.grown), arena.CAPACITY_ARENA_SIZE + 0x40)
        self.assertEqual(spare.import_vacancies(self.grown), 155 + RECORDS)
        # A disc resource grows from a disc resource; the retail-geometry inspectors get it back byte for byte.
        source = b'ROST' + struct.pack('<7I', len(self.base), len(self.base), 0, 0, 0, 0, 0) + self.base
        grown, _ = arena.migrate(source, reserves_16=False, capacity_records=RECORDS)
        self.assertEqual(arena.legacy_disc_resource(grown), source)

    def test_replay_is_a_no_op_and_options_refuse(self):
        replay, receipt = arena.migrate(self.grown, reserves_16=False, capacity_records=RECORDS)
        self.assertEqual(replay, self.grown)
        self.assertTrue(receipt['already_applied'])
        with self.assertRaises(ValueError):
            arena.migrate(self.base, reserves_16=True, capacity_records=RECORDS)
        with self.assertRaises(ValueError):
            arena.migrate(self.base, created_teams_extra=2, capacity_records=RECORDS)
        with self.assertRaises(ValueError):
            arena.migrate(self.base, reserves_16=False, capacity_records=0)

    def test_capacity_records_are_private_blank_create_records(self):
        doc = rr.RosterDocument(self.grown, scheme='one_pool', reference_year=2026)
        by_key = {(player.pool, player.index): player for player in doc.players}
        first = 2619
        for index in range(first, first + RECORDS):
            player = by_key[('primary', index)]
            self.assertEqual(player.record.get('player_type'), 1)
            self.assertFalse(player.teams)
            self.assertEqual((player.first, player.last), ('****************', '****************'))
            self.assertNotIn(index, doc.free_agents)
        # Every new name buffer is private and adjacent; no share with an existing player.
        targets = []
        for index in range(first, first + RECORDS):
            player = by_key[('primary', index)]
            first_name = doc._pointer_target(player.offset, 'first_name_pointer')
            last_name = doc._pointer_target(player.offset, 'last_name_pointer')
            self.assertEqual(last_name, first_name + 34)
            self.assertEqual(doc.name_refs[first_name], 1)
            self.assertEqual(doc.name_refs[last_name], 1)
            targets.extend((first_name, last_name))
        self.assertEqual(len(targets), len(set(targets)))
        self.assertEqual(doc.names.text_at(targets[0]), '****************')

    def test_all_candidates_fit_at_the_safe_margin(self):
        if not PLAN.is_file():
            self.skipTest(f'fa3/rt1 plan absent: {PLAN}')
        fa3, fa4 = _fa3(), _fa4()
        data = fa3.load()
        self.assertEqual(len(data['players']), CANDIDATES)
        plan = json.loads(PLAN.read_text(encoding='utf-8'))['roster_refresh']
        fitted, floor_added, floor = fa4.floor_shortfall(self.base, plan, data, 10)
        self.assertEqual(fitted, 19)
        self.assertEqual(floor_added, 70)
        records = max((CANDIDATES - fitted) + floor_added, RECORDS)
        grown, _ = fa4.grow(self.base, records)
        extended = fa3.extend_plan(plan, data, CANDIDATES, grown)
        body, receipt = rr.apply_body(grown, {'schema': rr.EDITS_SCHEMA, 'edits': [],
                                              'roster_refresh': extended, 'restore_import_floor': True},
                                      scheme='one_pool')
        self.assertEqual(len(body), len(grown))
        final = rr.RosterDocument(body, scheme='one_pool', reference_year=2026)
        self.assertEqual(len(final.by_pool('primary')), 2619 + records)
        self.assertEqual(len(final.free_agents), 346 + CANDIDATES)
        vacancies = spare.import_vacancies(body)
        self.assertEqual(vacancies, receipt['roster_refresh']['import_floor']['vacancies_after'])
        self.assertGreaterEqual(vacancies, spare.IMPORT_FLOOR + 10)
        self.assertEqual(receipt['roster_refresh']['import_floor']['added_records'], 0)
        names = {p.display for p in final.players if p.offset in set(final.free_agents)}
        for player in data['players']:
            self.assertIn(f"{player['first']} {player['last']}", names)
        self.assertIn('Colin Kaepernick', names)
        # The grown body's free-agent list is still the native 2,500-pointer capacity.
        self.assertLessEqual(len(final.free_agents), final.free_agent_capacity)
        self.assertEqual(final.free_agent_capacity, 2500)
        self.assertEqual(spare.status(body), 'applied')
        spare.extended_layout(body)

    def test_tool_merge_writes_the_same_plan(self):
        if not PLAN.is_file():
            self.skipTest(f'fa3/rt1 plan absent: {PLAN}')
        fa4 = _fa4()
        with tempfile.TemporaryDirectory(prefix='fa4-plan-') as folder:
            out = Path(folder).resolve() / 'plan.json'
            result = fa4.merge(types.SimpleNamespace(edits=str(PLAN), base=str(BASE), out=str(out),
                                                     data=str(fa4.fa3.DATA), margin=10, records=RECORDS))
            self.assertEqual(result, 0)
            document = json.loads(out.read_text(encoding='utf-8'))
        request = document['free_agent_capacity']
        self.assertEqual(request['records'], RECORDS)
        self.assertEqual(request['arena_size'], arena.CAPACITY_ARENA_SIZE)
        self.assertEqual(request['final_primary'], 2619 + RECORDS)
        self.assertEqual(request['free_agents'], 346 + CANDIDATES)
        self.assertGreaterEqual(request['import_vacancies'], spare.IMPORT_FLOOR + 10)
        self.assertEqual(request['import_vacancies'], request['margin'] + spare.IMPORT_FLOOR)
        self.assertEqual(document['fa3_free_agent_depth']['added'], CANDIDATES)
        self.assertEqual(len(document['roster_refresh']['players']), len(json.loads(PLAN.read_text())['roster_refresh']['players']) + CANDIDATES)

    def test_save_migration_preserves_the_auxiliary_tail_and_suffix(self):
        source = HUB / 'f0/UDATA/53450030/0B8506889D40/SAVEGAME.DAT'
        if not source.is_file():
            self.skipTest(f'preserved save absent: {source}')
        original = source.read_bytes()
        grown, receipt = arena.migrate(original, reserves_16=False, capacity_records=RECORDS)
        delta = arena.CAPACITY_ARENA_SIZE - arena.RETAIL_SIZE
        self.assertEqual(len(grown), len(original) + delta)
        self.assertEqual(receipt['file_growth'], delta)
        doc = codec.decode(grown)
        self.assertEqual(doc.layout.version, 1)
        self.assertEqual(doc.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
        self.assertEqual(doc.tables['primary'].count, 2479 + RECORDS)
        self.assertEqual(struct.unpack_from('<I', grown, 0x2E8)[0], 366)
        self.assertEqual(grown[0x320 + arena.CAPACITY_ARENA_SIZE - 366:0x320 + arena.CAPACITY_ARENA_SIZE],
                         original[0x91320 - 366:0x91320])
        self.assertEqual(grown[0x91320 + delta:0x996FC + delta], original[0x91320:0x996FC])
        self.assertEqual(grown[0x996FC + delta:], original[0x996FC:])
        self.assertEqual(grown[:0x2E0], original[:0x2E0])
        save = fs.FranchiseSave(grown)
        self.assertEqual(save.header, fs.FranchiseSave(original).header)
        self.assertEqual(save.arena_end, 0x91320 + delta)
        self.assertEqual(save.season_block, 0x91320 + delta)
        self.assertEqual(save.front_office_block, 0x996FC + delta)
        # Signed cold copy through the unchanged container codec.
        container = rr.SaveContainer.load(source.parent)
        written = container.with_savegame(grown)
        with tempfile.TemporaryDirectory(prefix='fa4-cold-') as folder:
            target = Path(folder).resolve() / 'save'
            target.mkdir()
            for name, payload in written.items():
                (target / Path(name).name).write_bytes(payload)
            reopened = rr.SaveContainer.load(target)
            self.assertTrue(rr.verify_extra(reopened.savegame, reopened.members[reopened.extra_name]))
            cold, _ = codec.load_save(target)
            self.assertEqual(cold.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
            self.assertEqual(cold.tables['primary'].count, 2479 + RECORDS)
            self.assertEqual(fs.FranchiseSave(cold.to_bytes()).header, fs.FranchiseSave(original).header)

    def test_sizes_match_the_save_writer_and_container(self):
        self.assertEqual(arena.CAPACITY_ARENA_SIZE - arena.RETAIL_SIZE, save_writer.CAPACITY_SAVE_GROWTH)
        self.assertEqual(save_writer.CAPACITY_SAVE_SIZE, 720044 + save_writer.CAPACITY_SAVE_GROWTH)
        self.assertEqual(arena.CAPACITY_BLOCK_OFFSET, arena.CAPACITY_ARENA_SIZE - 0x400)
        self.assertEqual(arena.CAPACITY_ARENA_SIZE + 0x60, 0xB0060)
        self.assertEqual(arena.CAPACITY_ARENA_SIZE + 0x40, 0xB0040)


@unittest.skipUnless(XBE.is_file(), 'pinned USA XBE required for the capacity image build')
class CapacityImageIntegrationTests(unittest.TestCase):
    FA4_PLAN = Path(os.environ.get(
        'NFL2K5_FA4_PLAN_OUT', '/home/noah/2k-worktrees/.b77-scratch/b778/fa5/out/roster-edits-b778-fa5.json'))

    def test_build_helper_reads_the_capacity_request(self):
        if not self.FA4_PLAN.is_file():
            self.skipTest('generated fa4 plan absent')
        from mod_editor.core import mod_build
        self.assertEqual(mod_build._roster_capacity_records(
            types.SimpleNamespace(roster_edits=str(self.FA4_PLAN))), RECORDS)
        self.assertEqual(mod_build._roster_capacity_records(types.SimpleNamespace(roster_edits=None)), 0)

    def test_paired_growth_then_the_real_refresh_writes_every_candidate(self):
        if not (BASE.is_file() and self.FA4_PLAN.is_file() and (XBE.parent / 'vc_53450030/0').is_file()):
            self.skipTest('capacity integration needs the fa4 base, generated plan and retail ROST pack')
        from tests.mod_editor.test_nfl2k5_roster_arena_image import SyntheticXiso
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        from mod_editor.core import mod_build, nfl2k5_music_archive as archive
        from mod_editor.core import nfl2k5_roster_arena_image as writer
        require_nfl_retail_packs(XBE.parent)
        base = BASE.read_bytes()
        resource = b'ROST' + struct.pack('<7I', len(base), len(base), 0, 0, 0, 0, 0) + base
        executable = XBE.read_bytes()
        with tempfile.TemporaryDirectory(prefix='fa4-image-') as folder:
            directory = Path(folder).resolve()
            entries = [(100 + i, bytes([i]) * 2048) for i in range(5)]
            entries += [(writer.ROST_NAME_ID, resource), (200, b'neighbor' * 256)]
            fixture = SyntheticXiso(directory, entries, pack_sizes=(0x10000,) * 16,
                                    pack_sectors=tuple(64 + 32 * i for i in range(16)))
            fd = os.open(fixture.path, os.O_RDWR | getattr(os, 'O_BINARY', 0))
            try:
                archive.write_named(fd, lambda n, at: archive.io.pread(fd, n, at), 0, 'default.xbe',
                                    lambda n, at: executable[at:at + n], len(executable))
            finally:
                os.close(fd)
            destination = directory / 'capacity.iso'
            built = writer.build_image(fixture.path, destination, reserves_16=False,
                                       created_teams_extra=0, capacity_records=RECORDS)
            self.assertEqual(built['verification']['status'], 'verified')
            self.assertEqual(built['rost']['primary_after'], 2619 + RECORDS)
            receipt = {'steps': []}
            plan = types.SimpleNamespace(roster_edits=str(self.FA4_PLAN), position_pools=True,
                                         espn25_more_moments=True, historic_teams_quick_game=True)
            mod_build._apply_roster_refresh(plan, destination, receipt, lambda *_a: None)
            step = receipt['steps'][0]['roster_refresh']
            self.assertGreaterEqual(step['added'], CANDIDATES)
            self.assertGreaterEqual(step['import_floor']['vacancies_after'], spare.IMPORT_FLOOR + 10)
            with archive.Disc(destination, descriptors=()) as disc:
                entry = disc.archive_entries[5]
                final = codec.decode(disc.read_entry_range(entry, 0, entry.size))
            self.assertEqual(final.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
            self.assertEqual(final.tables['primary'].count, 2619 + RECORDS)
            self.assertEqual(final.tables['free_agents'].count, 346 + CANDIDATES)


@unittest.skipUnless(XBE.is_file(), 'pinned USA XBE required for the native capacity boot path')
class CapacityNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.mod_editor import test_nfl2k5_roster_arena_growth as growth_tests
        if not (XBE.parent / 'vc_53450030/0').is_file():
            raise unittest.SkipTest('capacity boot proof requires the preserved ROST pack')
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(XBE.parent)
        cls.retail = XBE.read_bytes()
        cls.xbe, _ = growth.apply(cls.retail, reserves_16=False, capacity=True)
        from mod_editor.core import nfl2k5_team_history as history
        with history._outer_image()(XBE.parent) as archive:
            entry = history._entry(archive)
            retail_rost = archive.read(entry.virtual_offset, entry.size)
        cls.rost, _ = arena.migrate(retail_rost, reserves_16=False, capacity_records=RECORDS)
        cls.site = growth.allocation(cls.xbe)
        cls.labels = {name: cls.site['va'] + offset for name, offset in growth.assembly.CAPACITY_LABELS.items()}
        cls.machine_class = growth_tests.BootPathTests

    def _machine(self):
        base = self.machine_class('test_retail_pair_loads_through_the_boot_path')
        base.machine(self.xbe)
        return base

    def test_capacity_boot_path_admits_and_relocates_the_whole_arena(self):
        base = self._machine()
        admitted, position = base.boot(self.rost)
        self.assertTrue(admitted)
        self.assertEqual(position, 0x1000)
        root = base.word(0xB72918)
        self.assertEqual((base.word(0xB72808), base.word(0xB7280C)),
                         (arena.CAPACITY_ARENA_SIZE, arena.CAPACITY_ARENA_SIZE))
        self.assertEqual(base.word(root), codec.decode(self.rost).tables['primary'].count)
        self.assertEqual(base.call(self.labels['integrity']), 1)
        base.call(0xC0730, ecx=root)
        self.assertEqual(bytes(base.uc.mem_read(root, arena.CAPACITY_ARENA_SIZE)), self.rost[0x60:])
        base.call(0xC0500, ecx=root)
        base.call(0xC7530)
        base.call(0x77D20)
        self.assertEqual((base.word(0xB72918), base.word(root + 0x18)), (root, 52))
        self.assertEqual(base.call(self.labels['integrity']), 1)


if __name__ == '__main__':
    unittest.main()
