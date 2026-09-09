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
        # MyCareer M3 (beta 63) deliberately places its promoted 16 KiB code AFTER every other code allocation, so
        # that one row moves with the union by design; every other owner must keep its exact address.
        promoted = ('nfl2k5_my_career', 'code')
        self.assertEqual([a for a in before if (a['owner'], a['kind']) != promoted],
                         [a for a in after if a['owner'] != growth.OWNER and (a['owner'], a['kind']) != promoted])
        self.assertEqual([(a['owner'], a['size']) for a in before if (a['owner'], a['kind']) == promoted],
                         [(a['owner'], a['size']) for a in after if (a['owner'], a['kind']) == promoted])
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
