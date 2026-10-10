"""Bounded native resolver proof; synthetic loaded SITU rows, no gameplay claim."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import hashlib
import json
import struct
import unittest

from mod_editor.core import nfl2k5_stock_books as books
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.nfl2k5_supersim_draft_fixture import Machine

RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')
try:
    import unicorn
except ImportError:
    unicorn = None


@unittest.skipUnless(RETAIL.is_file() and unicorn, 'USA retail XBE and Unicorn required')
class ModernMomentBooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise ValueError('USA retail XBE pin differs')
        cls.current = books.apply(cls.retail)[0]
        allocated = space.apply(cls.retail, books.REQUESTS)[0]
        a = books.allocation(allocated)
        for name, code in (('legacy', books.code_for(a['va'], modern_moments=False, legacy=True)),
                           ('previous50', books.code_for(a['va'], moment_limit=50, legacy=True)),
                           ('v05', books.code_for(a['va'], legacy=True))):      # b77-a4: the v0.5 body (40 byte alias rows)
            buf = bytearray(space.install_code(allocated, books.OWNER, code)[0])
            image = XbeImage(buf)
            at = image.offset(books.SITE, len(books.RETAIL))
            buf[at:at + len(books.RETAIL)] = books.hook(a['va'])
            for section in books._sections(buf):
                buf[section.header_offset + 36:section.header_offset + 56] = books.section_digest(buf, section)
            setattr(cls, name, bytes(buf))

    def machine(self, payload=None):
        m = Machine(payload or self.current, trace_writes=False)
        a = m.ARENA
        m.put(a + 0x110, a + 0x300)
        m.put(a + 0x304, a + 0x400)
        m.uc.mem_write(a + 0x400, 'BUF\0'.encode('utf-16le'))
        m.put(0xC8F0D4, a + 0x1000)
        m.put(0xC8F0D8, books.MOMENT_COUNT)
        return m

    def resolve(self, m, *, mode=8, ordinal=0, home=False, category=4, null_team=False):
        a = m.ARENA
        m.put(0xE5FF80, mode)
        m.put(0xBF1858, ordinal)
        m.put(a + 0x128, category)
        m.put(a + 0x508, int(home))
        m.uc.mem_write(a + 0x600, b'\xA5' * 32)
        for name, value in dict(EAX=0 if null_team else a, EBX=0x1234, EDI=0, ESI=a + 0x600,
                                EBP=a + 0x500, ESP=m.STACK, EFLAGS=0x202).items():
            m.reg(name, value)
        stops = (0x62A1B, 0x62A37)
        hook = m.uc.hook_add(unicorn.UC_HOOK_CODE,
                            lambda uc, va, *_: uc.emu_stop() if va in stops else None)
        try:
            m.uc.emu_start(books.SITE, m.STOP, count=1000)
        finally:
            m.uc.hook_del(hook)
        self.assertIn(m.reg('EIP'), stops)
        self.assertEqual(m.reg('ESP'), m.STACK)
        self.assertEqual((m.reg('EBX'), m.reg('EDI'), m.reg('ESI'), m.reg('EBP')),
                         (0 if null_team else a, 0, a + 0x600, a + 0x500))
        modern = m.reg('EIP') == 0x62A1B
        if not modern:
            self.assertEqual(bytes(m.uc.mem_read(a + 0x600, 32)).decode('utf-16le').rstrip('\0'),
                             'E2R-BUF-pb.iff')
        return modern

    def seasons(self, m, away, home, ordinal=0):
        at = m.ARENA + 0x1000 + ordinal * 0x6C
        m.put(at + 0x1C, away)
        m.put(at + 0x20, home)

    def test_all_profile_seasons_both_sides_and_legacy_counterexample(self):
        rows = json.loads((Path(__file__).resolve().parents[2] /
                          'data/nfl2k5_era_rules.json').read_text())['mappings']
        self.assertEqual(len(rows), books.MOMENT_COUNT)
        m, legacy = self.machine(), self.machine(self.legacy)
        for row in rows:
            ordinal, year = row['row'] - 1, row['season']
            for machine in (m, legacy):
                self.seasons(machine, year, year, ordinal)
            for home in (False, True):
                with self.subTest(row=row['row'], home=home):
                    self.assertEqual(self.resolve(m, ordinal=ordinal, home=home),
                                     books.MODERN_FIRST_SEASON <= year <= books.MODERN_LAST_SEASON)
                    self.assertFalse(self.resolve(legacy, ordinal=ordinal, home=home))

    def test_side_specific_year_boundaries_and_non_anniversary_modes(self):
        m = self.machine()
        for year in (0, 1999, 2004, 2005, 2022, 2030, 2031, 0xFFFFFFFF):
            self.seasons(m, year, 1990)
            self.assertEqual(self.resolve(m), 2005 <= year <= 2030)
            self.assertFalse(self.resolve(m, home=True))
        self.seasons(m, 1990, 2022)
        self.assertFalse(self.resolve(m))
        self.assertTrue(self.resolve(m, home=True))
        for mode in (0, 1, 2, 3, 4, 7, 9):
            self.assertFalse(self.resolve(m, mode=mode, home=True, category=4))
            self.assertTrue(self.resolve(m, mode=mode, home=True, category=0))

    def test_unloaded_bad_count_and_out_of_range_ordinal_keep_stock(self):
        m = self.machine()
        self.seasons(m, 2022, 2022)
        for count, ordinal, pointer in ((0, 0, m.ARENA + 0x1000), (52, 0, m.ARENA + 0x1000),
                                        (51, 51, m.ARENA + 0x1000),
                                        (50, 50, m.ARENA + 0x1000), (50, -1, m.ARENA + 0x1000),
                                        (50, 0, 0), (50, 1, 0), (50, 49, 0)):
            m.put(0xC8F0D8, count)
            m.put(0xC8F0D4, pointer)
            self.assertFalse(self.resolve(m, ordinal=ordinal))

    def test_null_team_preserves_legacy_continuation_and_abi(self):
        for payload in (self.current, self.legacy):
            m = self.machine(payload)
            self.seasons(m, 2022, 2022)
            self.assertTrue(self.resolve(m, null_team=True))

    def test_exact_upgrade_idempotence_and_foreign_code_refusal(self):
        for previous in (self.legacy, self.previous50, self.v05):
            self.assertEqual(books.status(previous), 'needs_fix')
            fixed, receipt = books.apply(previous)
            self.assertEqual(fixed, self.current)
            self.assertTrue(receipt['upgraded_moment_routing'])
            self.assertEqual(books.apply(fixed)[0], fixed)
            disabled, _ = books.apply(previous, enabled=False)
            self.assertEqual(books.apply(disabled)[0], fixed)
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        studio, _ = tuning._apply_all(self.previous50, None, catch_slider=False, historic_stock_books=True)
        self.assertEqual(books.status(studio), 'applied')
        # Current code still accepts an exactly bounded old 50-row collection.
        old = self.machine(self.previous50)
        old.put(0xC8F0D8, 50)
        self.seasons(old, 2025, 2025, 49)
        self.assertTrue(self.resolve(old, ordinal=49))
        image = XbeImage(self.legacy)
        for va in (books.allocation(self.legacy)['va'] + 20, 0x2CFD40):
            bad = bytearray(self.legacy)
            bad[image.offset(va, 1)] ^= 1
            self.assertEqual(books.status(bytes(bad)), 'foreign')
            with self.assertRaises(ValueError):
                books.apply(bytes(bad))

    def test_chronological_display_composes_only_with_exact_anniversary_owner(self):
        from mod_editor.core import nfl2k5_espn25_more_moments as moments
        reserved = space.apply(self.retail, books.REQUESTS + moments.REQUESTS)[0]
        chronological = moments.apply(reserved)[0]
        final = books.apply(chronological)[0]
        self.assertEqual(moments.status(final), "applied")
        self.assertEqual(books.status(final), "applied")
        self.assertEqual(books.apply(final)[0], final)
        bad = bytearray(final)
        bad[XbeImage(final).offset(0x20CB45, 1)] ^= 1
        self.assertEqual(books.status(bytes(bad)), "foreign")
        with self.assertRaises(ValueError):
            books.apply(bytes(bad))


if __name__ == '__main__':
    unittest.main()
