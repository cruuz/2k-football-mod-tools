"""Bounded real-XDVDFS proof for the Anniversary image writer and its rollback."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import struct
import tempfile
import unittest
from unittest.mock import patch

from tests.nfl2k5_xiso_fixture import SyntheticXiso
from mod_editor.core import nfl2k5_anniversary_pack as pack
from mod_editor.core import nfl2k5_espn25_more_moments as mm
from mod_editor.core import nfl2k5_historic_styles as styles
from mod_editor.core import nfl2k5_music_archive as archive
from mod_editor.core import platform_compat as io


class AnniversaryImageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.resources = {'a00dd.iff': b'first synthetic alias'.ljust(2048, b'A'),
                          'a50nd.iff': b'newest synthetic alias'.ljust(2048, b'B')}

    def fixture(self, name, *, partition=0):
        # Twenty-five old resources include a SITU-shaped directory identity;
        # the writer is tested without parsing any synthetic resource body.
        # The final old member spans 0..F and ends exactly at the archive end.
        members = [(mm.SITU_ID if i == mm.SITU_OUTER else 0x12340000+i, bytes((i+1,))*2048)
                   for i in range(24)]
        members.append((0x1234ffff, b'OLD END-OF-ARCHIVE'.ljust(16*2048, b'F')))
        fixture = SyntheticXiso(self.root/name, members, pack_sizes=(26*2048,)+(2048,)*15,
                                pack_sectors=(64,)+tuple(96+3*i for i in range(15)))
        if partition:
            fixture.path.write_bytes(bytes(partition)+fixture.image)
        return fixture.path, dict(members)

    def test_real_readers_follow_rewritten_nodes_preserve_old_payloads_and_replay_identically(self):
        for partition in (0, 0x30000):
            with self.subTest(partition=partition):
                path, members = self.fixture('append-'+str(partition), partition=partition)
                before = path.read_bytes()
                self.assertLess(len(before), 512*1024)
                with archive.Disc(path, descriptors=()) as disc:
                    old_nodes = dict(disc.nodes)
                    old_packs = {name: disc.read(e.size, e.byte_offset) for name, e in disc.pack_extents.items()}
                receipt = pack.append_to_image(path, self.resources)
                after = path.read_bytes()
                self.assertEqual(receipt['status'], 'applied')
                self.assertEqual(len(after)-len(before), receipt['image_growth'])
                with archive.Disc(path, descriptors=()) as disc:
                    self.assertEqual(disc.partition, partition)
                    self.assertEqual(len(disc.archive_entries), len(members)+3)  # two aliases + alignment member
                    for name in '0F':
                        at, sector, size = disc.nodes[name]
                        self.assertEqual(at, old_nodes[name][0])
                        self.assertNotEqual(sector, old_nodes[name][1])
                        self.assertGreaterEqual(partition+sector*2048, len(before))
                        self.assertEqual(after[at:at+8], struct.pack('<II', sector, size))
                    for name in '123456789ABCDE':
                        self.assertEqual(disc.nodes[name], old_nodes[name])
                        e = disc.pack_extents[name]
                        self.assertEqual(disc.read(e.size, e.byte_offset), old_packs[name])
                    f = disc.pack_extents['F']
                    self.assertEqual(disc.read(len(old_packs['F']), f.byte_offset), old_packs['F'])
                    for entry in disc.archive_entries:
                        if entry.name_id in members:
                            self.assertEqual(disc.read_entry_range(entry, 0, entry.size), members[entry.name_id])
                with styles.Source(path) as source:
                    for name, raw in self.resources.items():
                        self.assertEqual(source.get(name), raw)
                    for identity, raw in members.items():
                        self.assertEqual(source.get(identity=identity), raw)
                # Inside the old image, only the two eight-byte XDVDFS nodes changed.
                masked_before, masked_after = bytearray(before), bytearray(after[:len(before)])
                for name in '0F':
                    at = old_nodes[name][0]
                    masked_before[at:at+8] = masked_after[at:at+8] = bytes(8)
                self.assertEqual(masked_before, masked_after)
                replay = pack.append_to_image(path, self.resources)
                self.assertEqual(replay['status'], 'already_applied')
                self.assertEqual(path.read_bytes(), after)
                path.rename(path.with_suffix('.closed'))  # all Windows-visible handles must be closed

    def test_partial_payload_partial_directory_and_readback_failures_restore_complete_image(self):
        for failure in ('payload', 'directory', 'readback'):
            with self.subTest(failure=failure):
                path, members = self.fixture(failure)
                before = path.read_bytes()
                real_write, real_read = archive.write_all, io.pread
                calls = 0
                failed = False
                def write(fd, raw, at):
                    nonlocal calls, failed
                    calls += 1
                    target = 1 if failure == 'payload' else 4
                    if failure != 'readback' and calls == target and not failed:
                        failed = True
                        real_write(fd, raw[:max(1, len(raw)//2)], at)
                        raise OSError('injected partial '+failure+' write')
                    return real_write(fd, raw, at)
                def read(fd, count, at):
                    nonlocal failed
                    raw = real_read(fd, count, at)
                    if failure == 'readback' and at >= len(before) and not failed:
                        failed = True
                        return raw[:-1]+bytes((raw[-1]^1,))
                    return raw
                with patch.object(archive, 'write_all', side_effect=write), patch.object(io, 'pread', side_effect=read):
                    if failure == 'readback':
                        with self.assertRaisesRegex(ValueError, 'pack readback'):
                            pack.append_to_image(path, self.resources)
                    else:
                        with self.assertRaisesRegex(OSError, 'injected partial'):
                            pack.append_to_image(path, self.resources)
                self.assertTrue(failed)
                self.assertEqual(path.read_bytes(), before)
                with archive.Disc(path, descriptors=()) as disc:
                    self.assertEqual(len(disc.archive_entries), len(members))
                with styles.Source(path) as source:
                    self.assertTrue(all(source.get(identity=identity) == raw for identity, raw in members.items()))
                path.rename(path.with_suffix('.closed'))


if __name__ == '__main__':
    unittest.main()
