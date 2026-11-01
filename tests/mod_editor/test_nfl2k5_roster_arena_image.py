"""Portable schema proofs and a bounded, transactional paired-archive proof."""
from pathlib import Path
import hashlib
import importlib.util
import os
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_roster_arena_growth as growth
from mod_editor.core import nfl2k5_roster_arena_image as writer
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import nfl2k5_practice_squad as ps
from tests.nfl2k5_xiso_fixture import SyntheticXiso
from tests.mod_editor import test_nfl2k5_roster_arena_growth as evidence


class PublicTests(unittest.TestCase):
    def test_header_limits_crc_and_canonical_rows(self):
        block = arena.Overflow(eligible_mask=1).with_row(0, (21, 23, 25, 27, 29))
        data = bytearray(arena.ARENA_SIZE)
        struct.pack_into('<I', data, 0, 100)
        arena.write_block(data, 0, block)
        self.assertEqual(arena.read(data, 0, len(data), 1), block)
        self.assertEqual((block.limit(0), block.limit(1)), (17, 16))
        self.assertEqual(arena.Overflow(reserves_enabled=False).limit(0), 12)
        for at in range(32):
            bad = bytearray(data); bad[arena.BLOCK_OFFSET+at] ^= 1
            with self.assertRaises(ValueError): arena.read(bad, 0, len(bad), 1)
        with self.assertRaises(ValueError): block.with_row(0, (2, 2))
        with self.assertRaises(ValueError): block.with_row(0, range(6))
        with self.assertRaises(ValueError): arena.Overflow(eligible_mask=1, reserves_enabled=False).encode()

    def test_options_and_full_union_preserve_existing_allocations(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        from mod_editor.core import nfl2k5_xbe_space as space
        before = space._scale_allocations([r for r in REQUESTS if r[0] != growth.OWNER])
        after = space._scale_allocations(REQUESTS)
        # Growth adds 8 KiB before the promoted MyCareer code and its code owners that follow. Static tails, the honors
        # gap, every data/RO row and every other code allocation keep their complete records.
        #   - my_career and the sprite scorebug sit directly behind the growth owner: +8,192.
        #   - b779 km1/hn1: K128 (1,536 B) and champions (5,632 B in the plan) fit the v3 code run before the growth
        #     but not after it (the 8 KiB fills the run), so both go whole to the pool, in LATE_OWNERS order.
        #   - letter_grades and its progression row sit behind K128 in the run; K128 leaving it frees 1,536 B, so they
        #     move +8,192 - 1,536 = +6,656.
        #   - cpu_third_down (last, 192 B) used to sit behind champions; with champions in the pool it sits directly
        #     behind the progression row (+16) instead.
        movers = {(name, 'code', 0) for name in (
            'nfl2k5_my_career', 'nfl2k5_scorebug_runtime', 'nfl2k5_k128', 'nfl2k5_champions',
            'nfl2k5_letter_grades', 'nfl2k5_letter_grades_progress', 'nfl2k5_cpu_third_down')}
        key = lambda row: (row['owner'], row['kind'], row.get('owner_offset', 0))
        self.assertTrue(movers.issubset({key(row) for row in before}))
        added = [row for row in after if row['owner'] == growth.OWNER]
        self.assertEqual([(row['kind'], row['size']) for row in added], [('code', 8192)])
        spills = [('nfl2k5_k128', 'code', 0), ('nfl2k5_champions', 'code', 0)]
        shifts = {('nfl2k5_my_career', 'code', 0): 8192, ('nfl2k5_scorebug_runtime', 'code', 0): 8192,
                  ('nfl2k5_letter_grades', 'code', 0): 8192 - 1536,
                  ('nfl2k5_letter_grades_progress', 'code', 0): 8192 - 1536}
        by_before = {key(row): row for row in before}
        k128_size = by_before[spills[0]]['size']
        self.assertEqual(k128_size, 1536)
        expected = []
        for row in before:
            if key(row) in spills:
                continue
            result = dict(row)
            if key(row) in shifts:
                result['va'] += shifts[key(row)]
                result['raw'] += shifts[key(row)]
            elif key(row) == ('nfl2k5_cpu_third_down', 'code', 0):
                moved = {**by_before[('nfl2k5_letter_grades_progress', 'code', 0)]}
                result['va'] = moved['va'] + shifts[('nfl2k5_letter_grades_progress', 'code', 0)] + moved['size']
                result['raw'] = moved['raw'] + shifts[('nfl2k5_letter_grades_progress', 'code', 0)] + moved['size']
            expected.append(result)
        self.assertEqual(expected, [row for row in after
                                    if row['owner'] != growth.OWNER and row['va'] < space.POOL_VA])
        # The spilled owners keep their identity; the pool holds its directory page, then K128, then champions
        # (aligned 16: K128's 1,536 B end on 0x600).
        for spill in spills:
            old_spill, new_spill = by_before[spill], next(row for row in after if key(row) == spill)
            self.assertEqual({k: v for k, v in old_spill.items() if k not in ('va', 'raw')},
                             {k: v for k, v in new_spill.items() if k not in ('va', 'raw')})
        pool_k128 = space.POOL_VA + space.PAGE
        self.assertEqual(sorted((row['owner'], row['kind'], row['size'], row['va'])
                                for row in after if row['va'] >= space.POOL_VA),
                         sorted([('nfl2k5_k128', 'code', 1536, pool_k128),
                                 ('nfl2k5_champions', 'code', by_before[spills[1]]['size'], pool_k128 + 1536),
                                 (space.DIRECTORY_OWNER, 'read_only', 4096, space.POOL_VA)]))
        for kwargs in (dict(created_teams_extra=1), dict(created_teams_extra=True), dict(reserves_16=1),
                       dict(reserves_16=False, created_teams_extra=0)):
            with self.assertRaises(ValueError): growth.options(**kwargs)
        for data in (b'', b'XBEH'+bytes(4092)):
            self.assertEqual(growth.status(data), 'foreign')
            with self.assertRaises(ValueError): growth.apply(data)


@unittest.skipUnless(evidence.XBE.is_file(), 'paired archive proof requires pinned USA XBE and extracted ROST')
class PairedArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='arena-paired-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        from mod_editor.core import nfl2k5_team_history as history
        if not (evidence.XBE.parent/'vc_53450030/0').is_file():
            self.skipTest('paired archive proof requires the preserved ROST pack')
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(evidence.XBE.parent)
        with history._outer_image()(evidence.XBE.parent) as disc:
            entry = history._entry(disc)
            rost = disc.read(entry.virtual_offset, entry.size)
        entries = [(100+i, bytes([i])*2048) for i in range(5)]
        entries += [(writer.ROST_NAME_ID, rost), (200, b'neighbor'*256)]
        fixture = SyntheticXiso(self.directory, entries, pack_sizes=(0x10000,)*16,
                                pack_sectors=tuple(64+32*i for i in range(16)))
        self.source = fixture.path
        executable = evidence.XBE.read_bytes()
        self.assertEqual(hashlib.sha256(executable).hexdigest(), ps.RETAIL_SHA256)
        fd = os.open(self.source, os.O_RDWR | getattr(os, 'O_BINARY', 0))
        try:
            archive.write_named(fd, lambda n, at: archive.io.pread(fd, n, at), 0, 'default.xbe',
                                lambda n, at: executable[at:at+n], len(executable))
        finally:
            os.close(fd)
        self.before = archive.file_hash(self.source)

    def test_paired_growth_replay_neighbors_and_transaction_rollback(self):
        destination = self.directory/'grown.iso'
        self.assertEqual(writer.image_status(self.source), 'retail')
        receipt = writer.build_image(self.source, destination, created_teams_extra=2)
        self.assertEqual(writer.image_status(destination), 'applied')
        self.assertTrue(receipt['source_unchanged_verified'])
        self.assertEqual(receipt['verification']['unchanged_outers'], 6)
        with archive.Disc(destination, descriptors=()) as disc:
            entry = disc.archive_entries[5]
            self.assertEqual(entry.size, 0x92060)
            from mod_editor.core.nfl2k5_save_rost import decode
            self.assertEqual(len(decode(disc.read_entry_range(entry, 0, entry.size)).teams), 54)
        replay = self.directory/'replay.iso'
        writer.build_image(destination, replay, created_teams_extra=2)
        self.assertEqual(archive.file_hash(replay), archive.file_hash(destination))
        self.assertEqual(archive.file_hash(self.source), self.before)
        published = archive.file_hash(destination)
        with patch.object(writer, '_verify', side_effect=ValueError('injected read-back failure')):
            with self.assertRaisesRegex(ValueError, 'injected'):
                writer.build_image(self.source, destination, created_teams_extra=2, overwrite=True)
        self.assertEqual(archive.file_hash(destination), published)
        self.assertEqual(archive.file_hash(self.source), self.before)
        self.assertFalse(list(self.directory.glob('.archive-*')))

    def test_capacity_growth_pairs_with_the_wider_arena(self):
        destination = self.directory/'capacity.iso'
        receipt = writer.build_image(self.source, destination, reserves_16=False,
                                     created_teams_extra=0, capacity_records=612)
        self.assertEqual(writer.image_status(destination), 'applied')
        self.assertEqual(receipt['verification']['status'], 'verified')
        # b779 ag1: 612 create vacancies, then free draft-class records up to what the arena holds (4,096 at most)
        self.assertEqual(receipt['rost']['vacancy_records'], 612)
        added = receipt['rost']['class_records']
        self.assertGreater(added, 0)
        self.assertEqual(receipt['rost']['capacity_records'], 612 + added)
        self.assertEqual(receipt['rost']['arena_size'], arena.CAPACITY_ARENA_SIZE)
        self.assertEqual(receipt['xbe']['capacity'], True)
        with archive.Disc(destination, descriptors=()) as disc:
            entry = disc.archive_entries[5]
            self.assertEqual(entry.size, arena.CAPACITY_ARENA_SIZE + 0x60)
            from mod_editor.core.nfl2k5_save_rost import decode
            resource = disc.read_entry_range(entry, 0, entry.size)
            grown = decode(resource)
            self.assertEqual(grown.layout.arena_size, arena.CAPACITY_ARENA_SIZE)
            self.assertEqual(grown.tables['primary'].count, 2479 + 612 + added)
            self.assertLessEqual(grown.tables['primary'].count, arena.CAPACITY_PRIMARY_LIMIT)
            self.assertIsNotNone(arena.capacity_descriptor(resource, grown.layout))
        self.assertEqual(self.before, archive.file_hash(self.source))

    def test_retail_geometry_inspectors_read_the_grown_roster_as_migrated(self):
        # The roster writers that run before the growth (2026 team names, team history, prospect names,
        # star tags) pin the retail 0x90F80 roster. After the growth their inspectors read the roster the
        # growth migrated: legacy_disc_resource() is the exact inverse, proved by migrating it again.
        from mod_editor.core import nfl2k5_team_names_2026 as names_2026
        from mod_editor.core import nfl2k5_team_history as history
        from mod_editor.core import nfl2k5_prospect_names as prospects
        from mod_editor.core import nfl2k5_player_tags as tags
        with archive.Disc(self.source, descriptors=()) as disc:
            entry = disc.archive_entries[writer.ROST_INDEX]
            retail = disc.read_entry_range(entry, 0, entry.size)
        edited, _ = names_2026.apply(retail)
        header, body = edited[:history.RESOURCE_HEADER_SIZE], edited[history.RESOURCE_HEADER_SIZE:]
        body, _ = history.apply_body(body, history.load_rows('retail')[0])
        body, _ = prospects.apply_body(body, prospects.load_rows('modern')[0])
        body, _ = tags.apply_body(body, ['615', '607', '247'])
        edited = header + body
        checks = (names_2026.status, history.resource_status, prospects.resource_status, tags.resource_status)
        self.assertEqual([check(edited) for check in checks], ['applied'] * 4)
        for flags in ((True, 0), (False, 2), (True, 2)):
            grown, _ = arena.migrate(edited, reserves_16=flags[0], created_teams_extra=flags[1])
            self.assertEqual(len(grown), arena.GROWN_DISC_RESOURCE_SIZE)
            self.assertEqual(arena.legacy_disc_resource(grown), edited)
            self.assertEqual(arena.legacy_disc_resource(arena.migrate(retail, reserves_16=flags[0],
                                                                      created_teams_extra=flags[1])[0]), retail)
        at = 0x60 + arena.BLOCK_OFFSET + 40   # an overflow row: the CRC no longer matches
        for bad in (retail, grown[:-1], grown[:at] + bytes([grown[at] ^ 1]) + grown[at + 1:]):
            with self.assertRaises(ValueError):
                arena.legacy_disc_resource(bad)
        # Whole images: the four inspectors read the same state before and after the paired growth.
        entries = [(100+i, bytes([i])*2048) for i in range(5)]
        entries += [(writer.ROST_NAME_ID, edited), (200, b'neighbor'*256)]
        fixture = SyntheticXiso(self.directory / 'edited', entries, pack_sizes=(0x10000,)*16,
                                pack_sectors=tuple(64+32*i for i in range(16)))
        executable = evidence.XBE.read_bytes()
        fd = os.open(fixture.path, os.O_RDWR | getattr(os, 'O_BINARY', 0))
        try:
            archive.write_named(fd, lambda n, at: archive.io.pread(fd, n, at), 0, 'default.xbe',
                                lambda n, at: executable[at:at+n], len(executable))
        finally:
            os.close(fd)
        grown_image = self.directory / 'edited-grown.iso'
        writer.build_image(fixture.path, grown_image, created_teams_extra=2)
        readers = (names_2026.image_status, history.status, prospects.status, tags.status)
        self.assertEqual([read(fixture.path) for read in readers], ['applied'] * 4)
        self.assertEqual([read(grown_image) for read in readers], ['applied'] * 4)
        self.assertEqual([read(self.source) for read in readers], ['retail'] * 4)
        # The writers still refuse a grown roster; only the inspectors read through it.
        with self.assertRaises(ValueError):
            history.apply(grown_image)

    def test_pin_guard_code_option_and_partial_hook_refusals(self):
        original = evidence.XBE.read_bytes()
        out, _ = growth.apply(original, created_teams_extra=2)
        self.assertEqual(growth.apply(out, created_teams_extra=2)[0], out)
        with self.assertRaises(ValueError): growth.apply(out, created_teams_extra=0)
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        empty = growth.space.apply(original, growth.REQUESTS, scaleout=True)[0]
        from tests.nfl2k5_practice_squad_screen_fixture import composed
        empty = composed(empty)
        partial = bytearray(empty)
        address = ps.SYMBOLS['ps_demote']
        at = growth.rdata.offset_of(empty, address)
        partial[at:at+5] = growth._jump(address, growth.allocation(empty)['va'], 5)
        for section in _sections(partial):
            partial[section.header_offset+36:section.header_offset+56] = section_digest(partial, section)
        self.assertEqual(growth.status(bytes(partial)), 'foreign')
        with self.assertRaises(ValueError): growth.apply(bytes(partial))
        for source, address in ((original, 0xC2058), (out, 0xC2058),
                                (out, growth.allocation(out)['va']+growth.OPTION_OFFSET)):
            changed = bytearray(source)
            at = growth.rdata.offset_of(source, address)
            changed[at] ^= 1
            for section in _sections(changed):
                changed[section.header_offset+36:section.header_offset+56] = section_digest(changed, section)
            self.assertEqual(growth.status(bytes(changed)), 'foreign')
            with self.assertRaises(ValueError): growth.apply(bytes(changed), created_teams_extra=2)


if __name__ == '__main__':
    unittest.main()
