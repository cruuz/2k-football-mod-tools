"""Crib cut: bounded 16-pack transactions and native movie failure dispatch."""
from pathlib import Path
import hashlib
import os
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_crib_reclaim as c, nfl2k5_my_career as career
from mod_editor.core import nfl2k5_music_archive as a, platform_compat as io
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.nfl2k5_xiso_fixture import SyntheticXiso
from tests.nfl2k5_my_career_fixture import XBE, HAVE_UC, Machine


class InventoryTests(unittest.TestCase):
    def test_exact_23_movie_cut_retains_trophy_room(self):
        self.assertEqual(len(c.MOVIES), 23)
        self.assertEqual(sum(n for _, _, n, _ in c.MOVIES), 417169408)
        self.assertTrue({4248, 4272, 4291}.isdisjoint({i for i, *_ in c.MOVIES}))
        self.assertEqual(c.REQUESTS, ())
        self.assertEqual(len(c.TOMBSTONE), 2048)


@unittest.skipUnless(XBE.is_file(), "pinned USA retail default.xbe is absent")
class RebuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe = XBE.read_bytes()
        if hashlib.sha256(cls.xbe).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("retail XBE differs from USA evidence pin")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        entries = [(i, bytes([i % 251]) * 2048) for i in range(4322)]
        movies = []
        for i, name, *_ in c.MOVIES:
            raw = bytes([i % 251]) * 6144
            entries[i] = (zlib.crc32(name.upper().encode("utf-16le")), raw)
            movies.append((i, name, len(raw), hashlib.sha256(raw).hexdigest()))
        patch = mock.patch.object(c, "MOVIES", tuple(movies))
        patch.start()
        self.addCleanup(patch.stop)
        fixture = SyntheticXiso(self.root, entries, pack_sizes=(0x90000,) * 16,
                                pack_sectors=tuple(64 + i * (0x90000 // 2048 + 1) for i in range(16)))
        self.source = fixture.path
        # The fixture is about 10 MiB; append the bounded retail XBE through the
        # same XDVDFS writer used in production. Never keep an acceptance disc.
        fd = os.open(self.source, os.O_RDWR | getattr(os, "O_BINARY", 0))
        try:
            a.write_named(fd, lambda n, at: io.pread(fd, n, at), 0, "default.xbe",
                          lambda n, at: self.xbe[at:at+n], len(self.xbe))
        finally:
            os.close(fd)
        self.assertLess(self.source.stat().st_size, 24 * 1024**2)

    def test_stream_rebuild_shrinks_disc_every_retained_outer_and_replay(self):
        source_hash = a.file_hash(self.source)
        plan = c.plan(self.source)
        self.assertEqual(plan["archive_bytes_reclaimed"], 23 * 4096)
        self.assertGreater(plan["disc_bytes_reclaimed"], 0)
        output = self.root / "cut.iso"
        receipt = c.rebuild(self.source, output, expected_plan=plan)
        self.assertEqual(a.file_hash(self.source), source_hash)
        check = receipt["verification"]
        self.assertTrue(check["all_retained_outer_hashes_verified"])
        self.assertEqual(set(check["trophy_outer_sha256"]), {"4248", "4272", "4291"})
        self.assertEqual(output.stat().st_size, self.source.stat().st_size - plan["disc_bytes_reclaimed"])
        replay = c.plan(output)
        self.assertTrue(replay["already_applied"])
        self.assertEqual(replay["disc_bytes_reclaimed"], 0)
        c.rebuild(output, self.root / "replay.iso", expected_plan=replay)
        self.assertEqual(a.file_hash(output), a.file_hash(self.root / "replay.iso"))
        self.assertFalse(list(self.root.glob(".archive-*")))

    def test_bad_inventory_and_stale_plan_refuse_before_publication(self):
        plan = c.plan(self.source)
        bad = dict(plan, source_sha256="changed")
        target = self.root / "no.iso"
        with self.assertRaisesRegex(ValueError, "stale"):
            c.rebuild(self.source, target, expected_plan=bad)
        self.assertFalse(target.exists())
        with a.Disc(self.source, descriptors=()) as disc:
            entry = disc.archive_entries[4298]
            location = disc.entry_spans(entry, 0, 1)[0].xiso_offset
        with self.source.open("r+b") as stream:
            stream.seek(location)
            stream.write(b"x")
        with self.assertRaisesRegex(ValueError, "foreign Crib movie payload"):
            c.rebuild(self.source, target)
        self.assertFalse(target.exists())

    def test_verification_failure_closes_handles_and_preserves_destination(self):
        output = self.root / "output.iso"
        output.write_bytes(b"existing destination")
        with mock.patch.object(c, "verify", side_effect=ValueError("injected verify failure")):
            with self.assertRaisesRegex(ValueError, "injected"):
                c.rebuild(self.source, output, overwrite=True)
        self.assertEqual(output.read_bytes(), b"existing destination")
        self.assertFalse(list(self.root.glob(".archive-*")))
        # Windows-compatible replacement after failure is also a handle check.
        replacement = self.root / "replacement"
        replacement.write_bytes(b"replaceable")
        os.replace(replacement, output)
        self.assertEqual(output.read_bytes(), b"replaceable")

    def test_xbe_only_reports_zero_reclaim_and_foreign_consumer_refuses(self):
        result, receipt = c.apply(self.xbe)
        self.assertEqual(c.status(result), "applied")
        self.assertEqual(c.apply(result)[0], result)
        self.assertEqual(receipt["disc_bytes_reclaimed"], 0)
        bad = bytearray(result)
        bad[c.rdata.offset_of(bad, 0x272A94)] ^= 1
        self.assertEqual(c.status(bytes(bad)), "foreign")
        with self.assertRaises(ValueError):
            c.apply(bytes(bad))


@unittest.skipUnless(HAVE_UC and XBE.is_file(), "Unicorn or pinned USA retail default.xbe is absent")
class MovieNativeTests(unittest.TestCase):
    def test_all_23_movies_never_open_and_pop_without_context_destructor(self):
        retail = XBE.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            self.skipTest("retail XBE differs from USA evidence pin")
        m = Machine(c.apply(career.apply(retail)[0])[0])
        opened, destroyed, popped = [], [], []
        m.stub(0x3CBBF0, lambda: (opened.append(True), m.ret(1, pop=8)))
        m.stub(0x3CCF90, lambda: (destroyed.append(True), m.ret()))
        m.stub(0x6E400, lambda: (popped.append(True), m.ret()))
        for va, pop in ((0x26DA50, 0), (0x2712F0, 0), (0x2716A0, 4)):
            m.stub(va, lambda pop=pop: m.ret(pop=pop))
        for index in range(23):
            m.put(0xAC8680, 0)
            m.put(0xAC8684, index)
            m.call(0x272A60, args=(m.BODIES,))
            self.assertEqual(m.get(0xAC8680), 6)
            m.call(0x272A60, args=(m.BODIES,))
        self.assertEqual(opened, [])
        self.assertEqual(destroyed, [])
        self.assertEqual(len(popped), 23)


if __name__ == "__main__":
    unittest.main()
