"""The franchise loader restores the saved coaching row for each selected club."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from itertools import combinations
import json
from pathlib import Path
import struct
import sys
from tempfile import TemporaryDirectory
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mod_editor.core import nfl2k5_load_user_team_guard as guard
from mod_editor.core import nfl2k5_rdata_sites as sites
from mod_editor.core.nfl2k5_bump_strength import SECTION_COUNT, _sections, section_digest
from tests.mod_editor.test_nfl2k5_cave_oracle import synthetic
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, Machine


def loader_fixture():
    """A sparse section table with just the registration loop, setter and original load guard."""
    spans = [(va, before) for _, va, before, _ in guard.SITES] + list(guard.NEIGHBOURS)
    pages = sorted({va & ~0xFFF for va, _ in spans})
    data = bytearray(0x1000 * (1 + len(pages)))
    data[:4] = b"XBEH"
    struct.pack_into("<II", data, 0x104, 0x10000, 0x1000)
    struct.pack_into("<II", data, 0x11C, SECTION_COUNT, 0x10200)
    for i, va in enumerate(pages):
        struct.pack_into("<5I", data, 0x200 + 56*i, 6, va, 0x1000, 0x1000*(i+1), 0x1000)
    for va, raw in spans:
        off = sites.offset_of(data, va)
        data[off:off+len(raw)] = raw
    for section in _sections(data):
        if section.raw_size:
            start = section.header_offset + 36
            data[start:start+20] = section_digest(data, section)
    return bytes(data)


def with_bytes(source, va, raw):
    off = sites.offset_of(source, va)
    return source[:off] + raw + source[off+len(raw):]


class LoaderRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = loader_fixture()
        cls.previous = sites.apply(cls.retail, guard.SITES_V1, "Original load guard")[0]
        cls.fixed = guard.apply(cls.retail)[0]

    def test_genuine_complete_states_upgrade_to_the_same_output(self):
        self.assertEqual(guard.status(self.retail), "retail")
        self.assertEqual(guard.read_settings(self.previous), {"status": "previous", "load_user_team_guard": True})
        self.assertEqual(guard.status(self.fixed), "applied")
        upgraded, receipt = guard.apply(self.previous)
        self.assertEqual(upgraded, self.fixed)
        self.assertEqual((receipt["upgraded_from"], receipt["revision"]), (1, 2))
        _, va, _, patch = guard.PLAN_SITE
        self.assertEqual([(r["va"], r["bytes"]) for r in receipt["edits"]], [(hex(va), 13)])
        section = next(s for s in _sections(upgraded) if s.virtual_address <= va < s.virtual_address+s.raw_size)
        self.assertEqual(section.stored_digest, section_digest(upgraded, section))
        changed = {i for i, (old, new) in enumerate(zip(self.previous, upgraded)) if old != new}
        off = sites.offset_of(upgraded, va)
        allowed = set(range(off, off+len(patch))) | set(range(section.header_offset+36, section.header_offset+56))
        self.assertLessEqual(changed, allowed)
        again, repeat = guard.apply(upgraded)
        self.assertEqual(again, upgraded)
        self.assertTrue(repeat["already_applied"])

    def test_copy_only_cli_upgrades_the_previous_guard_and_refuses_an_existing_output(self):
        from mod_editor.core import nfl2k5_patch_cli
        with TemporaryDirectory() as folder:
            source = Path(folder) / "older.xbe"
            target = Path(folder) / "updated.xbe"
            source.write_bytes(self.previous)
            args = ["load_user_team_guard", str(source), str(target)]
            receipt = StringIO()
            with redirect_stdout(receipt):
                self.assertEqual(nfl2k5_patch_cli.main(args), 0)
            self.assertEqual(json.loads(receipt.getvalue())["upgraded_from"], 1)
            self.assertEqual(target.read_bytes(), self.fixed)
            target.write_bytes(b"existing disc copy")
            with self.assertRaises(SystemExit), redirect_stderr(StringIO()):
                nfl2k5_patch_cli.main(args)
            self.assertEqual(target.read_bytes(), b"existing disc copy")
            self.assertEqual(source.read_bytes(), self.previous)

    def test_partial_owners_and_each_changed_guard_are_refused(self):
        for mask in range(1 << len(guard.SITES)):
            if mask in (0, 7, 15):
                continue
            mixed = self.retail
            for bit, (_, va, _, patch) in enumerate(guard.SITES):
                if mask & (1 << bit):
                    mixed = with_bytes(mixed, va, patch)
            with self.subTest(mask=mask):
                self.assertEqual(guard.status(mixed), "foreign")
                with self.assertRaises(sites.RdataSiteError):
                    guard.apply(mixed)
        for source in (self.retail, self.previous, self.fixed):
            for va, raw in [(s[1], s[2]) for s in guard.SITES] + list(guard.NEIGHBOURS):
                for address in (va, va+len(raw)-1):
                    wrong = bytes([source[sites.offset_of(source, address)] ^ 0x80])
                    altered = with_bytes(source, address, wrong)
                    with self.subTest(va=hex(address)):
                        self.assertEqual(guard.status(altered), "foreign")
                        with self.assertRaises(sites.RdataSiteError):
                            guard.apply(altered)


@unittest.skipUnless(HAVE_UC, "Unicorn is required for native club registration")
class NativeRegistrationTests(unittest.TestCase):
    def test_previous_and_current_loop_for_every_single_and_pair(self):
        stock = loader_fixture()
        cases = [()] + [(i,) for i in range(32)] + list(combinations(range(32), 2))
        cases += [(1, 15, 31), tuple(range(0, 32, 2)), tuple(range(1, 32, 2)), tuple(range(32))]
        base, table, width = 0xE41CE0, 0xE5A268, 36
        for fixed, payload in ((False, stock), (True, guard.apply(stock)[0])):
            m = Machine(synthetic(), trace_writes=False)
            for va, raw in [(s[1], s[2]) for s in guard.SITES] + list(guard.NEIGHBOURS):
                off = sites.offset_of(payload, va)
                m.uc.mem_write(va, payload[off:off+len(raw)])
            # Generate the selection-list boundary. The actual loader, its stride math and its
            # native table setter execute below. Full signed leagues exercise these three helpers.
            m.leaf(0x13EC40, lambda: m.ret(len(clubs)), reason="number of selected human clubs")
            m.leaf(0x13EBE0, lambda: m.ret(m.ARENA + 500*clubs[m.reg("ECX")]), reason="return selected club record")
            m.leaf(0xC4CA0, lambda: m.ret((m.reg("ECX")-m.ARENA)//500), reason="resolve the record to its league index")
            sentinels = struct.pack("<288I", *range(288))
            m.uc.mem_write(base, sentinels)
            for clubs in cases:
                m.uc.mem_write(table-4, b"\xA5"*136)
                m.uc.mem_write(table, bytes(128))
                m.call(0x2D0D98, stop=0x2D0DCC)
                expected = [0] * 32
                for ordinal, club in enumerate(clubs):
                    expected[club] = base + width * (club if fixed else ordinal)
                with self.subTest(fixed=fixed, clubs=clubs):
                    self.assertEqual(bytes(m.uc.mem_read(table-4, 136)),
                                     b"\xA5"*4 + struct.pack("<32I", *expected) + b"\xA5"*4)
                    self.assertEqual(bytes(m.uc.mem_read(base, len(sentinels))), sentinels)


if __name__ == "__main__":
    unittest.main()
